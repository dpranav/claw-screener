import asyncio
import hmac
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests
from fastapi import FastAPI, Header, WebSocket, WebSocketDisconnect


logging.basicConfig(
    level=os.getenv("VOICE_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [voice-bridge] %(levelname)s %(message)s",
)
log = logging.getLogger("voice-bridge")


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


VOICE_ENABLED = env_bool("VOICE_CHANNEL_ENABLED", False)
HOOK_URL = os.getenv("OPENCLAW_HOOK_URL", "http://openclaw:18789/hooks/agent")
AUTH_TOKEN = os.getenv("OPENCLAW_AUTH_TOKEN", "")
INVOKE_MODE = os.getenv("OPENCLAW_INVOKE_MODE", "docker_exec").strip().lower()
OPENCLAW_CONTAINER_NAME = os.getenv("OPENCLAW_CONTAINER_NAME", "openclaw-screener")
VOICE_API_TOKEN = os.getenv("VOICE_API_TOKEN", "")
VOICE_AGENT_ID = os.getenv("VOICE_AGENT_ID", "ai-sales-coach")
MIN_INTERVAL_SECONDS = int(os.getenv("VOICE_MIN_SECONDS_BETWEEN_PROMPTS", "20"))
MIN_CHARS = int(os.getenv("VOICE_MIN_CHARS_BEFORE_PROMPT", "160"))
MAX_CONTEXT_CHARS = int(os.getenv("VOICE_MAX_CONTEXT_CHARS", "5000"))
MAX_RESPONSE_CHARS = int(os.getenv("VOICE_MAX_RESPONSE_CHARS", "1200"))


@dataclass
class SessionState:
    lines: List[str] = field(default_factory=list)
    last_sent_at: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


sessions: Dict[str, SessionState] = {}
app = FastAPI(title="OpenClaw Voice Bridge", version="1.0.0")


def get_session(session_id: str) -> SessionState:
    if session_id not in sessions:
        sessions[session_id] = SessionState()
    return sessions[session_id]


def call_openclaw(transcript_block: str, session_id: str) -> str:
    prompt = (
        "You are assisting during a live client call.\n"
        "Return only concise, immediate coaching guidance.\n"
        "Format:\n"
        "1) Ask next (max 3 bullets)\n"
        "2) Risk to watch (1 bullet)\n"
        "3) Suggested pivot (1 bullet)\n\n"
        f"Session: {session_id}\n"
        f"Transcript window:\n{transcript_block[-MAX_CONTEXT_CHARS:]}"
    )

    if INVOKE_MODE == "docker_exec":
        cmd = [
            "docker",
            "exec",
            OPENCLAW_CONTAINER_NAME,
            "openclaw",
            "agent",
            "--agent",
            VOICE_AGENT_ID,
            "--message",
            prompt,
            "--json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"openclaw agent failed ({proc.returncode}): {proc.stderr.strip()[:400]}")
        raw = (proc.stdout or "").strip()
        data = json.loads(raw) if raw else {}
        payloads = (((data.get("result") or {}).get("payloads")) or [])
        for item in payloads:
            text = item.get("text") if isinstance(item, dict) else None
            if isinstance(text, str) and text.strip():
                return text.strip()[:MAX_RESPONSE_CHARS]
        return raw[:MAX_RESPONSE_CHARS]

    payload = {
        "agentId": VOICE_AGENT_ID,
        "name": "Live Voice Coach",
        "message": prompt,
    }

    headers = {"Content-Type": "application/json"}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
        headers["x-openclaw-auth-token"] = AUTH_TOKEN

    resp = requests.post(HOOK_URL, json=payload, headers=headers, timeout=90)
    resp.raise_for_status()
    try:
        data = resp.json()
    except Exception:
        return resp.text.strip()[:MAX_RESPONSE_CHARS]
    for key in ("response", "message", "output", "text", "result"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:MAX_RESPONSE_CHARS]
    return str(data)[:MAX_RESPONSE_CHARS]


def extract_token(auth_header: Optional[str], header_token: Optional[str], query_token: Optional[str]) -> str:
    if query_token:
        return query_token.strip()
    if header_token:
        return header_token.strip()
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""


def is_authorized(token: str) -> bool:
    if not VOICE_API_TOKEN:
        return False
    return hmac.compare_digest(token or "", VOICE_API_TOKEN)


async def maybe_get_tip(session_id: str, new_line: str, force: bool = False) -> str:
    if not VOICE_ENABLED:
        return "Voice bridge is disabled (set VOICE_CHANNEL_ENABLED=true)."

    session = get_session(session_id)
    async with session.lock:
        session.lines.append(new_line.strip())
        now = time.time()
        transcript = "\n".join(session.lines)[-MAX_CONTEXT_CHARS:]
        should_send = force or (
            len(transcript) >= MIN_CHARS and (now - session.last_sent_at) >= MIN_INTERVAL_SECONDS
        )
        if not should_send:
            return ""

        loop = asyncio.get_running_loop()
        tip = await loop.run_in_executor(None, call_openclaw, transcript, session_id)
        session.last_sent_at = now
        return tip


@app.get("/health")
def health() -> dict:
    return {"ok": True, "voice_enabled": VOICE_ENABLED, "agent_id": VOICE_AGENT_ID}


@app.post("/ingest")
async def ingest(
    payload: dict,
    authorization: Optional[str] = Header(default=None),
    x_voice_token: Optional[str] = Header(default=None),
) -> dict:
    token = extract_token(authorization, x_voice_token, None)
    if not is_authorized(token):
        return {"ok": False, "error": "unauthorized"}

    session_id = str(payload.get("sessionId", "default"))
    text = str(payload.get("text", "")).strip()
    is_final = bool(payload.get("final", False))
    if not text:
        return {"ok": False, "error": "text is required"}

    tip = await maybe_get_tip(session_id, text, force=is_final)
    return {"ok": True, "tip": tip}


@app.websocket("/ws/live-coach/{session_id}")
async def live_coach(ws: WebSocket, session_id: str) -> None:
    token = extract_token(
        ws.headers.get("authorization"),
        ws.headers.get("x-voice-token"),
        ws.query_params.get("token"),
    )
    if not is_authorized(token):
        await ws.close(code=1008, reason="unauthorized")
        return

    await ws.accept()
    await ws.send_json(
        {
            "type": "ready",
            "sessionId": session_id,
            "message": "Send transcript chunks as JSON: {\"text\":\"...\",\"final\":false}",
        }
    )
    try:
        while True:
            packet = await ws.receive_json()
            text = str(packet.get("text", "")).strip()
            if not text:
                continue
            is_final = bool(packet.get("final", False))
            tip = await maybe_get_tip(session_id, text, force=is_final)
            if tip:
                await ws.send_json({"type": "coach_tip", "sessionId": session_id, "tip": tip})
    except WebSocketDisconnect:
        log.info("WebSocket disconnected session=%s", session_id)
