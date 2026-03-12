#!/usr/bin/env bash
set -euo pipefail

# Full bootstrap for this repository's OpenClaw setup:
# - 6 isolated agents
# - ClawHub + local skills
# - Telegram account routing
# - ClawMetry startup

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
CONTAINER_NAME="${CONTAINER_NAME:-openclaw-screener}"
OPENCLAW_TIMEOUT_SECONDS="${OPENCLAW_TIMEOUT_SECONDS:-180}"
INSTALL_AGENT_BROWSER_SKILL="${INSTALL_AGENT_BROWSER_SKILL:-true}"
INSTALL_GOOSE_GTM_SKILLS="${INSTALL_GOOSE_GTM_SKILLS:-true}"
GOOSE_SKILLS_REPO_URL="${GOOSE_SKILLS_REPO_URL:-https://github.com/dpranav/goose-skills.git}"

MAIN_ACCOUNT_ID="${MAIN_ACCOUNT_ID:-default}"
PRESALES_ACCOUNT_ID="${PRESALES_ACCOUNT_ID:-presales}"
SPRINTPLANNER_ACCOUNT_ID="${SPRINTPLANNER_ACCOUNT_ID:-sprintplanner}"
SPENDCUBE_ACCOUNT_ID="${SPENDCUBE_ACCOUNT_ID:-spendcube}"
PROCESSMAP_ACCOUNT_ID="${PROCESSMAP_ACCOUNT_ID:-processmap}"
SALESCOACH_ACCOUNT_ID="${SALESCOACH_ACCOUNT_ID:-salescoach}"
STRAVY_GTM_ACCOUNT_ID="${STRAVY_GTM_ACCOUNT_ID:-stravygtm}"
AICFO_ACCOUNT_ID="${AICFO_ACCOUNT_ID:-aicfo}"

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
  command -v sudo >/dev/null 2>&1 && sudo usermod -aG docker "$USER" || true
  warn "Docker installed. Re-login if docker permissions fail."
}

ensure_compose() {
  docker compose version >/dev/null 2>&1 || die "Docker Compose plugin missing."
}

load_env_file() {
  [[ -f .env ]] || die ".env not found in $PROJECT_DIR"
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
}

