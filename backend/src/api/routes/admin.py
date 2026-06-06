from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ...admin_auth import require_admin_user
from ...ai import _get_missing_llm_key_error
from ...config import get_config
from ...database import get_db
from ...runtime_settings import (
    RUNTIME_SETTING_KEYS,
    encrypt_setting_value,
    get_runtime_setting_rows,
    load_runtime_settings_cache,
)

router = APIRouter(prefix="/admin", tags=["admin"])


SETTING_METADATA = {
    "LLM": {
        "label": "LLM model",
        "description": "Provider and model, for example openai:gpt-5.2.",
        "input_type": "text",
    },
    "OPENAI_API_KEY": {
        "label": "OpenAI API key",
        "description": "Required for openai:* models.",
        "input_type": "password",
    },
    "GOOGLE_API_KEY": {
        "label": "Google API key",
        "description": "Required for google-gla:* models and fallback YouTube metadata.",
        "input_type": "password",
    },
    "ANTHROPIC_API_KEY": {
        "label": "Anthropic API key",
        "description": "Required for anthropic:* models.",
        "input_type": "password",
    },
    "OLLAMA_BASE_URL": {
        "label": "Ollama base URL",
        "description": "Optional URL for local or hosted Ollama-compatible endpoints.",
        "input_type": "text",
    },
    "OLLAMA_API_KEY": {
        "label": "Ollama API key",
        "description": "Optional, used by hosted Ollama-compatible providers.",
        "input_type": "password",
    },
    "YOUTUBE_DATA_API_KEY": {
        "label": "YouTube Data API key",
        "description": "Optional metadata provider key.",
        "input_type": "password",
    },
    "APIFY_API_TOKEN": {
        "label": "Apify API token",
        "description": "Optional YouTube download fallback provider token.",
        "input_type": "password",
    },
    "PEXELS_API_KEY": {
        "label": "Pexels API key",
        "description": "Optional B-roll stock footage provider key.",
        "input_type": "password",
    },
    "PLAN_FREE_LIMIT": {
        "label": "Free plan limit",
        "description": "Max generations per billing period for Free plan (0 = unlimited).",
        "input_type": "number",
    },
    "PLAN_PRO_LIMIT": {
        "label": "Pro plan limit",
        "description": "Max generations per billing period for Pro plan (0 = unlimited).",
        "input_type": "number",
    },
    "PLAN_SCALE_LIMIT": {
        "label": "Scale plan limit",
        "description": "Max generations per billing period for Scale plan (0 = unlimited).",
        "input_type": "number",
    },
}


class RuntimeSettingsUpdate(BaseModel):
    updates: dict[str, str] = Field(default_factory=dict)
    delete_keys: list[str] = Field(default_factory=list)
    prefer_admin_values: dict[str, bool] = Field(default_factory=dict)


def _setting_status(
    setting_key: str, rows: dict[str, dict[str, object]]
):
    env_value = get_config()._get_optional_env(setting_key)
    has_env = bool(env_value)
    row = rows.get(setting_key, {})
    has_admin_value = bool(row.get("encrypted_value"))
    prefer_admin_value = bool(row.get("prefer_admin_value"))
    metadata = SETTING_METADATA[setting_key]

    if has_admin_value and (prefer_admin_value or not has_env):
        source = "admin"
    elif has_env:
        source = "environment"
    else:
        source = "unset"

    return {
        "key": setting_key,
        "label": metadata["label"],
        "description": metadata["description"],
        "input_type": metadata["input_type"],
        "source": source,
        "configured": has_env or has_admin_value,
        "has_admin_value": has_admin_value,
        "has_env_value": has_env,
        "prefer_admin_value": prefer_admin_value,
        "overridden_by_env": has_env and has_admin_value and not prefer_admin_value,
        "updated_at": row.get("updated_at"),
    }


@router.get("/health")
async def admin_health(
    request: Request, db: AsyncSession = Depends(get_db)
):
    await require_admin_user(request, db, get_config())
    return {"status": "ok"}


@router.get("/runtime-settings")
async def get_runtime_settings(request: Request, db: AsyncSession = Depends(get_db)):
    await require_admin_user(request, db, get_config())
    rows = await get_runtime_setting_rows(db)
    return {
        "settings": [
            _setting_status(setting_key, rows) for setting_key in RUNTIME_SETTING_KEYS
        ]
    }


