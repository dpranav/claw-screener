# Teams Real-Time Bot Starter

This folder provides a production-oriented starter scaffold for the **true real-time** Teams path:

1. capture transcript/audio in a Teams meeting bot,
2. send transcript chunks every few seconds,
3. call existing Azure Function (`teams-transcript`),
4. receive AI Sales Coach tip and post back to Teams.

It intentionally separates:
- **Control plane (this starter):** chunk ingest, forwarding, throttling, dedupe, posting contract.
- **Media plane (you implement):** Teams meeting media capture + STT pipeline.

---

## 1) What this starter includes

- `src/server.js`  
  HTTP service with:
  - `GET /health`
  - `POST /api/transcript-chunk`
  - `POST /api/media-frame`
  - `POST /api/media-flush`
- `src/functionClient.js`  
  Forwarding client to:
  - `https://stravion-teams-voice-fn.azurewebsites.net/api/teams-transcript?code=...`
- `src/sessionStore.js`  
  In-memory dedupe and post-throttle guardrails.
- `src/mediaBuffer.js`  
  Session-aware rolling chunk buffer with overlap.
- `src/sttAdapter.js`  
  Pluggable STT adapter contract (`passthrough` and Azure stub).
- `manifest/manifest.template.json`  
  Teams app manifest template for packaging/install.
- `.env.example`  
  Environment template.

---

## 2) Quick start

```bash
cd integrations/teams-realtime-bot
cp .env.example .env
npm install
npm run dev
```

Health check:

```bash
curl http://localhost:7090/health
```

Send a sample chunk:

```bash
curl -X POST http://localhost:7090/api/transcript-chunk \
  -H "Content-Type: application/json" \
  -H "X-Bot-Token: <BOT_INGEST_TOKEN_if_set>" \
  -d "{\"sessionId\":\"teams-demo\",\"text\":\"Client says budget gate is next Friday\",\"final\":false}"
```

Send a sample media frame (contract endpoint):

```bash
curl -X POST http://localhost:7090/api/media-frame \
  -H "Content-Type: application/json" \
  -H "X-Bot-Token: <BOT_INGEST_TOKEN_if_set>" \
  -d "{\"sessionId\":\"teams-demo\",\"text\":\"We need procurement sign-off by Tuesday\",\"sequence\":1,\"final\":false}"
```

---

## 3) Environment variables

Required:
- `TEAMS_TRANSCRIPT_FUNCTION_URL`
- `INTEGRATION_TOKEN`

Optional:
- `BOT_INGEST_TOKEN` (protect inbound endpoint)
- `TEAMS_TIP_WEBHOOK_URL` (if set, service posts tips externally; if not, tips are returned/logged only)
- throttling knobs:
  - `TIP_MIN_SECONDS_BETWEEN_POSTS`
  - `TIP_MIN_CHARS`
  - `TIP_DEDUPE_WINDOW`
- media/STT knobs:
  - `MEDIA_FLUSH_SECONDS`
  - `MEDIA_MAX_CHARS_PER_CHUNK`
  - `MEDIA_OVERLAP_WORDS`
  - `STT_ADAPTER`
  - `AZURE_SPEECH_KEY`
  - `AZURE_SPEECH_REGION`
  - `STT_LANGUAGE`
  - `STT_SAMPLE_RATE_HZ`
  - `STT_BITS_PER_SAMPLE`
  - `STT_CHANNELS`
  - `STT_MIN_CONFIDENCE`

---

## 4) Media plane implementation (what your dev team must add)

This starter includes the ingestion contract but does **not** include direct Teams media capture.  
Add a media worker service:

1. Join meeting media as a Teams bot/service.
2. Capture speaker audio stream.
3. Run STT (Azure Speech SDK recommended).
4. For each STT partial/final event, call:
   - `POST /api/media-frame`
5. Use `sessionId = meetingId` for continuity.

Recommended chunking:
- flush interval: 4 seconds
- max chunk chars: 1200
- overlap: 10-20 words for context continuity

### `/api/media-frame` request contract

```json
{
  "sessionId": "teams-meeting-123",
  "sequence": 42,
  "timestamp": "2026-02-25T14:05:20Z",
  "speakerId": "user-aad-object-id",
  "contentType": "audio/pcm",
  "audioBase64": "<optional-audio-bytes>",
  "text": "optional pre-transcribed text",
  "final": false
}
```

Notes:
- With `STT_ADAPTER=passthrough`, send `text` directly.
- With `STT_ADAPTER=azure_speech`, this starter uses Azure Speech SDK and transcribes `audioBase64`.
- The service buffers text by session and auto-flushes to Azure Function on threshold/final.
- For `azure_speech`, audio must be raw PCM that matches:
  - `STT_SAMPLE_RATE_HZ`
  - `STT_BITS_PER_SAMPLE`
  - `STT_CHANNELS`

### `/api/media-flush` request contract

```json
{
  "sessionId": "teams-meeting-123",
  "final": false
}
```

Use this when your media worker wants to force immediate chunk emission.

---

## 5) Teams app packaging

1. Copy `manifest/manifest.template.json` to `manifest.json`.
2. Replace:
   - `id`
   - `botId`
   - `validDomains`
3. Add icon files:
   - `outline.png`
   - `color.png`
4. Zip `manifest.json`, `outline.png`, `color.png`.
5. Upload in Teams Developer Portal / Admin Center.

---

## 6) Security checklist

- Keep `INTEGRATION_TOKEN` and function key in secret storage.
- Set `BOT_INGEST_TOKEN` to protect this service endpoint.
- Restrict inbound network (private endpoint or IP allowlist where possible).
- Log request IDs, `sessionId`, and response status (without leaking transcript in error logs).

---

## 7) How this connects to current repo architecture

Existing pipeline already available:

`teams-realtime-bot` -> `teams-azure-function` -> `voice.proqaai.net/ingest` -> `ai-sales-coach`

So your primary remaining build task is Teams meeting media capture and wiring real Azure Speech transcription into `src/sttAdapter.js`.