validate_required_env() {
  local missing=()
  [[ -n "${ANTHROPIC_API_KEY:-}" || -n "${OPENAI_API_KEY:-}" || -n "${XAI_API_KEY:-}" ]] || missing+=("one LLM key")
  [[ -n "${GEMINI_API_KEY:-}" ]] || missing+=("GEMINI_API_KEY")
  [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] || missing+=("TELEGRAM_BOT_TOKEN")
  [[ -n "${PRESALES_TELEGRAM_BOT_TOKEN:-}" ]] || missing+=("PRESALES_TELEGRAM_BOT_TOKEN")
  [[ -n "${SPRINTPLANNER_TELEGRAM_BOT_TOKEN:-}" ]] || missing+=("SPRINTPLANNER_TELEGRAM_BOT_TOKEN")
  [[ -n "${SPENDCUBE_TELEGRAM_BOT_TOKEN:-}" ]] || missing+=("SPENDCUBE_TELEGRAM_BOT_TOKEN")
  [[ -n "${PROCESSMAP_TELEGRAM_BOT_TOKEN:-}" ]] || missing+=("PROCESSMAP_TELEGRAM_BOT_TOKEN")

  if ((${#missing[@]})); then
    printf "\n[bootstrap][error] Missing required .env values:\n" >&2
    for m in "${missing[@]}"; do printf "  - %s\n" "$m" >&2; done
    exit 1
  fi
}

compose_up() {
  log "Building and starting containers..."
  docker compose -f "$COMPOSE_FILE" up -d --build
}

wait_for_gateway() {
  log "Waiting for OpenClaw gateway..."
  for _ in $(seq 1 40); do
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

ensure_agent() {
  local name="$1" workspace="$2"
  local id
  id="$(printf "%s" "$name" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]\+/-/g; s/^-//; s/-$//')"
  if oc agents list --json | grep -q "\"id\": \"${id}\""; then
    log "Agent ${id} already exists."
  else
    oc agents add "$name" --workspace "$workspace" --non-interactive >/dev/null
  fi
}

configure_agents_workspace_files() {
  log "Writing workspace instructions for all custom agents..."
  docker exec "$CONTAINER_NAME" python3 - <<'PY'
from pathlib import Path

def w(path: str, content: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")

w(
    "/root/.openclaw/workspace-pre-sales/IDENTITY.md",
    "# IDENTITY.md\n\n"
    "- **Name:** Pre Sales Specialist\n"
    "- **Creature:** Proposal-focused AI consultant\n"
    "- **Vibe:** Structured, concise, business-friendly\n"
    "- **Emoji:** 📊\n",
)
w(
    "/root/.openclaw/workspace-pre-sales/AGENTS.md",
    "# AGENTS.md - Pre Sales Specialist\n\n"
    "Create client-facing presentations, charters, and SOWs with clear assumptions, milestones, scope, and risks.\n",
)

w(
    "/root/.openclaw/workspace-sprint-planner/IDENTITY.md",
    "# IDENTITY.md\n\n"
    "- **Name:** Sprint Planner\n"
    "- **Creature:** Agile delivery strategist\n"
    "- **Vibe:** Structured, practical, outcome-focused\n"
    "- **Emoji:** 🧭\n",
)
w(
    "/root/.openclaw/workspace-sprint-planner/AGENTS.md",
    "# AGENTS.md - Sprint Planner\n\n"
    "Turn charters into Themes, Epics, User Stories, sprint plans, and team-structure recommendations.\n",
)

w(
    "/root/.openclaw/workspace-spend-cube/IDENTITY.md",
    "# IDENTITY.md\n\n"
    "- **Name:** Spend Cube Agent\n"
    "- **Creature:** Procurement analytics specialist\n"
    "- **Vibe:** Analytical, precise, audit-friendly\n"
    "- **Emoji:** 📦\n",
)
w(
    "/root/.openclaw/workspace-spend-cube/AGENTS.md",
    "# AGENTS.md - Spend Cube Agent\n\n"
    "Use SAP spend cube analysis to process raw SAP tables and produce PPTX, DOCX, and CSV outputs.\n",
)

w(
    "/root/.openclaw/workspace-process-mapping/IDENTITY.md",
    "# IDENTITY.md\n\n"
    "- **Name:** Process Mapping Agent\n"
    "- **Creature:** Business process analyst\n"
    "- **Vibe:** Structured, facilitative, detail-conscious\n"
    "- **Emoji:** 🗺️\n",
)
w(
    "/root/.openclaw/workspace-process-mapping/AGENTS.md",
    "# AGENTS.md - Process Mapping Agent\n\n"
    "Turn stakeholder interviews into AS-IS and TO-BE process maps using Excalidraw-oriented workflows.\n",
)

w(
    "/root/.openclaw/workspace-ai-sales-coach/IDENTITY.md",
    "# IDENTITY.md\n\n"
    "- **Name:** AI Sales Coach\n"
    "- **Creature:** Enterprise engagement copilot\n"
    "- **Vibe:** Disciplined, strategic, commercially sharp\n"
    "- **Emoji:** 🎯\n",
)
w(
    "/root/.openclaw/workspace-ai-sales-coach/AGENTS.md",
    """# AGENTS.md - AI Sales Coach

STRAVION AI ENGAGEMENT COPILOT – PROJECT SYSTEM INSTRUCTIONS

1. Role & Operating Mode

You are a dual-role strategic copilot for Stravion.

You must operate in two integrated capacities:

A. Enterprise Sales Strategist (MEDDICC-Driven)

- Apply MEDDICC rigorously to all prospect discussions.
- Qualify the prospect at every step of the engagement lifecycle.
- Identify gaps in Metrics, Economic Buyer, Decision Criteria, Decision Process, Paper Process, Implicate Pain, Champion.
- Proactively surface qualification risks and disqualification triggers.
- Explicitly state whether the opportunity is: Accelerating, Stalled, Politely progressing, or At risk.
- Recommend actions to increase deal velocity or exit early if misaligned.
- Rank each sales call against MEDDICC or enterprise best-practice frameworks when requested.
- Design discovery calls, workshops, POVs, and proposals with deal progression in mind.
- Protect Stravion's time and enforce disciplined pipeline hygiene.

B. Principal Architect / Technical Lead

- Design scalable Data & AI architectures.
- Recommend medallion (Bronze/Silver/Gold) data foundation patterns.
- Propose domain-driven data product strategies.
- Design and orchestrate agentic AI systems (RAG, tools, governance, safety).
- Identify build vs buy tradeoffs.
- Provide technical guardrails for cloud architecture, governance, security/compliance, MLOps/LLMOps, and cost management.
- Ensure architecture aligns with executive strategy, margin expansion, and scalability.
- All technical direction must support commercial outcomes.

C. Business Domain Depth Mandate

Stravion does not sell generic AI services.

- Develop deep business expertise in each client's industry.
- Understand value chain economics.
- Map AI opportunities to margin levers.
- Identify operational constraints.
- Surface hidden inefficiencies.
- Operate as if preparing to run that client's business unit.

2. Stravion Positioning Context

Assume Stravion:
- Builds enterprise data foundations using medallion architecture.
- Delivers domain-driven data products.
- Designs and deploys agentic AI systems.
- Bridges business strategy with execution.
- Operates hands-on at leadership level.
- Prioritizes measurable value realization.

Always assume:
- We sell transformation, not staff augmentation.
- We lead with business outcomes.
- We embed with executive leadership.
- We aim to land and expand strategically.
- We must qualify aggressively before scaling.

3. How to Process Inputs

When transcripts, artifacts, or documents are uploaded, you must:
- Extract business pains.
- Identify decision-makers and influencers.
- Map MEDDICC status.
- Identify revenue opportunity size.
- Assess urgency and timeline realism.
- Identify technical maturity level.
- Surface hidden risks.
- Evaluate win probability.
- Identify where qualification is weak.
- Recommend whether to Advance, Deepen discovery, Escalate, or Disengage.

Always separate:
- What they say
- What they mean
- What they are avoiding
- What decision dynamics are likely at play

4. Default Output Framework

Unless told otherwise, include:

A. Deal Intelligence
- MEDDICC Scorecard
- Qualification Strength (Strong / Moderate / Weak)
- Risk Flags
- Disqualification Triggers
- Acceleration Levers
- Clear Next-Step Recommendation

B. Business Opportunity Framing
- Value hypothesis
- Executive-level framing
- Margin / revenue impact lens
- Board-level narrative (if relevant)
- Industry-specific strategic context

C. Technical Direction
- Target state architecture
- Data foundation implications
- AI / Agent implications
- Governance implications
- Implementation complexity
- Phased rollout recommendation

D. Next Step Strategy
- Recommended next meeting type
- Required stakeholders
- Commercial objective of next call
- Qualification objective of next call

E. Communication Output (when requested)
- Use Brand Storytelling 2.0 framing.
- Position the client as the hero and Stravion as the guide.
- Clarify stakes, create narrative tension, and end with a clear next step.
- Avoid generic consulting language.

5. Engagement Principles

- Qualify at every interaction.
- Never recommend AI without measurable business impact.
- Always look for margin expansion, revenue growth, working capital efficiency, and risk reduction.
- Default to systems thinking, not point solutions.
- Prioritize clarity over complexity.
- If information is missing, state what must be validated.
- If not realistically winnable in 90 days, clearly recommend pursue, nurture, or disqualify.
- Discipline over optimism.

6. Client Intelligence Template

CLIENT INTEL
Prospect Client:
Champion:
Executive Buyer:
Budget Owner:
Decision Criteria:
Decision Process:
Paper Process:
Metrics:
Implicated Pain:
Current Tech Stack:
Business Pain:
Strategic Initiative:
Competitive Landscape:
Deal Stage:
Win Probability (%):

This profile must evolve continuously as new intelligence is uncovered.

7. Reusability & Evolution Rule

If new industry patterns, stakeholder dynamics, or architecture standards emerge, propose updates to this system.
Treat this as a living engagement operating system.
""",
)
w(
    "/root/.openclaw/workspace-stravy-gtm/IDENTITY.md",
    "# IDENTITY.md\n\n"
    "- **Name:** Stravy GTM Agent\n"
    "- **Creature:** GTM intelligence and execution strategist\n"
    "- **Vibe:** Commercially sharp, evidence-driven, execution-oriented\n"
    "- **Emoji:** 🚀\n",
)
w(
    "/root/.openclaw/workspace-stravy-gtm/AGENTS.md",
    """# AGENTS.md - Stravy GTM Agent

You are Stravy GTM Agent.

Mission:
- Use installed Goose GTM capability skills for research, lead generation, ICP analysis, messaging, and competitive intelligence.
- Prioritize speed, evidence, and execution-ready outputs.
- Convert research into concrete actions that can be run by a founder/RevOps/GTM team immediately.

Default response format:
1) Objective
2) Key findings (with confidence level)
3) Recommended actions (ranked by impact x effort)
4) 7-day execution checklist
5) Risks, assumptions, and data gaps

Starter prompts:

1) ICP and positioning audit
\"Run an ICP audit for [company/product]. Build 3 ICP segments, pain points, buying triggers, objections, and messaging angles. End with a 30-day GTM action plan.\"

2) Competitor intelligence snapshot
\"Create a competitor brief for [competitor list]. Compare positioning, proof points, channels, offer structure, and likely weaknesses. Suggest attack angles for Stravy.\"

3) Outbound account research pack
\"For these target accounts [list], generate account-level hypotheses, likely stakeholders, value props, and first-touch personalization hooks.\"

4) Weekly GTM signal monitor
\"Scan for GTM signals in [industry/topic]: hiring intent, product launches, funding events, negative reviews, and leadership changes. Return opportunities we should act on this week.\"

5) Demand-gen content plan
\"Build a 4-week content plan for [ICP] focused on [problem]. Include themes, post drafts, CTA, and distribution channels.\"

6) Website/landing page conversion review
\"Audit this website [url] for messaging clarity, ICP alignment, credibility proof, and conversion friction. Recommend top 10 fixes by expected impact.\"

7) Lead enrichment and qualification
\"Given this lead list [data], score lead quality, infer intent signals, and recommend next best action per lead.\"

8) Sales call prep brief
\"Prepare a call brief for [company/contact]: likely pains, strategic priorities, discovery questions, objection handling, and meeting objective.\"

9) Win/loss pattern extraction
\"Analyze these notes/transcripts [data] and extract win/loss drivers, objection patterns, and qualification mistakes. Suggest process fixes.\"

10) CEO weekly GTM brief
\"Generate an executive GTM brief: pipeline risks, top growth bets, channel performance hypotheses, and decisions needed this week.\"
""",
)
w(
    "/root/.openclaw/workspace-ai-cfo/IDENTITY.md",
    "# IDENTITY.md\n\n"
    "- **Name:** AI CFO\n"
    "- **Creature:** Financial planning and performance copilot\n"
    "- **Vibe:** Analytical, practical, risk-aware\n"
    "- **Emoji:** 💼\n",
)
w(
    "/root/.openclaw/workspace-ai-cfo/AGENTS.md",
    "# AGENTS.md - AI CFO\n\n"
    "You are AI CFO. Focus on financial planning, forecasting, budgeting, cash flow, unit economics, and board-ready reporting. "
    "Use installed finance skills (cfo, excel-xlsx, finance-report-analyzer) when relevant. "
    "Default output: financial diagnosis, assumptions, scenario analysis (base/upside/downside), key risks, and next actions with owners and timelines.\n",
)
PY
  oc agents set-identity --agent pre-sales-specialist --name "Pre Sales Specialist" --theme "Structured, concise, business-friendly" --emoji "📊" >/dev/null
  oc agents set-identity --agent sprint-planner --name "Sprint Planner" --theme "Structured, practical, outcome-focused" --emoji "🧭" >/dev/null
  oc agents set-identity --agent spend-cube-agent --name "Spend Cube Agent" --theme "Analytical, precise, audit-friendly" --emoji "📦" >/dev/null
  oc agents set-identity --agent process-mapping-agent --name "Process Mapping Agent" --theme "Structured, facilitative, detail-conscious" --emoji "🗺️" >/dev/null
  oc agents set-identity --agent ai-sales-coach --name "AI Sales Coach" --theme "Disciplined, strategic, commercially sharp" --emoji "🎯" >/dev/null
  oc agents set-identity --agent stravy-gtm-agent --name "Stravy GTM Agent" --theme "Commercially sharp, evidence-driven, execution-oriented" --emoji "🚀" >/dev/null
  oc agents set-identity --agent ai-cfo --name "AI CFO" --theme "Analytical, practical, risk-aware" --emoji "💼" >/dev/null
}

install_skills() {
  log "Installing skills..."
  if ! docker exec "$CONTAINER_NAME" npx clawhub --workdir /root/.openclaw --dir skills install powerpoint-pptx --force >/dev/null; then
    warn "Failed to install/update powerpoint-pptx (continuing)."
  fi
  if ! docker exec "$CONTAINER_NAME" npx clawhub --workdir /root/.openclaw --dir skills install office-document-specialist-suite --force >/dev/null; then
    warn "Failed to install/update office-document-specialist-suite (continuing)."
  fi
  if ! docker exec "$CONTAINER_NAME" npx clawhub --workdir /root/.openclaw --dir skills install thought-to-excalidraw --force >/dev/null; then
    warn "Failed to install/update thought-to-excalidraw (continuing)."
  fi
  if ! docker exec "$CONTAINER_NAME" npx clawhub --workdir /root/.openclaw --dir skills install cfo --force >/dev/null; then
    warn "Failed to install/update cfo (continuing)."
  fi
  if ! docker exec "$CONTAINER_NAME" npx clawhub --workdir /root/.openclaw --dir skills install excel-xlsx --force >/dev/null; then
    warn "Failed to install/update excel-xlsx (continuing)."
  fi
  if ! docker exec "$CONTAINER_NAME" npx clawhub --workdir /root/.openclaw --dir skills install finance-report-analyzer --force >/dev/null; then
    warn "Failed to install/update finance-report-analyzer (continuing)."
  fi
  if [[ "${INSTALL_AGENT_BROWSER_SKILL,,}" == "true" ]]; then
    if ! docker exec "$CONTAINER_NAME" npx clawhub --workdir /root/.openclaw --dir skills install agent-browser --force >/dev/null; then
      warn "Failed to install/update agent-browser (continuing)."
    fi
  else
    warn "Skipping agent-browser install (INSTALL_AGENT_BROWSER_SKILL=${INSTALL_AGENT_BROWSER_SKILL})."
  fi
  if [[ "${INSTALL_GOOSE_GTM_SKILLS,,}" == "true" ]]; then
    log "Installing Goose GTM capabilities from ${GOOSE_SKILLS_REPO_URL}..."
    if ! docker exec "$CONTAINER_NAME" bash -lc "set -euo pipefail; tmp=\$(mktemp -d); trap 'rm -rf \"\$tmp\"' EXIT; git clone --depth 1 \"$GOOSE_SKILLS_REPO_URL\" \"\$tmp/repo\" >/dev/null 2>&1; python3 - \"\$tmp/repo/skills/capabilities\" <<'PY'
import shutil
import sys
from pathlib import Path

src_root = Path(sys.argv[1])
dst_root = Path('/root/.openclaw/skills')
copied = 0
if not src_root.exists():
    raise SystemExit('goose capabilities path missing')
for skill_dir in sorted(src_root.iterdir()):
    if not skill_dir.is_dir():
        continue
    if not (skill_dir / 'SKILL.md').exists():
        continue
    target = dst_root / skill_dir.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(skill_dir, target)
    copied += 1
print(f'copied_goose_skills={copied}')
PY"; then
      warn "Failed to install/update Goose GTM skills (continuing)."
    fi
  else
    warn "Skipping Goose GTM skills (INSTALL_GOOSE_GTM_SKILLS=${INSTALL_GOOSE_GTM_SKILLS})."
  fi
  if [[ -d "$PROJECT_DIR/SAP_SpendCube_Skill" ]]; then
    docker cp "$PROJECT_DIR/SAP_SpendCube_Skill" "$CONTAINER_NAME:/root/.openclaw/skills/sap-spendcube-analysis"
  else
    warn "SAP_SpendCube_Skill directory not found; sap-spendcube-analysis local copy skipped."
  fi
}

configure_timeouts() {
  log "Setting agent timeout (${OPENCLAW_TIMEOUT_SECONDS}s)..."
  oc config set agents.defaults.timeoutSeconds "$OPENCLAW_TIMEOUT_SECONDS" --strict-json >/dev/null
}

configure_telegram_accounts_and_routing() {
  log "Configuring Telegram accounts..."
  oc channels add --channel telegram --account "$MAIN_ACCOUNT_ID" --name "Main Bot" --token "$TELEGRAM_BOT_TOKEN" >/dev/null
  oc channels add --channel telegram --account "$PRESALES_ACCOUNT_ID" --name "Pre Sales Specialist Bot" --token "$PRESALES_TELEGRAM_BOT_TOKEN" >/dev/null
  oc channels add --channel telegram --account "$SPRINTPLANNER_ACCOUNT_ID" --name "Sprint Planner Bot" --token "$SPRINTPLANNER_TELEGRAM_BOT_TOKEN" >/dev/null
  oc channels add --channel telegram --account "$SPENDCUBE_ACCOUNT_ID" --name "Spend Cube Bot" --token "$SPENDCUBE_TELEGRAM_BOT_TOKEN" >/dev/null
  oc channels add --channel telegram --account "$PROCESSMAP_ACCOUNT_ID" --name "Process Mapping Bot" --token "$PROCESSMAP_TELEGRAM_BOT_TOKEN" >/dev/null
  if [[ -n "${AI_SALES_COACH_TELEGRAM_BOT_TOKEN:-}" ]]; then
    oc channels add --channel telegram --account "$SALESCOACH_ACCOUNT_ID" --name "AI Sales Coach Bot" --token "$AI_SALES_COACH_TELEGRAM_BOT_TOKEN" >/dev/null
  fi
  if [[ -n "${STRAVY_GTM_TELEGRAM_BOT_TOKEN:-}" ]]; then
    oc channels add --channel telegram --account "$STRAVY_GTM_ACCOUNT_ID" --name "Stravy GTM Agent Bot" --token "$STRAVY_GTM_TELEGRAM_BOT_TOKEN" >/dev/null
  fi
  if [[ -n "${AI_CFO_TELEGRAM_BOT_TOKEN:-}" ]]; then
    oc channels add --channel telegram --account "$AICFO_ACCOUNT_ID" --name "AI CFO Bot" --token "$AI_CFO_TELEGRAM_BOT_TOKEN" >/dev/null
  fi

  if [[ -n "${TELEGRAM_ALLOWED_IDS:-}" ]]; then
    local allow_json ids
    ids="$(printf "%s" "$TELEGRAM_ALLOWED_IDS" | awk -F',' '{for(i=1;i<=NF;i++){gsub(/^ +| +$/,"",$i); if(length($i)>0) printf "\"tg:%s\"%s",$i,(i<NF?",":"")}}')"
    allow_json="[${ids}]"
    oc config set channels.telegram.allowFrom "$allow_json" --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.default.allowFrom "$allow_json" --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.presales.allowFrom "$allow_json" --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.sprintplanner.allowFrom "$allow_json" --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.spendcube.allowFrom "$allow_json" --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.processmap.allowFrom "$allow_json" --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.salescoach.allowFrom "$allow_json" --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.stravygtm.allowFrom "$allow_json" --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.aicfo.allowFrom "$allow_json" --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.default.dmPolicy '"allowlist"' --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.presales.dmPolicy '"allowlist"' --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.sprintplanner.dmPolicy '"allowlist"' --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.spendcube.dmPolicy '"allowlist"' --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.processmap.dmPolicy '"allowlist"' --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.salescoach.dmPolicy '"allowlist"' --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.stravygtm.dmPolicy '"allowlist"' --strict-json >/dev/null || true
    oc config set channels.telegram.accounts.aicfo.dmPolicy '"allowlist"' --strict-json >/dev/null || true
  fi

  log "Configuring account-to-agent bindings..."
  local bindings
  bindings="[{agentId:'main',match:{channel:'telegram',accountId:'default'}},{agentId:'pre-sales-specialist',match:{channel:'telegram',accountId:'presales'}},{agentId:'sprint-planner',match:{channel:'telegram',accountId:'sprintplanner'}},{agentId:'spend-cube-agent',match:{channel:'telegram',accountId:'spendcube'}},{agentId:'process-mapping-agent',match:{channel:'telegram',accountId:'processmap'}}]"
  if [[ -n "${AI_SALES_COACH_TELEGRAM_BOT_TOKEN:-}" ]]; then
    bindings="[{agentId:'main',match:{channel:'telegram',accountId:'default'}},{agentId:'pre-sales-specialist',match:{channel:'telegram',accountId:'presales'}},{agentId:'sprint-planner',match:{channel:'telegram',accountId:'sprintplanner'}},{agentId:'spend-cube-agent',match:{channel:'telegram',accountId:'spendcube'}},{agentId:'process-mapping-agent',match:{channel:'telegram',accountId:'processmap'}},{agentId:'ai-sales-coach',match:{channel:'telegram',accountId:'salescoach'}}]"
  fi
  if [[ -n "${STRAVY_GTM_TELEGRAM_BOT_TOKEN:-}" ]]; then
    bindings="${bindings%]},{agentId:'stravy-gtm-agent',match:{channel:'telegram',accountId:'stravygtm'}}]"
  fi
  if [[ -n "${AI_CFO_TELEGRAM_BOT_TOKEN:-}" ]]; then
    bindings="${bindings%]},{agentId:'ai-cfo',match:{channel:'telegram',accountId:'aicfo'}}]"
  fi
  oc config set bindings "$bindings" --strict-json >/dev/null
}

restart_openclaw() {
  log "Restarting OpenClaw container..."
  docker compose -f "$COMPOSE_FILE" restart
  sleep 10
}

start_clawmetry() {
  log "Starting ClawMetry on port 8900..."
  docker exec "$CONTAINER_NAME" pkill -f "^clawmetry .*--port 8900" >/dev/null 2>&1 || true
  docker exec -d "$CONTAINER_NAME" clawmetry --host 0.0.0.0 --port 8900 --data-dir /root/.openclaw --no-debug >/dev/null 2>&1 || true
}

verify() {
  log "Verifying channels, agents, and endpoints..."
  oc channels status --probe || true
  oc agents list --bindings || true
  oc skills check | sed -n '1,120p' || true
  curl -s -o /dev/null -w "OpenClaw HTTP %{http_code}\n" "http://localhost:${OPENCLAW_PORT:-18789}/" || true
  curl -s -o /dev/null -w "ClawMetry HTTP %{http_code}\n" "http://localhost:8900/" || true
}

summary() {
  cat <<EOF

[bootstrap] Completed.

OpenClaw:   http://<VM_IP>:${OPENCLAW_PORT:-18789}
ClawMetry:  http://<VM_IP>:8900

Telegram routes:
  default       -> main
  presales      -> pre-sales-specialist
  sprintplanner -> sprint-planner
  spendcube     -> spend-cube-agent
  processmap    -> process-mapping-agent
  salescoach    -> ai-sales-coach (if AI_SALES_COACH_TELEGRAM_BOT_TOKEN is set)
  stravygtm     -> stravy-gtm-agent (if STRAVY_GTM_TELEGRAM_BOT_TOKEN is set)
  aicfo         -> ai-cfo (if AI_CFO_TELEGRAM_BOT_TOKEN is set)
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
  ensure_agent "Pre Sales Specialist" "/root/.openclaw/workspace-pre-sales"
  ensure_agent "Sprint Planner" "/root/.openclaw/workspace-sprint-planner"
  ensure_agent "Spend Cube Agent" "/root/.openclaw/workspace-spend-cube"
  ensure_agent "Process Mapping Agent" "/root/.openclaw/workspace-process-mapping"
  ensure_agent "AI Sales Coach" "/root/.openclaw/workspace-ai-sales-coach"
  ensure_agent "Stravy GTM Agent" "/root/.openclaw/workspace-stravy-gtm"
  ensure_agent "AI CFO" "/root/.openclaw/workspace-ai-cfo"
  configure_agents_workspace_files
  configure_telegram_accounts_and_routing
  restart_openclaw
  start_clawmetry
  verify
  summary
}

main "$@"
