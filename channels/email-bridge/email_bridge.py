import json
import imaplib
import logging
import os
import re
import smtplib
import subprocess
import time
from email import message_from_bytes
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr

import requests


logging.basicConfig(
    level=os.getenv("EMAIL_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [email-bridge] %(levelname)s %(message)s",
)
log = logging.getLogger("email-bridge")


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


EMAIL_ENABLED = env_bool("EMAIL_CHANNEL_ENABLED", False)
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "imap").strip().lower()
POLL_SECONDS = int(os.getenv("EMAIL_POLL_SECONDS", "30"))
IMAP_HOST = os.getenv("EMAIL_IMAP_HOST", "")
IMAP_PORT = int(os.getenv("EMAIL_IMAP_PORT", "993"))
IMAP_USER = os.getenv("EMAIL_IMAP_USER", "")
IMAP_PASS = os.getenv("EMAIL_IMAP_PASSWORD", "")
IMAP_FOLDER = os.getenv("EMAIL_IMAP_FOLDER", "INBOX")
INSECURE_TLS = env_bool("EMAIL_IMAP_INSECURE_TLS", False)

SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
SMTP_USER = os.getenv("EMAIL_SMTP_USER", "")
SMTP_PASS = os.getenv("EMAIL_SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("EMAIL_SMTP_FROM", IMAP_USER)
EMAIL_REPLY_ENABLED = env_bool("EMAIL_REPLY_ENABLED", False)

GRAPH_TENANT_ID = os.getenv("EMAIL_GRAPH_TENANT_ID", "")
GRAPH_CLIENT_ID = os.getenv("EMAIL_GRAPH_CLIENT_ID", "")
GRAPH_CLIENT_SECRET = os.getenv("EMAIL_GRAPH_CLIENT_SECRET", "")
GRAPH_USER_ID = os.getenv("EMAIL_GRAPH_USER_ID", IMAP_USER)
GRAPH_SCOPE = os.getenv("EMAIL_GRAPH_SCOPE", "https://graph.microsoft.com/.default")
GRAPH_BASE_URL = os.getenv("EMAIL_GRAPH_BASE_URL", "https://graph.microsoft.com/v1.0")

HOOK_URL = os.getenv("OPENCLAW_HOOK_URL", "http://openclaw:18789/hooks/agent")
AUTH_TOKEN = os.getenv("OPENCLAW_AUTH_TOKEN", "")
INVOKE_MODE = os.getenv("OPENCLAW_INVOKE_MODE", "docker_exec").strip().lower()
OPENCLAW_CONTAINER_NAME = os.getenv("OPENCLAW_CONTAINER_NAME", "openclaw-screener")
EMAIL_ROUTING = os.getenv(
    "EMAIL_AGENT_ROUTING",
    "presales=pre-sales-specialist,sprint=sprint-planner,spendcube=spend-cube-agent,processmap=process-mapping-agent,salescoach=ai-sales-coach,stravygtm=stravy-gtm-agent,cfo=ai-cfo,default=main",
)
MAX_BODY_CHARS = int(os.getenv("EMAIL_MAX_BODY_CHARS", "12000"))
REPLY_MAX_CHARS = int(os.getenv("EMAIL_REPLY_MAX_CHARS", "3500"))
GRAPH_MARK_READ = env_bool("EMAIL_GRAPH_MARK_READ", False)
PROCESSED_IDS_PATH = os.getenv("EMAIL_PROCESSED_IDS_PATH", "/tmp/email_bridge_processed_ids.txt")
SUBJECT_AGENT_ROUTING = os.getenv(
    "EMAIL_SUBJECT_AGENT_ROUTING",
    "[presales]=pre-sales-specialist,[sprint]=sprint-planner,[spendcube]=spend-cube-agent,[processmap]=process-mapping-agent,[salescoach]=ai-sales-coach,[stravygtm]=stravy-gtm-agent,[cfo]=ai-cfo",
)


def parse_routing(raw: str) -> dict:
    routing = {}
    for pair in (raw or "").split(","):
        part = pair.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        routing[k.strip().lower()] = v.strip()
    if "default" not in routing:
        routing["default"] = "main"
    return routing


def parse_subject_routing(raw: str) -> list:
    rules = []
    for pair in (raw or "").split(","):
        part = pair.strip()
        if not part or "=" not in part:
            continue
        token, agent = part.split("=", 1)
        token = token.strip().lower()
        agent = agent.strip()
        if token and agent:
            rules.append((token, agent))
    return rules


ROUTING = parse_routing(EMAIL_ROUTING)
SUBJECT_RULES = parse_subject_routing(SUBJECT_AGENT_ROUTING)
TOKEN_CACHE = {"token": "", "expires_at": 0}
PROCESSED_GRAPH_IDS = set()


def load_processed_ids() -> None:
    try:
        with open(PROCESSED_IDS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                mid = line.strip()
                if mid:
                    PROCESSED_GRAPH_IDS.add(mid)
    except FileNotFoundError:
        return
    except Exception as exc:
        log.warning("Could not load processed IDs cache: %s", exc)


def remember_processed_id(message_id: str) -> None:
    if not message_id:
        return
    if message_id in PROCESSED_GRAPH_IDS:
        return
    PROCESSED_GRAPH_IDS.add(message_id)
    try:
        with open(PROCESSED_IDS_PATH, "a", encoding="utf-8") as f:
            f.write(message_id + "\n")
    except Exception as exc:
        log.warning("Could not persist processed ID cache: %s", exc)


def extract_plain_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            if ctype == "text/plain":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                try:
                    return payload.decode(charset, errors="replace")
                except Exception:
                    return payload.decode("utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except Exception:
        return payload.decode("utf-8", errors="replace")


def resolve_agent(to_header: str) -> str:
    addresses = getaddresses([to_header or ""])
    for _, addr in addresses:
        lower = addr.lower()
        if lower in ROUTING:
            return ROUTING[lower]
        local = lower.split("@", 1)[0]
        if local in ROUTING:
            return ROUTING[local]
    return ROUTING.get("default", "main")


def resolve_agent_from_subject(subject: str) -> str:
    s = (subject or "").strip().lower()
    if not s:
        return ""
    for token, agent in SUBJECT_RULES:
        if token in s:
            return agent
    return ""


def extract_recipients_from_headers(headers: list) -> list:
    if not isinstance(headers, list):
        return []
    # Prefer envelope/original-recipient style headers first.
    preferred = [
        "x-original-to",
        "delivered-to",
        "envelope-to",
        "x-forwarded-to",
        "to",
        "cc",
    ]
    collected = []
    by_name = {}
    for h in headers:
        if not isinstance(h, dict):
            continue
        name = str(h.get("name", "")).strip().lower()
        value = str(h.get("value", "")).strip()
        if not name or not value:
            continue
        by_name.setdefault(name, []).append(value)
    for key in preferred:
        for value in by_name.get(key, []):
            for _, addr in getaddresses([value]):
                if addr:
                    collected.append(addr.strip().lower())
    # De-duplicate while preserving order.
    seen = set()
    uniq = []
    for addr in collected:
        if addr not in seen:
            uniq.append(addr)
            seen.add(addr)
    return uniq


def strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+\n", "\n", re.sub(r"[ \t]+", " ", text)).strip()


def call_openclaw(agent_id: str, from_addr: str, subject: str, body: str) -> str:
    prompt = (
        "You are responding to an inbound email. Keep response business-friendly and concise.\n\n"
        f"From: {from_addr}\n"
        f"Subject: {subject}\n\n"
        f"Body:\n{body[:MAX_BODY_CHARS]}"
    )

    if INVOKE_MODE == "docker_exec":
        cmd = [
            "docker",
            "exec",
            OPENCLAW_CONTAINER_NAME,
            "openclaw",
            "agent",
            "--agent",
            agent_id,
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
                return text.strip()
        if isinstance(data, dict):
            fallback = (((data.get("result") or {}).get("meta")) or {})
            if fallback:
                return json.dumps(fallback)[:REPLY_MAX_CHARS]
        return raw[:REPLY_MAX_CHARS]

    payload = {
        "agentId": agent_id,
        "name": "Email Interface",
        "message": prompt,
    }
    headers = {"Content-Type": "application/json"}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
        headers["x-openclaw-auth-token"] = AUTH_TOKEN
    resp = requests.post(HOOK_URL, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    try:
        data = resp.json()
    except Exception:
        return resp.text.strip()
    for key in ("response", "message", "output", "text", "result"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return str(data)


def get_graph_token() -> str:
    now = int(time.time())
    cached = TOKEN_CACHE.get("token", "")
    if cached and TOKEN_CACHE.get("expires_at", 0) > now + 60:
        return cached

    if not (GRAPH_TENANT_ID and GRAPH_CLIENT_ID and GRAPH_CLIENT_SECRET):
        raise RuntimeError(
            "EMAIL_GRAPH_TENANT_ID, EMAIL_GRAPH_CLIENT_ID, EMAIL_GRAPH_CLIENT_SECRET are required for EMAIL_PROVIDER=graph."
        )

    token_url = f"https://login.microsoftonline.com/{GRAPH_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": GRAPH_CLIENT_ID,
        "client_secret": GRAPH_CLIENT_SECRET,
        "scope": GRAPH_SCOPE,
    }
    resp = requests.post(token_url, data=data, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    token = payload["access_token"]
    TOKEN_CACHE["token"] = token
    TOKEN_CACHE["expires_at"] = now + int(payload.get("expires_in", 3600))
    return token


def graph_headers() -> dict:
    token = get_graph_token()
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def graph_list_unread_messages() -> list:
    if not GRAPH_USER_ID:
        raise RuntimeError("EMAIL_GRAPH_USER_ID (or EMAIL_IMAP_USER) is required for graph provider.")
    folder = IMAP_FOLDER if IMAP_FOLDER else "inbox"
    url = (
        f"{GRAPH_BASE_URL}/users/{GRAPH_USER_ID}/mailFolders/{folder}/messages"
        "?$filter=isRead eq false"
        "&$orderby=receivedDateTime asc"
        "&$top=20"
        "&$select=id,subject,from,replyTo,toRecipients,internetMessageHeaders,body,bodyPreview"
    )
    headers = graph_headers()
    headers["Prefer"] = 'outlook.body-content-type="text"'
    resp = requests.get(url, headers=headers, timeout=45)
    resp.raise_for_status()
    return resp.json().get("value", [])


def graph_mark_read(message_id: str) -> None:
    url = f"{GRAPH_BASE_URL}/users/{GRAPH_USER_ID}/messages/{message_id}"
    resp = requests.patch(url, headers=graph_headers(), json={"isRead": True}, timeout=30)
    resp.raise_for_status()


def graph_send_reply(to_addr: str, subject: str, response_text: str) -> None:
    if not EMAIL_REPLY_ENABLED:
        return
    if not GRAPH_USER_ID:
        log.warning("EMAIL_REPLY_ENABLED is true but EMAIL_GRAPH_USER_ID is empty.")
        return

    url = f"{GRAPH_BASE_URL}/users/{GRAPH_USER_ID}/sendMail"
    payload = {
        "message": {
            "subject": f"Re: {subject}" if subject else "Re: Your request",
            "body": {"contentType": "Text", "content": response_text[:REPLY_MAX_CHARS]},
            "toRecipients": [{"emailAddress": {"address": to_addr}}],
        },
        "saveToSentItems": True,
    }
    resp = requests.post(url, headers=graph_headers(), json=payload, timeout=45)
    resp.raise_for_status()


def send_reply(to_addr: str, subject: str, response_text: str) -> None:
    if not EMAIL_REPLY_ENABLED:
        return
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and SMTP_FROM):
        log.warning("SMTP reply is enabled but SMTP settings are incomplete; skipping reply.")
        return

    msg = EmailMessage()
    msg["Subject"] = f"Re: {subject}" if subject else "Re: Your request"
    msg["From"] = SMTP_FROM
    msg["To"] = to_addr
    msg.set_content(response_text[:REPLY_MAX_CHARS])

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


def connect_imap():
    if INSECURE_TLS:
        return imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
    return imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)


def process_once_imap() -> None:
    if not (IMAP_HOST and IMAP_USER and IMAP_PASS):
        raise RuntimeError("EMAIL_IMAP_HOST, EMAIL_IMAP_USER, EMAIL_IMAP_PASSWORD are required.")

    mail = connect_imap()
    try:
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select(IMAP_FOLDER)
        status, data = mail.search(None, "UNSEEN")
        if status != "OK":
            raise RuntimeError(f"IMAP search failed: {status}")
        ids = data[0].split() if data and data[0] else []
        if not ids:
            log.debug("No unread emails.")
            return

        for msg_id in ids:
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data:
                continue
            raw = msg_data[0][1]
            msg = message_from_bytes(raw)
            reply_to = parseaddr(msg.get("Reply-To", ""))[1]
            from_addr = reply_to or parseaddr(msg.get("From", ""))[1]
            to_header = msg.get("To", "")
            subject = msg.get("Subject", "(no subject)")
            body = extract_plain_text(msg).strip()
            agent_id = resolve_agent(to_header)

            if not body:
                log.info("Skipping empty email from %s subject=%s", from_addr or "unknown", subject)
                continue

            log.info("Routing email subject=%s to agent=%s", subject, agent_id)
            try:
                answer = call_openclaw(agent_id, from_addr, subject, body)
                send_reply(from_addr, subject, answer)
            except Exception as exc:
                log.exception("Failed processing email subject=%s: %s", subject, exc)
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def process_once_graph() -> None:
    messages = graph_list_unread_messages()
    if not messages:
        log.debug("No unread emails.")
        return

    for item in messages:
        message_id = item.get("id", "")
        if message_id and message_id in PROCESSED_GRAPH_IDS:
            continue
        subject = item.get("subject", "(no subject)")
        reply_to_list = item.get("replyTo", []) or []
        reply_to_addr = ""
        if reply_to_list:
            reply_to_addr = (((reply_to_list[0] or {}).get("emailAddress") or {}).get("address") or "").strip()
        from_addr = reply_to_addr or (((item.get("from") or {}).get("emailAddress") or {}).get("address") or "").strip()
        recipients = item.get("toRecipients", []) or []
        to_csv = ",".join(
            ((r.get("emailAddress") or {}).get("address") or "").strip()
            for r in recipients
            if (r.get("emailAddress") or {}).get("address")
        )
        header_recipients = extract_recipients_from_headers(item.get("internetMessageHeaders", []) or [])
        route_target = ",".join(header_recipients) if header_recipients else to_csv
        body_node = item.get("body") or {}
        body_text = str(body_node.get("content") or "").strip()
        if body_node.get("contentType", "").lower() == "html":
            body_text = strip_html(body_text)
        if not body_text:
            body_text = str(item.get("bodyPreview") or "").strip()
        agent_from_subject = resolve_agent_from_subject(subject)
        # Some O365 internal mails arrive as TNEF with empty body/bodyPreview.
        # If routing tag is in subject, still process with a synthetic body.
        if not body_text and agent_from_subject:
            body_text = f"(No body content available. Subject-only request.)\nSubject: {subject}"
        body_text = body_text[:MAX_BODY_CHARS]
        agent_id = agent_from_subject or resolve_agent(route_target)

        try:
            if body_text:
                if agent_from_subject:
                    log.info(
                        "Routing email subject=%s to agent=%s via_subject_rule recipients=%s",
                        subject,
                        agent_id,
                        route_target or "(none)",
                    )
                else:
                    log.info("Routing email subject=%s to agent=%s recipients=%s", subject, agent_id, route_target or "(none)")
                answer = call_openclaw(agent_id, from_addr, subject, body_text)
                graph_send_reply(from_addr, subject, answer)
            if message_id:
                remember_processed_id(message_id)
                if GRAPH_MARK_READ:
                    try:
                        graph_mark_read(message_id)
                    except Exception as exc:
                        log.warning("Could not mark message as read (continuing): %s", exc)
        except Exception as exc:
            log.exception("Failed processing Graph email subject=%s: %s", subject, exc)


def main() -> None:
    if not EMAIL_ENABLED:
        log.warning("EMAIL_CHANNEL_ENABLED is false; sleeping forever.")
        while True:
            time.sleep(3600)

    if EMAIL_PROVIDER not in {"imap", "graph"}:
        raise RuntimeError("EMAIL_PROVIDER must be either 'imap' or 'graph'.")

    load_processed_ids()
    log.info("Email bridge started. provider=%s interval=%ss folder=%s", EMAIL_PROVIDER, POLL_SECONDS, IMAP_FOLDER)
    while True:
        try:
            if EMAIL_PROVIDER == "graph":
                process_once_graph()
            else:
                process_once_imap()
        except Exception as exc:
            log.exception("Email poll iteration failed: %s", exc)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
