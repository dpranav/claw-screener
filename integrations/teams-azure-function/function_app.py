import json
import logging
import os
from typing import Any, Dict

import azure.functions as func
import requests


app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
log = logging.getLogger("teams-voice-webhook")


VOICE_BRIDGE_URL = os.getenv("VOICE_BRIDGE_URL", "https://voice.proqaai.net/ingest")
VOICE_API_TOKEN = os.getenv("VOICE_API_TOKEN", "")
INTEGRATION_TOKEN = os.getenv("INTEGRATION_TOKEN", "")
TEAMS_OUTGOING_WEBHOOK_URL = os.getenv("TEAMS_OUTGOING_WEBHOOK_URL", "")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))


def _json_error(status: int, message: str) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"ok": False, "error": message}),
        mimetype="application/json",
        status_code=status,
    )


def _optional_post_to_teams(text: str) -> bool:
    if not TEAMS_OUTGOING_WEBHOOK_URL:
        return False
    card = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": "AI Sales Coach Tip",
        "themeColor": "0078D7",
        "title": "AI Sales Coach",
        "text": text,
    }
    resp = requests.post(
        TEAMS_OUTGOING_WEBHOOK_URL,
        json=card,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return True


def _extract_payload(req: func.HttpRequest) -> Dict[str, Any]:
    body = req.get_json()
    transcript = str(body.get("text") or body.get("transcript") or "").strip()
    if not transcript:
        raise ValueError("text (or transcript) is required")
    return {
        "sessionId": str(body.get("sessionId") or body.get("meetingId") or "teams-default"),
        "text": transcript,
        "final": bool(body.get("final", False)),
    }


@app.route(route="teams-transcript", methods=["POST"])
def teams_transcript(req: func.HttpRequest) -> func.HttpResponse:
    try:
        supplied = req.headers.get("x-integration-token", "")
        if INTEGRATION_TOKEN and supplied != INTEGRATION_TOKEN:
            return _json_error(401, "unauthorized")

        if not VOICE_API_TOKEN:
            return _json_error(500, "VOICE_API_TOKEN is not configured")

        payload = _extract_payload(req)
        headers = {
            "Content-Type": "application/json",
            "X-Voice-Token": VOICE_API_TOKEN,
        }
        resp = requests.post(
            VOICE_BRIDGE_URL,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        tip = str(data.get("tip", "")).strip()

        posted_to_teams = False
        if tip:
            posted_to_teams = _optional_post_to_teams(tip)

        return func.HttpResponse(
            json.dumps(
                {
                    "ok": True,
                    "tip": tip,
                    "voiceResponse": data,
                    "postedToTeamsWebhook": posted_to_teams,
                }
            ),
            mimetype="application/json",
            status_code=200,
        )
    except ValueError as exc:
        return _json_error(400, str(exc))
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        body = exc.response.text[:800] if exc.response is not None else str(exc)
        log.exception("Voice bridge HTTP error: %s", body)
        return _json_error(status, f"voice bridge error: {body}")
    except Exception as exc:
        log.exception("Unhandled Teams integration error")
        return _json_error(500, f"internal error: {exc}")
