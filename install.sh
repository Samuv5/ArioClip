#!/bin/bash
set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BOLD}╔═══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║       ArioClip — Installer                ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Check OS ──────────────────────────────────────────────────
if [ ! -f /etc/os-release ]; then
    echo -e "${YELLOW}⚠  Unrecognized OS — proceeding anyway${NC}"
fi

# ── 2. Check prerequisites ──────────────────────────────────────
echo -e "${BOLD}Checking prerequisites...${NC}"

PREREQ_OK=true

check_cmd() {
    local cmd=$1
    local name=$2
    local hint=$3
    if command -v "$cmd" &>/dev/null; then
        echo -e "  ${GREEN}✅${NC} $name"
    else
        echo -e "  ${RED}❌${NC} $name — $hint"
        PREREQ_OK=false
    fi
}

check_cmd python3    "Python 3"     "Install Python 3.11+ (https://python.org)"
check_cmd node       "Node.js"      "Install Node.js 20+ (https://nodejs.org)"
check_cmd npm        "npm"          "Comes with Node.js"
check_cmd ffmpeg     "ffmpeg"       "Install ffmpeg (apt install ffmpeg / brew install ffmpeg)"
check_cmd psql       "PostgreSQL"   "Install PostgreSQL 15+ (apt install postgresql)"
check_cmd redis-cli  "Redis CLI"    "Install Redis 7+ (apt install redis-server)"
check_cmd git        "git"          "Install git (apt install git)"

# Check Python version
if command -v python3 &>/dev/null; then
    pyver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [ "$(echo "$pyver < 3.11" | bc -l 2>/dev/null || echo 1)" = "1" ]; then
        echo -e "  ${YELLOW}⚠  Python $pyver detected — 3.11+ recommended${NC}"
    fi
fi

# Check Node version
if command -v node &>/dev/null; then
    nodever=$(node -v | sed 's/v//' | cut -d. -f1)
    if [ "$nodever" -lt 18 ]; then
        echo -e "  ${YELLOW}⚠  Node.js $(node -v) detected — 18+ recommended${NC}"
    fi
fi

# Check uv (optional but recommended)
if command -v uv &>/dev/null; then
    echo -e "  ${GREEN}✅${NC} uv (Python package manager)"
else
    echo -e "  ${YELLOW}⚠  uv not found — will use pip instead (install via: curl -LsSf https://astral.sh/uv/install.sh | sh)${NC}"
fi

echo ""

if [ "$PREREQ_OK" = false ]; then
    echo -e "${RED}Please install missing prerequisites and try again.${NC}"
    exit 1
fi

# ── 3. Database setup ─────────────────────────────────────────────
echo -e "${BOLD}Setting up database...${NC}"

# Check if supoclip role exists
if psql -h localhost -U postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='supoclip'" 2>/dev/null | grep -q 1; then
    echo -e "  ${GREEN}✅${NC} PostgreSQL role 'supoclip' exists"
else
    echo -e "  ${YELLOW}⚡ Creating PostgreSQL role 'supoclip'...${NC}"
    sudo -u postgres createuser -P supoclip 2>/dev/null || createuser -h localhost -U postgres supoclip 2>/dev/null || echo -e "  ${YELLOW}⚠  Could not create role — create manually: createuser -P supoclip${NC}"
fi

# Check if supoclip database exists
if psql -h localhost -U supoclip -d supoclip -c "SELECT 1" 2>/dev/null | grep -q 1; then
    echo -e "  ${GREEN}✅${NC} Database 'supoclip' exists"
else
    echo -e "  ${YELLOW}⚡ Creating database 'supoclip'...${NC}"
    sudo -u postgres createdb -O supoclip supoclip 2>/dev/null || createdb -h localhost -U postgres supoclip 2>/dev/null || echo -e "  ${YELLOW}⚠  Could not create database — create manually: createdb -O supoclip supoclip${NC}"
fi

# Run init.sql
if [ -f init.sql ]; then
    echo -e "  ${YELLOW}⚡ Running init.sql...${NC}"
    PGPASSWORD=supoclip_password psql -h localhost -U supoclip -d supoclip -f init.sql 2>/dev/null && echo -e "  ${GREEN}✅${NC} Schema applied" || echo -e "  ${YELLOW}⚠  Schema may already exist (run manually: psql -U supoclip -d supoclip -f init.sql)${NC}"
