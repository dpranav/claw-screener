# Teams -> AI Sales Coach (Azure Function)

This function accepts Microsoft Teams transcript chunks and forwards them to your secured voice bridge:

- Voice bridge URL: `https://voice.proqaai.net/ingest`
- Voice auth header: `X-Voice-Token`
- Route: `POST /api/teams-transcript`

## What It Does

1. Validates integration token (`x-integration-token`) if configured.
2. Receives transcript payload from Teams workflow.
3. Calls `voice.proqaai.net/ingest` with `X-Voice-Token`.
4. Returns the AI Sales Coach tip.
5. Optionally posts tip to Teams Incoming Webhook.

## Required App Settings

- `VOICE_BRIDGE_URL` (default `https://voice.proqaai.net/ingest`)
- `VOICE_API_TOKEN` (must match your VM voice token)
- `INTEGRATION_TOKEN` (shared secret between Teams workflow and this function)
- `REQUEST_TIMEOUT_SECONDS` (default `30`)
- `TEAMS_OUTGOING_WEBHOOK_URL` (optional)

## Request Payload

Send one of these fields for transcript text:

- `text`
- `transcript`

Example:

```json
{
  "sessionId": "teams-meeting-abc",
  "text": "Client says budget gate closes next Friday.",
  "final": false
}
```

Required header (if `INTEGRATION_TOKEN` is set):

- `x-integration-token: <INTEGRATION_TOKEN>`

## Response

```json
{
  "ok": true,
  "tip": "1) Ask next ...",
  "voiceResponse": {
    "ok": true,
    "tip": "..."
  },
  "postedToTeamsWebhook": false
}
```

## Local Run

1. Copy `local.settings.example.json` -> `local.settings.json`
2. Fill values
3. Install dependencies:
   - `pip install -r requirements.txt`
4. Run:
   - `func start`

## Azure Deploy (CLI)

From this directory:

```bash
az functionapp deployment source config-zip \
  --resource-group <rg> \
  --name <function-app-name> \
  --src teams-azure-function.zip
```

Set app settings:

```bash
az functionapp config appsettings set \
  --resource-group <rg> \
  --name <function-app-name> \
  --settings \
  VOICE_BRIDGE_URL=https://voice.proqaai.net/ingest \
  VOICE_API_TOKEN=<VOICE_API_TOKEN> \
  INTEGRATION_TOKEN=<INTEGRATION_TOKEN> \
  REQUEST_TIMEOUT_SECONDS=30
```
