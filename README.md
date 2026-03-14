# Claw-Screener

Stock screener combining technical analysis (Williams %R oversold signals) with Warren Buffett-style fundamental analysis using SEC data. Supports US (S&P 500) and Thai (SET) markets.

## Installation

```bash
bun install
```

## Scripts

### 1. Combined Screening (`screening.ts`)

Runs both technical and fundamental analysis to find quality oversold stocks.

```bash
bun run src/screening.ts [options]
```

**Options:**
| Flag | Description | Default |
|------|-------------|---------|
| `--market` | Market: `us` or `bk` | `us` |
| `--min-score` | Minimum Buffett score (0-10) | `5` |
| `--top-n` | Number of results to show | `10` |
| `--format` | Output: `text`, `json`, `telegram` | `text` |

**Examples:**

```bash
# US market, default settings
bun run src/screening.ts

# US market, stricter fundamental requirements
bun run src/screening.ts --market us --min-score 7 --top-n 5

# Thai market (technical only, no SEC data)
bun run src/screening.ts --market bk

# JSON output for automation
bun run src/screening.ts --format json

# Telegram format for messaging apps
bun run src/screening.ts --format telegram
```

### 2. Technical Only (`technicalOnly.ts`)

Fast oversold scan using Williams %R indicator only. No SEC data required.

```bash
bun run src/technicalOnly.ts [options]
```

**Options:**
| Flag | Description | Default |
|------|-------------|---------|
| `--market` | Market: `us` or `bk` | `us` |
| `--threshold` | Williams %R threshold (e.g., -80) | `-80` |
| `--top-n` | Number of results to show | `20` |
| `--format` | Output: `text`, `json`, `telegram` | `text` |

**Examples:**

```bash
# Default scan
bun run src/technicalOnly.ts

# More oversold stocks
bun run src/technicalOnly.ts --threshold -70 --top-n 50

# Thai market
bun run src/technicalOnly.ts --market bk
```

### 3. Analyze Stock (`analyze.ts`)

Deep analysis of a single stock using Buffett's 10 formulas.

```bash
bun run src/analyze.ts <ticker> [options]
```

**Options:**
| Flag | Description | Default |
|------|-------------|---------|
| `--format` | Output: `text`, `json`, `telegram` | `text` |

**Examples:**

```bash
# Analyze a US stock
bun run src/analyze.ts AAPL

# Analyze with Telegram format
bun run src/analyze.ts MSFT --format telegram

# JSON for programmatic use
bun run src/analyze.ts GOOGL --format json

# Analyze a Thai stock (uses Yahoo Finance)
bun run src/analyze.ts PTT.BK
```

## Telegram Channel

You can connect this screener to Telegram so you can interact with OpenClaw directly from a Telegram chat.

### Setup

1. **Create a bot** -- open Telegram, search for **@BotFather**, send `/newbot`, and follow the prompts. Copy the bot token it gives you.

2. **Get your Telegram user ID** -- search for **@userinfobot** on Telegram and send it a message. It will reply with your numeric user ID.

3. **Configure env vars** -- add the following to your `.env`:

   ```env
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   TELEGRAM_DM_POLICY=pairing
   # TELEGRAM_ALLOWED_IDS=123456789,987654321
   # AI_SALES_COACH_TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   # STRAVY_GTM_TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   # AI_CFO_TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   # TELEGRAM_GROUP_IDS=-1001234567890
   # TELEGRAM_GROUP_REQUIRE_MENTION=true
   INSTALL_AGENT_BROWSER_SKILL=true
   INSTALL_GOOSE_GTM_SKILLS=true
   ```

   | Variable | Description | Default |
   |----------|-------------|---------|
   | `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | *(required)* |
   | `TELEGRAM_DM_POLICY` | `pairing` / `allowlist` / `open` / `disabled` | `pairing` |
   | `TELEGRAM_ALLOWED_IDS` | Comma-separated Telegram user IDs (for `allowlist` mode) | — |
   | `AI_SALES_COACH_TELEGRAM_BOT_TOKEN` | Optional dedicated bot token for `AI Sales Coach` agent routing | — |
   | `STRAVY_GTM_TELEGRAM_BOT_TOKEN` | Optional dedicated bot token for `Stravy GTM Agent` routing | — |
   | `AI_CFO_TELEGRAM_BOT_TOKEN` | Optional dedicated bot token for `AI CFO` routing | — |
   | `TELEGRAM_GROUP_IDS` | Comma-separated Telegram group IDs allowed when `groupPolicy=allowlist` | — |
   | `TELEGRAM_GROUP_REQUIRE_MENTION` | Require `@botusername` mentions inside allowlisted groups | `true` |
   | `INSTALL_AGENT_BROWSER_SKILL` | Auto-install `agent-browser` skill during bootstrap (uses `--force`) | `true` |
   | `INSTALL_GOOSE_GTM_SKILLS` | Auto-install all Goose capabilities from repo during bootstrap | `true` |

### Production lock-in settings

To keep HTTPS and model settings stable across container restarts, set:

```env
OPENCLAW_MODEL=anthropic/claude-sonnet-4-5
OPENCLAW_ALLOWED_ORIGINS=https://openclaw.proqaai.net
OPENCLAW_ALLOW_HOST_HEADER_FALLBACK=false
```

4. **Restart the container**:

   ```bash
   docker compose down && docker compose up -d
   ```

5. **Start chatting** -- open your bot in Telegram and send `/start`. If using `pairing` mode, the gateway will give you an approval code on first contact.

## Email Interface (Non-Technical Friendly)

This channel lets users email an address like `presales@...` or `cfo@...` and have the right OpenClaw agent process it.

### How it works

1. `email-bridge` polls your inbox via Microsoft Graph (recommended) or IMAP.
2. It maps recipient aliases to agent IDs.
3. It invokes the target agent via `openclaw agent` inside the OpenClaw container.
4. Optional: sends email reply (Graph when `EMAIL_PROVIDER=graph`, SMTP when `imap`).

### Configure `.env`

```env
OPENCLAW_HOOK_URL=http://openclaw:18789/hooks/agent
OPENCLAW_INVOKE_MODE=docker_exec
OPENCLAW_CONTAINER_NAME=openclaw-screener

