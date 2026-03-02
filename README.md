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
   ```

   | Variable | Description | Default |
   |----------|-------------|---------|
   | `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | *(required)* |
   | `TELEGRAM_DM_POLICY` | `pairing` / `allowlist` / `open` / `disabled` | `pairing` |
   | `TELEGRAM_ALLOWED_IDS` | Comma-separated Telegram user IDs (for `allowlist` mode) | — |

4. **Restart the container**:

   ```bash
   docker compose down && docker compose up -d
   ```

5. **Start chatting** -- open your bot in Telegram and send `/start`. If using `pairing` mode, the gateway will give you an approval code on first contact.

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
