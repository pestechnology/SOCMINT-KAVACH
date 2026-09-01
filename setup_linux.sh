#!/usr/bin/env bash
# ============================================================
# VERTEX — automated native setup for Linux.
#
# Runs every mechanical step from SETUP.md's Linux section: system packages,
# venv, Python deps, the agentic-browser Chromium binary, face models,
# Blackbird (clone + wrapper + site list), the frontend's npm install, and
# DB + admin bootstrap. It does NOT touch your `.env` secrets beyond copying
# the template if missing — you still fill in real keys yourself.
#
# Usage:
#   ./setup_linux.sh              # full setup, stops right before you'd run the servers
#   ./setup_linux.sh --skip-sudo  # skip the apt/dnf system-package step (already installed,
#                                 # or you don't have sudo — e.g. inside a container)
#   ./setup_linux.sh --skip-browser  # skip the Chromium download for the agentic browser
#                                    # (large; only needed if you'll actually use it)
#
# Safe to re-run: every step checks whether its work is already done first.
# Matches SETUP.md exactly — if you change one, change the other.
# ============================================================
set -uo pipefail

SKIP_SUDO=false
SKIP_BROWSER=false
for arg in "$@"; do
  case "$arg" in
    --skip-sudo) SKIP_SUDO=true ;;
    --skip-browser) SKIP_BROWSER=true ;;
    *) echo "Unknown flag: $arg (known: --skip-sudo, --skip-browser)"; exit 1 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

BOLD='\033[1m'; GREEN='\033[32m'; YELLOW='\033[33m'; RED='\033[31m'; RESET='\033[0m'
step()  { echo -e "\n${BOLD}==> $*${RESET}"; }
ok()    { echo -e "${GREEN}  ok:${RESET} $*"; }
warn()  { echo -e "${YELLOW}  warn:${RESET} $*"; }
fail()  { echo -e "${RED}  FAILED:${RESET} $*"; exit 1; }

# ---- 0. Sanity: run this from the repo root ----
[ -f "requirements.txt" ] && [ -d "backend" ] || fail "run this from the repo root (requirements.txt / backend/ not found here: $REPO_ROOT)"

# ---- 1. System packages ----
if [ "$SKIP_SUDO" = true ]; then
  step "1/9 System packages — skipped (--skip-sudo)"
else
  step "1/9 System packages"
  if command -v apt >/dev/null 2>&1; then
    sudo apt update && sudo apt install -y python3 python3-venv python3-dev build-essential git curl \
      || warn "apt install had a non-zero exit; continuing (packages may already be present)"
    if ! command -v node >/dev/null 2>&1; then
      warn "Node not found — installing via NodeSource (Node 20.x)"
      curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - \
        && sudo apt install -y nodejs \
        || warn "Node install failed — install it yourself (nvm, or your distro's package) before step 8"
    fi
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-devel gcc gcc-c++ git nodejs curl \
      || warn "dnf install had a non-zero exit; continuing (packages may already be present)"
  else
    warn "Neither apt nor dnf found — install python3/python3-venv/python3-dev/build-essential/git/nodejs yourself, then re-run with --skip-sudo"
  fi
  ok "system packages"
fi

command -v python3 >/dev/null 2>&1 || fail "python3 not found on PATH — install it (see step 1) then re-run"
command -v git >/dev/null 2>&1 || fail "git not found on PATH — install it (see step 1) then re-run"

# ---- 2. Secrets ----
step "2/9 .env"
if [ -f ".env" ]; then
  ok ".env already exists — leaving it alone"
else
  cp .env.example .env
  ok "copied .env.example -> .env"
  warn "you MUST edit .env and fill in real keys before running the backend — see GET_API_KEYS.md"
  echo "     (generate a JWT secret now if you want:  python3 -c \"import secrets; print(secrets.token_hex(32))\")"
fi

# ---- 3. Python venv + deps ----
step "3/9 Python venv + backend dependencies"
if [ -d "venv" ]; then
  ok "venv/ already exists — reusing it (delete it first if it was created on a different machine/user)"
else
  python3 -m venv venv || fail "python3 -m venv venv"
  ok "created venv/"
fi
# shellcheck disable=SC1091
source venv/bin/activate || fail "could not activate venv"
pip install --upgrade pip -q || fail "pip upgrade"
pip install -r requirements.txt || fail "pip install -r requirements.txt (see the error above — a missing system package from step 1 is the usual cause)"
pip install -q pytest pytest-asyncio || fail "pip install pytest pytest-asyncio"
ok "backend dependencies installed"