EMAIL_CHANNEL_ENABLED=true
EMAIL_PROVIDER=graph

# Preferred: Microsoft Graph app-only (O365)
EMAIL_GRAPH_TENANT_ID=<tenant-id>
EMAIL_GRAPH_CLIENT_ID=<client-id>
EMAIL_GRAPH_CLIENT_SECRET=<client-secret>
EMAIL_GRAPH_USER_ID=agents@stravion.ai
EMAIL_GRAPH_MARK_READ=false
EMAIL_PROCESSED_IDS_PATH=/state/email_bridge_processed_ids.txt

# Optional fallback: IMAP mode
EMAIL_IMAP_HOST=imap.office365.com
EMAIL_IMAP_PORT=993
EMAIL_IMAP_USER=agents@stravion.ai
EMAIL_IMAP_PASSWORD=your-app-password
EMAIL_IMAP_FOLDER=INBOX
EMAIL_POLL_SECONDS=30
EMAIL_AGENT_ROUTING=presales=pre-sales-specialist,sprint=sprint-planner,spendcube=spend-cube-agent,processmap=process-mapping-agent,salescoach=ai-sales-coach,stravygtm=stravy-gtm-agent,cfo=ai-cfo,default=main
EMAIL_SUBJECT_AGENT_ROUTING=[presales]=pre-sales-specialist,[sprint]=sprint-planner,[spendcube]=spend-cube-agent,[processmap]=process-mapping-agent,[salescoach]=ai-sales-coach,[stravygtm]=stravy-gtm-agent,[cfo]=ai-cfo

# Optional: auto-reply with the agent response
EMAIL_REPLY_ENABLED=true
EMAIL_SMTP_HOST=smtp.office365.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USER=agents@stravion.ai
EMAIL_SMTP_PASSWORD=your-app-password
EMAIL_SMTP_FROM=agents@stravion.ai
```

Note: with least-privilege Graph permissions (`Mail.Read` + `Mail.Send`), keep `EMAIL_GRAPH_MARK_READ=false`.
If O365 rewrites aliases to `agents@...` in recipient fields, use subject tags such as `[presales]` to force routing.

### Start

```bash
docker compose up -d --build
docker compose logs --tail 120 email-bridge
```

---

## Voice Channel (Live Meeting Assistant)

This channel accepts live transcript chunks and returns real-time coaching prompts (default agent: `ai-sales-coach`).

### How it works

1. Your meeting/transcription system streams text chunks to `voice-bridge`.
2. `voice-bridge` batches transcript context.
3. It calls OpenClaw Hooks API and returns concise "what to ask next" guidance.

### Configure `.env`

```env
VOICE_CHANNEL_ENABLED=true
VOICE_AGENT_ID=ai-sales-coach
VOICE_BRIDGE_PORT=8787
VOICE_API_TOKEN=<long-random-token>
VOICE_MIN_SECONDS_BETWEEN_PROMPTS=20
VOICE_MIN_CHARS_BEFORE_PROMPT=160
VOICE_MAX_CONTEXT_CHARS=5000
```

### Start

```bash
docker compose up -d --build
curl http://127.0.0.1:8787/health
```

### Ingest options

- HTTP: `POST /ingest` with header `X-Voice-Token: <VOICE_API_TOKEN>` and JSON `{ "sessionId": "call-001", "text": "...", "final": false }`
- WebSocket: connect to `/ws/live-coach/{sessionId}?token=<VOICE_API_TOKEN>` and stream JSON `{ "text": "...", "final": false }`

### Example

```bash
curl -X POST http://127.0.0.1:8787/ingest \
  -H "X-Voice-Token: <VOICE_API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"sessionId":"demo-call","text":"Client says budget is not approved yet, but they need Q2 rollout","final":true}'