fi

echo ""

# ── 4. Environment ────────────────────────────────────────────────
echo -e "${BOLD}Configuring environment...${NC}"

if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "  ${GREEN}✅${NC} Created .env from .env.example"
    echo -e "  ${YELLOW}⚠  Edit .env and add your API keys!${NC}"
else
    echo -e "  ${GREEN}✅${NC} .env already exists"
fi

echo ""

# ── 5. Backend setup ──────────────────────────────────────────────
echo -e "${BOLD}Setting up backend...${NC}"

cd "$SCRIPT_DIR/backend"

if [ ! -d .venv ]; then
    if command -v uv &>/dev/null; then
        uv venv .venv
        echo -e "  ${GREEN}✅${NC} Virtual env created (uv)"
    else
        python3 -m venv .venv
        echo -e "  ${GREEN}✅${NC} Virtual env created (python3 -m venv)"
    fi
else
    echo -e "  ${GREEN}✅${NC} Virtual env exists"
fi

# Activate
source .venv/bin/activate

if command -v uv &>/dev/null; then
    uv sync
else
    pip install --upgrade pip
    pip install -r requirements.txt 2>/dev/null || pip install -e ".[dev]" 2>/dev/null || {
        echo -e "  ${YELLOW}⚡ Installing core deps...${NC}"
        pip install fastapi uvicorn arq sqlalchemy asyncpg pydantic pydantic-ai pydantic-settings moviepy assemblyai openai python-dotenv yt-dlp google-api-python-client google-auth-oauthlib httpx redis
    }
fi

echo -e "  ${GREEN}✅${NC} Backend dependencies installed"
cd "$SCRIPT_DIR"

echo ""

# ── 6. Frontend setup ─────────────────────────────────────────────
echo -e "${BOLD}Setting up frontend...${NC}"

cd "$SCRIPT_DIR/frontend"

if [ ! -d node_modules ]; then
    npm install
    echo -e "  ${GREEN}✅${NC} Frontend dependencies installed"
else
    echo -e "  ${GREEN}✅${NC} node_modules exists"
fi

# Generate Prisma client
if [ -f prisma/schema.prisma ]; then
    npx prisma generate 2>/dev/null && echo -e "  ${GREEN}✅${NC} Prisma client generated" || echo -e "  ${YELLOW}⚠  Prisma generate skipped${NC}"
fi

cd "$SCRIPT_DIR"

echo ""

# ── 7. Default user ──────────────────────────────────────────────
echo -e "${BOLD}Setting up default user...${NC}"
if [ -f setup-default-user.sh ]; then
    bash setup-default-user.sh 2>/dev/null && echo -e "  ${GREEN}✅${NC} Default user created" || echo -e "  ${YELLOW}⚠  Default user setup skipped${NC}"
fi

echo ""

# ── 8. Done ──────────────────────────────────────────────────────
echo -e "${BOLD}╔═══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║       Installation complete!              ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}✅${NC} Prerequisites checked"
echo -e "  ${GREEN}✅${NC} Database configured"
echo -e "  ${GREEN}✅${NC} Environment configured"
echo -e "  ${GREEN}✅${NC} Backend ready"
echo -e "  ${GREEN}✅${NC} Frontend ready"
echo ""
echo -e "  ${BOLD}Next steps:${NC}"
echo -e "  1. Edit ${YELLOW}.env${NC} with your API keys:"
echo -e "     - ${BOLD}ASSEMBLY_AI_API_KEY${NC} (required for transcription)"
echo -e "     - ${BOLD}OPENAI_API_KEY${NC} or ${BOLD}GOOGLE_API_KEY${NC} or ${BOLD}ANTHROPIC_API_KEY${NC} (LLM)"
echo -e "  2. Run ${BOLD}./start-local.sh${NC} to start all services"
echo -e "  3. Open ${BOLD}http://localhost:3107${NC} in your browser"
echo ""
echo -e "  Default login: ${BOLD}admin@supoclip.local${NC} / ${BOLD}admin123${NC}"
echo ""
