# OpenClaw Rebuild Runbook

This runbook is the single reference to recreate this project from scratch on a new machine or VM.

It covers:
- required keys and secrets (by name, purpose, and where they are used),
- infrastructure and DNS setup,
- deployment order,
- channel setup (Telegram, Email, Voice, Teams),
- verification and troubleshooting.

---

## 1) Scope and Baseline

Current target baseline:
- Project: `claw-screener`
- Runtime stack: Docker Compose with OpenClaw + channel bridges
- Core domain: `openclaw.proqaai.net`
- Voice domain: `voice.proqaai.net`
- Cloud: Azure VM in resource group `Stravion` (Central US)

Primary services:
- `openclaw-screener` (OpenClaw gateway + agents + ClawMetry)
- `openclaw-email-bridge` (O365 Graph inbound email routing + replies)
- `openclaw-voice-bridge` (token-protected transcript ingestion for AI Sales Coach)
- Azure Function (`stravion-teams-voice-fn`) for Teams transcript integration

---

## 2) Repository Files You Need

Critical files/directories:
- `Dockerfile`
- `docker-compose.yml`
- `docker-entrypoint.sh`
- `bootstrap.sh`
- `hardening.sh`
- `.env.example`
- `cloud-init.yaml`
- `agent-templates/`
- `channels/email-bridge/`
- `channels/voice-bridge/`
- `integrations/teams-azure-function/`
- `scripts/azure_voice_nginx.sh`
- `scripts/azure_voice_certbot.sh`

---

## 3) Key and Secret Inventory

Do not commit real values into Git. Store in a secure secret manager and inject at deploy time.

### 3.1 LLM and Skill Keys

| Key | Required | Used by | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | One provider required | OpenClaw | Claude models |
| `OPENAI_API_KEY` | Optional | OpenClaw | OpenAI models |
| `XAI_API_KEY` | Optional | OpenClaw | xAI models |
| `GEMINI_API_KEY` | Yes (for image/browser skill flows) | OpenClaw skills | Gemini-backed skill support |

### 3.2 OpenClaw Core Settings

| Key | Required | Notes |
|---|---|---|
| `OPENCLAW_PROVIDER` | Yes | Example: `anthropic` |
| `OPENCLAW_MODEL` | Yes | Current safe runtime in this environment has used `google/gemini-2.5-flash` due upstream issue |
| `OPENCLAW_PORT` | Yes | Default `18789` |
| `OPENCLAW_ALLOWED_ORIGINS` | Yes for non-local UI | Must include `https://openclaw.proqaai.net` |
| `OPENCLAW_ALLOW_HOST_HEADER_FALLBACK` | Yes | Keep `false` in hardened prod |
| `OPENCLAW_AUTH_TOKEN` | Yes in production | Gateway auth for UI/API access |
| `OPENCLAW_INVOKE_MODE` | Yes | Set `docker_exec` for channel bridges |
| `OPENCLAW_CONTAINER_NAME` | Yes | `openclaw-screener` |

### 3.3 Telegram Bot Tokens

| Key | Agent Route |
|---|---|
| `TELEGRAM_BOT_TOKEN` | `main` |
| `PRESALES_TELEGRAM_BOT_TOKEN` | `pre-sales-specialist` |
| `SPRINTPLANNER_TELEGRAM_BOT_TOKEN` | `sprint-planner` |
| `SPENDCUBE_TELEGRAM_BOT_TOKEN` | `spend-cube-agent` |
| `PROCESSMAP_TELEGRAM_BOT_TOKEN` | `process-mapping-agent` |
| `AI_SALES_COACH_TELEGRAM_BOT_TOKEN` | `ai-sales-coach` |
| `STRAVY_GTM_TELEGRAM_BOT_TOKEN` | `stravy-gtm-agent` |
| `AI_CFO_TELEGRAM_BOT_TOKEN` | `ai-cfo` |

Additional Telegram controls:
- `TELEGRAM_DM_POLICY`
- `TELEGRAM_ALLOWED_IDS`
- `TELEGRAM_GROUP_IDS`
- `TELEGRAM_GROUP_REQUIRE_MENTION`
- `TELEGRAM_ACCOUNT_IDS`

### 3.4 Email Channel (Microsoft Graph)

| Key | Required | Purpose |
|---|---|---|
| `EMAIL_CHANNEL_ENABLED` | Yes | Turn channel on/off |
| `EMAIL_PROVIDER` | Yes | `graph` |
| `EMAIL_GRAPH_TENANT_ID` | Yes | Microsoft Entra tenant |
| `EMAIL_GRAPH_CLIENT_ID` | Yes | App registration client ID |
| `EMAIL_GRAPH_CLIENT_SECRET` | Yes | App secret |
| `EMAIL_GRAPH_USER_ID` | Yes | Mailbox (`agents@stravion.ai`) |
| `EMAIL_REPLY_ENABLED` | Yes | Auto-reply toggle |
| `EMAIL_GRAPH_MARK_READ` | Recommended `false` | Keep false with least privilege (`Mail.Read` + `Mail.Send`) |
| `EMAIL_AGENT_ROUTING` | Yes | Address-based route map |
| `EMAIL_SUBJECT_AGENT_ROUTING` | Recommended | Subject tag fallback (`[cfo]`, `[presales]`, etc.) |
| `EMAIL_PROCESSED_IDS_PATH` | Recommended | Dedupe persistence path (`/state/...`) |