```

## Microsoft Teams Integration

Use the Azure Function template in `integrations/teams-azure-function` to connect Teams transcript chunks to the `ai-sales-coach` voice channel.

Flow:
1. Teams workflow/bot sends transcript chunks to the Function endpoint (`/api/teams-transcript`).
2. Function validates `x-integration-token`.
3. Function forwards chunk to `https://voice.proqaai.net/ingest` with `X-Voice-Token`.
4. Function returns coaching tip and can optionally post it to a Teams Incoming Webhook.

See setup and deploy instructions in:
- `integrations/teams-azure-function/README.md`

For true real-time Teams bot scaffolding (chunk ingest + forwarding + throttling starter):
- `integrations/teams-realtime-bot/README.md`

### Deploy Teams Real-Time Bot (Docker on VM)

1. Add variables to `.env` (see `.env.example`):
   - `TEAMS_RT_BOT_PORT`
   - `TEAMS_RT_BOT_INGEST_TOKEN`
   - `TEAMS_TRANSCRIPT_FUNCTION_URL`
   - `INTEGRATION_TOKEN`
   - `TEAMS_RT_STT_ADAPTER` (`passthrough` or `azure_speech`)
   - Azure Speech keys when using `azure_speech`

2. Build/start service:

   ```bash
   make up-teams
   make logs-teams
   ```

3. Local health check:

   ```bash
   curl http://127.0.0.1:${TEAMS_RT_BOT_PORT:-7090}/health
   ```

4. Optional public endpoint via Nginx + TLS:
   - Configure reverse proxy: `scripts/azure_teamsrt_nginx.sh`
   - Issue cert: `scripts/azure_teamsrt_certbot.sh`

## Project Documentation

- Rebuild runbook: `docs/rebuild-from-scratch-runbook.md`
- Technical architecture: `docs/technical-architecture.md`

## Buffett's 10 Formulas

The fundamental analysis evaluates stocks against Warren Buffett's criteria:

| #   | Formula            | Target       | Description              |
| --- | ------------------ | ------------ | ------------------------ |
| 1   | Cash Test          | > Total Debt | Cash covers all debt     |
| 2   | Debt-to-Equity     | < 0.5        | Low leverage             |
| 3   | Return on Equity   | > 15%        | Efficient use of capital |
| 4   | Current Ratio      | > 1.5        | Short-term liquidity     |
| 5   | Operating Margin   | > 12%        | Operational efficiency   |
| 6   | Asset Turnover     | > 0.5        | Asset efficiency         |
| 7   | Interest Coverage  | > 3x         | Ability to pay interest  |
| 8   | Earnings Stability | Positive     | Consistent profitability |
| 9   | Free Cash Flow     | > 0          | Cash generation          |
| 10  | Capital Allocation | > 15% ROE    | Management effectiveness |

**Scoring:** Each passing formula earns 1 point. Maximum score: 10/10.

## Technical Indicator

**Williams %R (Williams Percent Range)**

- Range: -100 to 0
- Oversold: < -80 (potential buy signal)
- Overbought: > -20 (potential sell signal)

The screener finds stocks where:

- Williams %R < -80 (oversold)
- Combined with Buffett score >= min-score (for US market)

## Output Formats

### Text (Default)

```
📊 Combined Quality Screening (US (S&P 500))
Technical: Oversold signals (Williams %R < -80)
Fundamental: Warren Buffett's 10 formulas on SEC data
Minimum Buffett Score: 5/10

Results:
  Total Scanned: 503
  Oversold Found: 42
  Quality Stocks: 8 (Buffett ≥5/10)

Top 10 Opportunities:

1. AAPL   — Combined: 85.2% | Buffett: 8/10 | WR: -82.3
2. MSFT   — Combined: 79.1% | Buffett: 7/10 | WR: -85.1
...
```

### JSON

```json
{
  "totalScanned": 503,
  "oversoldCount": 42,
  "qualityCount": 8,
  "minBuffettScore": 5,
  "market": "us",
  "topStocks": [...]
}
```

### Telegram

```
📊 Combined Quality Screening (US (S&P 500))
Scanned: 503 stocks
Oversold: 42
Quality (Buffett ≥5/10): 8

🌟 Top 10 Quality Opportunities:

1. **AAPL** — Combined: 85% | Buffett: 8/10 | WR: -82.3
2. **MSFT** — Combined: 79% | Buffett: 7/10 | WR: -85.1
```

## Data Sources

- **US Stocks**: SEC EDGAR for fundamentals, Yahoo Finance for prices
- **Thai Stocks**: Yahoo Finance only (no SEC data available)

## Scoring Formula

Combined score = (Technical Score × 0.3) + (Fundamental Score × 0.7)

- Technical Score: (Williams %R + 100) / 100
- Fundamental Score: (Buffett Score / 10) × 100

## npm Scripts

```bash
npm run dev          # Run screening (alias for bun run src/screening.ts)
npm run screening    # Run combined screening
npm run technical    # Run technical-only scan
npm run analyze      # Analyze a stock (requires ticker argument)
```