# ---- 4. Agentic browser (Chromium) ----
if [ "$SKIP_BROWSER" = true ]; then
  step "4/9 Agentic browser Chromium — skipped (--skip-browser)"
else
  step "4/9 Agentic browser Chromium (large download; skip with --skip-browser if you don't need it)"
  playwright install --with-deps chromium || warn "playwright install failed — agentic browser will stay disabled, everything else still works"
  python -m patchright install chromium || warn "patchright install failed — agentic browser will stay disabled, everything else still works"
  ok "chromium"
fi

# ---- 5. Face-matching models ----
step "5/9 Face-matching models (~37 MB)"
python backend/scripts/download_face_models.py || warn "face model download failed — face matching will be disabled, every other signal still works"

# ---- 6. ignorant ----
step "6/9 ignorant (phone registration checker)"
pip install -q ignorant || warn "ignorant install failed — that one phone-lookup source will return [] instead of failing the pipeline"

# ---- 7. Blackbird ----
step "7/9 Blackbird (username/email enumerator)"
if [ -d "tools/blackbird" ]; then
  ok "tools/blackbird already cloned — reusing it"
else
  git clone https://github.com/p1ngul1n0/blackbird tools/blackbird || fail "git clone blackbird"
fi
pip install -r tools/blackbird/requirements.txt || warn "blackbird requirements install failed"
# Deliberately a SEPARATE pip command from the one above — see SETUP.md for why
# (Blackbird pins older aiohttp/multidict/reportlab than maigret needs).
pip install "aiohttp>=3.12.14,<4.0.0" "multidict>=6.6.3,<7.0.0" "reportlab>=4.4.3,<5.0.0" \
  || warn "version-conflict fixup failed — re-run manually if maigret/blackbird misbehave"

cat > venv/bin/blackbird <<EOF
#!/usr/bin/env bash
exec "$REPO_ROOT/venv/bin/python" "$REPO_ROOT/tools/blackbird/blackbird.py" "\$@"
EOF
chmod +x venv/bin/blackbird
ok "venv/bin/blackbird wrapper"

if [ -f "tools/blackbird/data/wmn-data.json" ]; then
  ok "Blackbird site list already downloaded"
else
  echo "  downloading Blackbird's site list (one-time, triggered by a real run)..."
  (cd tools/blackbird && python blackbird.py -u torvalds >/dev/null 2>&1) \
    && ok "site list downloaded" \
    || warn "site-list download failed (network?) — Blackbird will retry on its first real use"
fi

if grep -q "^BLACKBIRD_PATH=" .env 2>/dev/null; then
  ok "BLACKBIRD_PATH already set in .env"
else
  echo "BLACKBIRD_PATH=$REPO_ROOT/tools/blackbird" >> .env
  ok "added BLACKBIRD_PATH=$REPO_ROOT/tools/blackbird to .env"
fi

# ---- 8. Frontend ----
step "8/9 Frontend (Next.js)"
if command -v npm >/dev/null 2>&1; then
  (cd frontend && npm install) || fail "npm install"
  if [ -f "frontend/.env.local" ]; then
    ok "frontend/.env.local already exists"
  else
    echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > frontend/.env.local
    ok "created frontend/.env.local"
  fi
else
  warn "npm not found — install Node 18+ (see step 1) then run: cd frontend && npm install"
fi

# ---- 9. Database + admin user ----
step "9/9 Database + admin user"
python -m backend.database || fail "python -m backend.database"
python -m scripts.create_admin || warn "create_admin failed — it may already exist; log in with admin / vertex2026"
ok "database ready"

echo
echo -e "${BOLD}${GREEN}Setup complete.${RESET}"
echo "Still to do by hand:"
echo "  1. Fill real keys into .env (see GET_API_KEYS.md) — or set DATA_MODE=mock for a"
echo "     zero-key offline demo."
echo "  2. Start the backend:   source venv/bin/activate && uvicorn backend.main:app --reload --port 8000"
echo "  3. Start the frontend:  cd frontend && npm run dev"
echo "  4. Open http://localhost:3000 — log in with admin / vertex2026 (change this before real use)."
echo "  5. Optional smoke test: pytest tests/ -q"