@router.patch("/runtime-settings")
async def update_runtime_settings(
    request: Request,
    payload: RuntimeSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    user_id = await require_admin_user(request, db, get_config())
    allowed_keys = set(RUNTIME_SETTING_KEYS)
    invalid_keys = [
        key
        for key in [
            *payload.updates.keys(),
            *payload.delete_keys,
            *payload.prefer_admin_values.keys(),
        ]
        if key not in allowed_keys
    ]
    if invalid_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported setting key(s): {', '.join(sorted(set(invalid_keys)))}",
        )

    if "LLM" in payload.updates:
        config_error = _get_missing_llm_key_error(
            payload.updates["LLM"].strip(), get_config()
        )
        if config_error and "API_KEY is not set" not in config_error:
            raise HTTPException(status_code=400, detail=config_error)

    for setting_key, raw_value in payload.updates.items():
        value = raw_value.strip()
        if not value:
            continue
        encrypted_value = encrypt_setting_value(value)
        await db.execute(
            text(
                """
                INSERT INTO app_settings (setting_key, encrypted_value, updated_by)
                VALUES (:setting_key, :encrypted_value, :updated_by)
                ON CONFLICT (setting_key) DO UPDATE
                SET encrypted_value = EXCLUDED.encrypted_value,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "setting_key": setting_key,
                "encrypted_value": encrypted_value,
                "updated_by": user_id,
            },
        )

    for setting_key, prefer_admin_value in payload.prefer_admin_values.items():
        await db.execute(
            text(
                """
                UPDATE app_settings
                SET prefer_admin_value = :prefer_admin_value,
                    updated_by = :updated_by,
                    updated_at = CURRENT_TIMESTAMP
                WHERE setting_key = :setting_key
                """
            ),
            {
                "setting_key": setting_key,
                "prefer_admin_value": prefer_admin_value,
                "updated_by": user_id,
            },
        )

    if payload.delete_keys:
        await db.execute(
            text(
                """
                DELETE FROM app_settings
                WHERE setting_key = ANY(CAST(:setting_keys AS text[]))
                """
            ),
            {"setting_keys": payload.delete_keys},
        )

    await db.commit()
    await load_runtime_settings_cache(db)

    rows = await get_runtime_setting_rows(db)
    return {
        "settings": [
            _setting_status(setting_key, rows) for setting_key in RUNTIME_SETTING_KEYS
        ]
    }


@router.get("/plans")
async def get_plans(request: Request, db: AsyncSession = Depends(get_db)):
    await require_admin_user(request, db, get_config())
    rows = await get_runtime_setting_rows(db)
    plan_keys = ["PLAN_FREE_LIMIT", "PLAN_PRO_LIMIT", "PLAN_SCALE_LIMIT"]
    config = get_config()
    return {
        "limits": [
            {
                "key": k,
                "label": {"PLAN_FREE_LIMIT": "Free", "PLAN_PRO_LIMIT": "Pro", "PLAN_SCALE_LIMIT": "Scale"}[k],
                "value": _plan_setting_value(k, rows, config),
            }
            for k in plan_keys
        ]
    }


class PlanLimitsUpdate(BaseModel):
    limits: dict[str, str]


@router.patch("/plans")
async def update_plans(
    request: Request,
    payload: PlanLimitsUpdate,
    db: AsyncSession = Depends(get_db),
):
    user_id = await require_admin_user(request, db, get_config())
    allowed = {"PLAN_FREE_LIMIT", "PLAN_PRO_LIMIT", "PLAN_SCALE_LIMIT"}
    for key, value in payload.limits.items():
        if key not in allowed:
            continue
        encrypted_value = encrypt_setting_value(str(value))
        await db.execute(
            text("""
                INSERT INTO app_settings (setting_key, encrypted_value, updated_by)
                VALUES (:key, :value, :updated_by)
                ON CONFLICT (setting_key) DO UPDATE
                SET encrypted_value = EXCLUDED.encrypted_value,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = CURRENT_TIMESTAMP
            """),
            {"key": key, "value": encrypted_value, "updated_by": user_id},
        )
    await db.commit()
    await load_runtime_settings_cache(db)
    return {"status": "ok"}


def _plan_setting_value(key: str, rows: dict, config) -> str:
    row = rows.get(key, {})
    if row.get("encrypted_value"):
        from ...runtime_settings import decrypt_setting_value
        try:
            return decrypt_setting_value(row["encrypted_value"])
        except Exception:
            pass
    env_map = {
        "PLAN_FREE_LIMIT": "free_plan_task_limit",
        "PLAN_PRO_LIMIT": "pro_plan_task_limit",
        "PLAN_SCALE_LIMIT": "scale_plan_task_limit",
    }
    return str(getattr(config, env_map[key], ""))


class CreateUserPayload(BaseModel):
    name: str = ""
    email: str
    password: str


@router.post("/users")
async def admin_create_user(
    request: Request,
    payload: CreateUserPayload,
    db: AsyncSession = Depends(get_db),
):
    from ...admin_auth import _get_user_id_from_request
    admin_id = await require_admin_user(request, db, get_config())
    import bcrypt
    import uuid
    user_id = str(uuid.uuid4())
    hashed = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
    await db.execute(
        text("""
            INSERT INTO users (id, name, email, email_verified, password_hash, plan, subscription_status, is_admin)
            VALUES (:id, :name, :email, TRUE, :password_hash, 'free', 'inactive', FALSE)
        """),
        {
            "id": user_id,
            "name": payload.name or payload.email.split("@")[0],
            "email": payload.email,
            "password_hash": hashed,
        },
    )
    await db.commit()
    return {"user": {"id": user_id, "email": payload.email, "name": payload.name or payload.email.split("@")[0]}}
