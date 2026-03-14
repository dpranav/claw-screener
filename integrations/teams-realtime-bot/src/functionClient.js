async function postJson({ url, body, headers = {}, timeoutMs = 15000 }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const raw = await resp.text();
    let data = {};
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      data = { raw };
    }
    if (!resp.ok) {
      const err = new Error(`HTTP ${resp.status}`);
      err.status = resp.status;
      err.data = data;
      throw err;
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

async function forwardTranscriptChunk({
  functionUrl,
  integrationToken,
  timeoutMs,
  sessionId,
  text,
  final = false,
}) {
  return postJson({
    url: functionUrl,
    timeoutMs,
    headers: {
      "x-integration-token": integrationToken,
    },
    body: {
      sessionId,
      text,
      final: Boolean(final),
    },
  });
}

async function postTipToTeamsWebhook({ webhookUrl, sessionId, tip, timeoutMs }) {
  if (!webhookUrl) return { posted: false, reason: "no_webhook_configured" };
  const payload = {
    text: `AI Sales Coach (${sessionId})\n${tip}`,
  };
  await postJson({
    url: webhookUrl,
    body: payload,
    timeoutMs,
  });
  return { posted: true };
}

module.exports = {
  forwardTranscriptChunk,
  postTipToTeamsWebhook,
};

