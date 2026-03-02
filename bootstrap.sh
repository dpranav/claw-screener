#!/usr/bin/env bash
set -euo pipefail

# Bootstrap OpenClaw + dual Telegram agents + skills + ClawMetry
# Intended for Ubuntu VMs (e.g., Azure). Run from repository root.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
CONTAINER_NAME="${CONTAINER_NAME:-openclaw-screener}"
PRESALES_ACCOUNT_ID="${PRESALES_ACCOUNT_ID:-presales}"
PRESALES_AGENT_NAME="${PRESALES_AGENT_NAME:-Pre Sales Specialist}"
PRESALES_AGENT_ID="${PRESALES_AGENT_ID:-pre-sales-specialist}"
MAIN_ACCOUNT_ID="${MAIN_ACCOUNT_ID:-default}"
MAIN_AGENT_ID="${MAIN_AGENT_ID:-main}"
OPENCLAW_TIMEOUT_SECONDS="${OPENCLAW_TIMEOUT_SECONDS:-180}"

log() { printf "\n[bootstrap] %s\n" "$*"; }
warn() { printf "\n[bootstrap][warn] %s\n" "$*" >&2; }
die() { printf "\n[bootstrap][error] %s\n" "$*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

ensure_docker() {
  if command -v docker >/dev/null 2>&1; then
    log "Docker already installed."
    return
  fi

  log "Installing Docker..."
  curl -fsSL https://get.docker.com | sh

  # shellcheck disable=SC2015
  command -v sudo >/dev/null 2>&1 && sudo usermod -aG docker "$USER" || true

  warn "Docker installed. If docker commands fail due to permissions, re-login and re-run this script."
}

ensure_compose() {
  if docker compose version >/dev/null 2>&1; then
    log "Docker Compose plugin available."
    return
  fi
  die "Docker Compose plugin is not available. Install Docker Compose v2."
}

load_env_file() {
  [[ -f .env ]] || die ".env not found in $PROJECT_DIR. Create it first."
  # Export .env for this script so we can validate required variables.
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
}

validate_required_env() {
  local missing=()

  [[ -n "${ANTHROPIC_API_KEY:-}" || -n "${OPENAI_API_KEY:-}" || -n "${XAI_API_KEY:-}" ]] || \
    missing+=("One LLM key: ANTHROPIC_API_KEY or OPENAI_API_KEY or XAI_API_KEY")
  [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] || missing+=("TELEGRAM_BOT_TOKEN (main bot)")
  [[ -n "${PRESALES_TELEGRAM_BOT_TOKEN:-}" ]] || missing+=("PRESALES_TELEGRAM_BOT_TOKEN (pre-sales bot)")
  [[ -n "${GEMINI_API_KEY:-}" ]] || missing+=("GEMINI_API_KEY (for nano-banana-pro)")

  if ((${#missing[@]} > 0)); then
    printf "\n[bootstrap][error] Missing required values in .env:\n" >&2
    for item in "${missing[@]}"; do
      printf "  - %s\n" "$item" >&2
    done
    cat <<'EOF' >&2

Add these to .env, then re-run:
  TELEGRAM_BOT_TOKEN=...
  PRESALES_TELEGRAM_BOT_TOKEN=...
  GEMINI_API_KEY=...
  ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY / XAI_API_KEY
EOF
    exit 1
  fi
}

compose_up() {
  log "Building and starting containers..."
  docker compose -f "$COMPOSE_FILE" up -d --build
}

wait_for_gateway() {
  log "Waiting for OpenClaw gateway..."
  local attempts=40
  local i
  for ((i=1; i<=attempts; i++)); do
    if curl -sSf "http://localhost:${OPENCLAW_PORT:-18789}/" >/dev/null 2>&1; then
      log "Gateway is up."
      return
    fi
    sleep 3
  done
  die "Gateway did not become ready in time."
}

oc() {
  docker exec "$CONTAINER_NAME" openclaw "$@"
}

configure_timeouts() {
  log "Setting agent timeout (${OPENCLAW_TIMEOUT_SECONDS}s)..."
  oc config set agents.defaults.timeoutSeconds "$OPENCLAW_TIMEOUT_SECONDS" --strict-json >/dev/null
}

install_skills() {
  log "Installing managed skills from ClawHub..."
  docker exec "$CONTAINER_NAME" npx clawhub --workdir /root/.openclaw --dir skills install powerpoint-pptx >/dev/null
  docker exec "$CONTAINER_NAME" npx clawhub --workdir /root/.openclaw --dir skills install office-document-specialist-suite >/dev/null
}

ensure_presales_agent() {
  log "Ensuring isolated pre-sales agent exists..."
  if oc agents list --json | grep -q "\"id\": \"${PRESALES_AGENT_ID}\""; then
    log "Agent ${PRESALES_AGENT_ID} already exists."
  else
    oc agents add "$PRESALES_AGENT_NAME" \
      --workspace "/root/.openclaw/workspace-pre-sales" \
      --non-interactive >/dev/null
  fi
}

configure_agent_identity_and_prompt() {
  log "Applying pre-sales workspace instructions..."
  docker exec "$CONTAINER_NAME" python3 - <<'PY'
from pathlib import Path

identity = Path("/root/.openclaw/workspace-pre-sales/IDENTITY.md")
identity.write_text(
    """# IDENTITY.md

- **Name:** Pre Sales Specialist
- **Creature:** Proposal-focused AI consultant
- **Vibe:** Structured, concise, business-friendly
- **Emoji:** 📊

## Role
You are a pre-sales expert who turns requirements into client-ready materials: presentations, project charters, and statements of work (SOW).
""",
    encoding="utf-8",
)

agents = Path("/root/.openclaw/workspace-pre-sales/AGENTS.md")
agents.write_text(
    """# AGENTS.md - Pre Sales Specialist

## Mission
Create client-facing pre-sales deliverables from user instructions:
- Presentation decks
- Project charters
- Statements of Work (SOW)

## Operating Style
- Clarify objective, audience, timeline, scope, and assumptions first.
- Produce outlines before full deliverables for broad requests.
- Keep language executive-friendly and concrete.
- Surface assumptions and risks explicitly.

## Preferred Skills
Use these skills first whenever relevant:
1. `PowerPoint PPTX` (slug: `powerpoint-pptx`)
2. `office-document-specialist-suite`
3. `nano-banana-pro`

## Deliverable Standards
### Presentations
- Include: title slide, problem, goals, approach, timeline, scope, deliverables, commercials (if provided), next steps.

### Project Charter
- Include: purpose, objectives, scope in/out, stakeholders, milestones, governance, risks, assumptions, success criteria.

### SOW
- Include: background, scope, deliverables, acceptance criteria, timeline, dependencies, roles/responsibilities, change control, commercial terms placeholders.
""",
    encoding="utf-8",
)
PY

  oc agents set-identity \
    --agent "$PRESALES_AGENT_ID" \
    --name "Pre Sales Specialist" \
    --theme "Structured, concise, business-friendly" \
    --emoji "📊" >/dev/null
}

configure_telegram_accounts_and_routing() {
  log "Configuring Telegram accounts..."

  oc channels add \
    --channel telegram \
    --account "$MAIN_ACCOUNT_ID" \
    --name "Main Bot" \
    --token "$TELEGRAM_BOT_TOKEN" >/dev/null

  oc channels add \
    --channel telegram \
    --account "$PRESALES_ACCOUNT_ID" \
    --name "Pre Sales Specialist Bot" \
    --token "$PRESALES_TELEGRAM_BOT_TOKEN" >/dev/null

  log "Configuring account-to-agent bindings..."
  oc config set bindings \
    "[{agentId:'${MAIN_AGENT_ID}',match:{channel:'telegram',accountId:'${MAIN_ACCOUNT_ID}'}},{agentId:'${PRESALES_AGENT_ID}',match:{channel:'telegram',accountId:'${PRESALES_ACCOUNT_ID}'}}]" \
    --strict-json >/dev/null
}

restart_openclaw() {
  log "Restarting OpenClaw container to apply settings..."
  docker compose -f "$COMPOSE_FILE" restart
  sleep 8
}

start_clawmetry() {
  log "Starting ClawMetry on port 8900..."
  # Start detached from exec session; safe to re-run.
  docker exec "$CONTAINER_NAME" pkill -f "^clawmetry .*--port 8900" >/dev/null 2>&1 || true
  docker exec -d "$CONTAINER_NAME" clawmetry \
    --host 0.0.0.0 \
    --port 8900 \
    --data-dir /root/.openclaw \
    --no-debug >/dev/null 2>&1 || true
}

verify() {
  log "Verifying channels and bindings..."
  oc channels status --probe || true
  oc agents list --bindings || true
  oc skills check | sed -n '1,80p' || true

  log "Health endpoints:"
  curl -s -o /dev/null -w "  OpenClaw: HTTP %{http_code}\n" "http://localhost:${OPENCLAW_PORT:-18789}/" || true
  curl -s -o /dev/null -w "  ClawMetry: HTTP %{http_code}\n" "http://localhost:8900/" || true
}

summary() {
  cat <<EOF

[bootstrap] Completed.

OpenClaw UI:
  http://<VM_IP>:${OPENCLAW_PORT:-18789}

ClawMetry UI:
  http://<VM_IP>:8900

Telegram routing:
  accountId=${MAIN_ACCOUNT_ID}     -> agent=${MAIN_AGENT_ID}
  accountId=${PRESALES_ACCOUNT_ID} -> agent=${PRESALES_AGENT_ID}

Next recommended step:
  Restrict public access with NSG/firewall and use SSH tunnel or reverse proxy + TLS.
EOF
}

main() {
  require_cmd curl
  ensure_docker
  require_cmd docker
  ensure_compose
  load_env_file
  validate_required_env
  compose_up
  wait_for_gateway
  configure_timeouts
  install_skills
  ensure_presales_agent
  configure_agent_identity_and_prompt
  configure_telegram_accounts_and_routing
  restart_openclaw
  start_clawmetry
  verify
  summary
}

main "$@"
