require("dotenv").config();

const express = require("express");
const { config, validateConfig } = require("./config");
const { SessionStore } = require("./sessionStore");
const { MediaBuffer } = require("./mediaBuffer");
const { createSttAdapter } = require("./sttAdapter");
const { forwardTranscriptChunk, postTipToTeamsWebhook } = require("./functionClient");

validateConfig();

const app = express();
const store = new SessionStore();
const mediaBuffer = new MediaBuffer({
  flushSeconds: config.mediaFlushSeconds,
  maxChunkChars: config.mediaMaxChunkChars,
  overlapWords: config.mediaOverlapWords,
});
const sttAdapter = createSttAdapter(config);

app.use(express.json({ limit: "1mb" }));

function info(message, extra = {}) {
  if (config.logLevel === "debug" || config.logLevel === "info") {
    console.log(JSON.stringify({ level: "info", message, ...extra }));
  }
}

function error(message, extra = {}) {
  console.error(JSON.stringify({ level: "error", message, ...extra }));
}

function requireBotToken(req, res, next) {
  if (!config.botIngestToken) return next();
  const supplied = String(req.header("x-bot-token") || "");
  if (supplied !== config.botIngestToken) {
    return res.status(401).json({ ok: false, error: "unauthorized" });
  }
  return next();
}

app.get("/health", (_req, res) => {
  res.json({ ok: true, service: "teams-realtime-bot-starter" });
});

async function processTranscriptChunk({ sessionId, text, final }) {
  const fnResp = await forwardTranscriptChunk({
    functionUrl: config.functionUrl,
    integrationToken: config.integrationToken,
    timeoutMs: config.requestTimeoutMs,
    sessionId,
    text,
    final,
  });

  const tip = String(fnResp.tip || "").trim();
  let posted = false;
  let postReason = "tip_not_posted";
  if (tip.length >= config.tipMinChars) {
    const canPost = store.shouldPostTip({
      sessionId,
      tip,
      nowMs: Date.now(),
      minSecondsBetweenPosts: config.tipMinSecondsBetweenPosts,
      dedupeWindow: config.tipDedupeWindow,
    });
    if (canPost) {
      const postResult = await postTipToTeamsWebhook({
        webhookUrl: config.teamsTipWebhookUrl,
        sessionId,
        tip,
        timeoutMs: config.requestTimeoutMs,
      });
      posted = Boolean(postResult.posted);
      postReason = posted ? "posted" : String(postResult.reason || "not_posted");
    } else {
      postReason = "throttled_or_duplicate";
    }
  } else if (tip) {
    postReason = "tip_too_short";
  }

  return {
    tip,
    posted,
    postReason,
    voiceResponse: fnResp.voiceResponse || null,
  };
}

app.post("/api/transcript-chunk", requireBotToken, async (req, res) => {
  try {
    const sessionId = String(req.body.sessionId || "").trim();
    const text = String(req.body.text || "").trim();
    const final = Boolean(req.body.final);

    if (!sessionId) return res.status(400).json({ ok: false, error: "sessionId is required" });
    if (!text) return res.status(400).json({ ok: false, error: "text is required" });

    const processed = await processTranscriptChunk({ sessionId, text, final });

    info("chunk_processed", {
      sessionId,
      textLen: text.length,
      hasTip: Boolean(processed.tip),
      posted: processed.posted,
      postReason: processed.postReason,
      final,
    });

    return res.json({
      ok: true,
      sessionId,
      tip: processed.tip,
      posted: processed.posted,
      postReason: processed.postReason,
      voiceResponse: processed.voiceResponse,
    });
  } catch (err) {
    error("chunk_failed", {
      error: String(err?.message || err),
      status: err?.status,
      data: err?.data,
    });
    return res.status(502).json({
      ok: false,
      error: "forwarding_failed",
      details: String(err?.message || err),
    });
  }
});

app.post("/api/media-frame", requireBotToken, async (req, res) => {
  try {
    const sessionId = String(req.body.sessionId || "").trim();
    const final = Boolean(req.body.final);
    if (!sessionId) return res.status(400).json({ ok: false, error: "sessionId is required" });

    const stt = await sttAdapter.transcribeFrame({
      sessionId,
      text: req.body.text,
      audioBase64: req.body.audioBase64,
      contentType: req.body.contentType,
      sequence: req.body.sequence,
      final,
      speakerId: req.body.speakerId,
      timestamp: req.body.timestamp,
    });

    const transcribedText = String(stt?.text || "").trim();
    if (!transcribedText && !final) {
      return res.json({
        ok: true,
        sessionId,
        accepted: true,
        transcribed: false,
        provider: stt?.provider || "unknown",
        reason: "empty_transcript_from_adapter",
      });
    }

    const ingest = mediaBuffer.ingest(sessionId, transcribedText);
    const shouldFlushNow = Boolean(final || ingest.shouldFlush);
    if (!shouldFlushNow) {
      return res.json({
        ok: true,
        sessionId,
        accepted: true,
        transcribed: Boolean(transcribedText),
        provider: stt?.provider || "unknown",
        bufferedChars: ingest.bufferedChars,
        flushed: false,
      });
    }

    const flushed = mediaBuffer.flush(sessionId, { final });
    if (!flushed.hasChunk) {
      return res.json({
        ok: true,
        sessionId,
        accepted: true,
        transcribed: Boolean(transcribedText),
        provider: stt?.provider || "unknown",
        flushed: false,
        reason: flushed.reason,
      });
    }

    const processed = await processTranscriptChunk({
      sessionId,
      text: flushed.text,
      final: flushed.final,
    });

    return res.json({
      ok: true,
      sessionId,
      accepted: true,
      transcribed: Boolean(transcribedText),
      provider: stt?.provider || "unknown",
      flushed: true,
      chunkChars: flushed.text.length,
      tip: processed.tip,
      posted: processed.posted,
      postReason: processed.postReason,
      voiceResponse: processed.voiceResponse,
    });
  } catch (err) {
    error("media_frame_failed", {
      error: String(err?.message || err),
      status: err?.status,
      data: err?.data,
    });
    return res.status(502).json({
      ok: false,
      error: "media_frame_failed",
      details: String(err?.message || err),
    });
  }
});

app.post("/api/media-flush", requireBotToken, async (req, res) => {
  try {
    const sessionId = String(req.body.sessionId || "").trim();
    const final = Boolean(req.body.final);
    if (!sessionId) return res.status(400).json({ ok: false, error: "sessionId is required" });

    const flushed = mediaBuffer.flush(sessionId, { final });
    if (!flushed.hasChunk) {
      return res.json({ ok: true, sessionId, flushed: false, reason: flushed.reason });
    }

    const processed = await processTranscriptChunk({
      sessionId,
      text: flushed.text,
      final: flushed.final,
    });

    return res.json({
      ok: true,
      sessionId,
      flushed: true,
      chunkChars: flushed.text.length,
      tip: processed.tip,
      posted: processed.posted,
      postReason: processed.postReason,
      voiceResponse: processed.voiceResponse,
    });
  } catch (err) {
    error("media_flush_failed", {
      error: String(err?.message || err),
      status: err?.status,
      data: err?.data,
    });
    return res.status(502).json({
      ok: false,
      error: "media_flush_failed",
      details: String(err?.message || err),
    });
  }
});

app.listen(config.port, () => {
  info("service_started", { port: config.port });
});

