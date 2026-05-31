#!/bin/bash
set -e
# Creates or resets the default admin user for local development
# Credentials: admin@supoclip.local / admin123

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Generate scrypt hash matching better-auth's format (salt:key)
HASH=$(cd "$SCRIPT_DIR/frontend" && node --experimental-vm-modules -e "
import('./node_modules/@better-auth/utils/dist/password.node.mjs').then(async (mod) => {
  process.stdout.write(await mod.hashPassword('admin123'));
}).catch(e => { console.error(e); process.exit(1); });
")

USER_ID=$(uuidgen 2>/dev/null || python3 -c "import uuid; print(uuid.uuid4())")

PGPASSWORD=supoclip_password psql -h localhost -U supoclip -d supoclip -t -c "
DO \$\$
DECLARE
  uid text;
BEGIN
  SELECT id INTO uid FROM users WHERE email = 'admin@supoclip.local';
  IF uid IS NULL THEN
    uid := gen_random_uuid()::text;
    INSERT INTO users (id, name, email, \"emailVerified\", \"createdAt\", \"updatedAt\", password_hash, is_admin, plan, subscription_status)
    VALUES (uid, 'Admin', 'admin@supoclip.local', true, NOW(), NOW(), '$HASH', true, 'pro', 'active');
  ELSE
    uid := uid;
  END IF;
  DELETE FROM account WHERE \"userId\" = uid AND \"providerId\" = 'credential';
  INSERT INTO account (id, \"accountId\", \"providerId\", \"userId\", password, \"createdAt\", \"updatedAt\")
  VALUES (gen_random_uuid()::text, uid, 'credential', uid, '$HASH', NOW(), NOW());
END \$\$;
" 2>&1

echo "✅ Default user ready: admin@supoclip.local / admin123"