Office 365 controls outside app:
- Mailbox aliases on `agents@stravion.ai` (`presales@`, `cfo@`, etc.).
- Graph app access policy restricted to mailbox scope group.

### 3.5 Voice Channel

| Key | Required | Purpose |
|---|---|---|
| `VOICE_CHANNEL_ENABLED` | Yes | Turn channel on/off |
| `VOICE_AGENT_ID` | Yes | Usually `ai-sales-coach` |
| `VOICE_BRIDGE_PORT` | Yes | Internal local bind, default `8787` |
| `VOICE_API_TOKEN` | Yes | Required for `/ingest` and websocket access |
| `VOICE_MIN_SECONDS_BETWEEN_PROMPTS` | Optional | Throttle |
| `VOICE_MIN_CHARS_BEFORE_PROMPT` | Optional | Context threshold |
| `VOICE_MAX_CONTEXT_CHARS` | Optional | Context window size |

### 3.6 Teams Function Integration

| Key | Required | Location |
|---|---|---|
| `VOICE_BRIDGE_URL` | Yes | Function App settings |
| `VOICE_API_TOKEN` | Yes | Function App settings |
| `INTEGRATION_TOKEN` | Yes | Function App settings + caller header |
| `REQUEST_TIMEOUT_SECONDS` | Optional | Function App settings |
| `TEAMS_OUTGOING_WEBHOOK_URL` | Optional | Function App settings |
| Function key (`?code=`) | Yes | Function endpoint auth |

---

## 4) One-Time External Setup

### 4.1 DNS

Required records:
- `openclaw.proqaai.net` -> VM public IP
- `voice.proqaai.net` -> VM public IP

### 4.2 Office 365 Mailbox and Graph Permissions

1. Create mailbox: `agents@stravion.ai`
2. Add aliases: `presales`, `sprint`, `spendcube`, `processmap`, `salescoach`, `stravygtm`, `cfo`
3. Azure App Registration permissions:
   - `Mail.Read` (Application)
   - `Mail.Send` (Application)
4. Restrict mailbox access with Exchange policy (only `agents@stravion.ai` scope group).

### 4.3 Telegram

Create all required bots via BotFather and capture tokens.

---

## 5) Build and Deploy Order (From Scratch)

## 5.1 VM Provision

Option A:
- Create VM with `cloud-init.yaml` and fill bootstrap placeholders.

Option B:
- Manual clone and deploy:
  1. Clone repo
  2. Copy `.env.example` -> `.env`
  3. Fill all required values
  4. Run:
     - `chmod +x bootstrap.sh`
     - `./bootstrap.sh`

## 5.2 Harden and TLS

Run:
- `sudo ./hardening.sh --domain openclaw.proqaai.net --email <admin-email> --with-certbot`

Voice TLS setup:
- `scripts/azure_voice_nginx.sh`
- `scripts/azure_voice_certbot.sh`

## 5.3 Channel Services

Bring up stack:
- `docker compose up -d --build`

Services expected:
- `openclaw-screener`
- `openclaw-email-bridge`
- `openclaw-voice-bridge`

## 5.4 Teams Function

Deploy from `integrations/teams-azure-function`:
1. Create storage account + Function App (Python 3.11, Linux)
2. Zip deploy
3. Set Function App settings:
   - `VOICE_BRIDGE_URL=https://voice.proqaai.net/ingest`
   - `VOICE_API_TOKEN=<VOICE_API_TOKEN>`
   - `INTEGRATION_TOKEN=<INTEGRATION_TOKEN>`
4. Call endpoint:
   - `POST /api/teams-transcript?code=<function_key>`
   - header `x-integration-token`

---

## 6) Validation Checklist

## 6.1 Core
- `https://openclaw.proqaai.net` returns `200`
- Gateway connects from Control UI with auth token

## 6.2 Telegram
- Each bot responds in DM
- Group routing works with allowlist and mention settings

## 6.3 Email
- Send `"[cfo] Monthly cash runway analysis"` to `cfo@stravion.ai`
- Confirm bridge logs route to `ai-cfo`
- Confirm reply sent from `agents@stravion.ai`

## 6.4 Voice
- `GET https://voice.proqaai.net/health`
- `POST /ingest` without token -> unauthorized
- `POST /ingest` with `X-Voice-Token` -> success

## 6.5 Teams Function
- Endpoint rejects missing/invalid `x-integration-token`
- Valid token returns `ok: true` and tip payload

---

## 7) Known Issues and Mitigations

- OpenClaw `v2026.3.12` showed an upstream startup regression in this environment (`ANTHROPIC_MODEL_ALIASES` initialization error).
  - Mitigation used: run stable version and/or use `OPENCLAW_MODEL=google/gemini-2.5-flash` in affected startup paths.
- Graph alias flattening may rewrite recipients to `agents@...`.
  - Mitigation: subject-tag fallback routing (`EMAIL_SUBJECT_AGENT_ROUTING`).
- Graph `mark as read` requires broader permission than least-privilege posture.
  - Mitigation: `EMAIL_GRAPH_MARK_READ=false` + processed ID cache.

---

## 8) Security and Rotation

Rotate on handover:
- all LLM API keys,
- Telegram bot tokens,
- Graph client secret,
- `OPENCLAW_AUTH_TOKEN`,
- `VOICE_API_TOKEN`,
- Teams Function `INTEGRATION_TOKEN`,
- Function key (`?code=`).

Never commit real values into Git. Keep `.env` and app settings in secure secret storage.
