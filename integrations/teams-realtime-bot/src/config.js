const toInt = (value, fallback) => {
  const n = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(n) ? n : fallback;
};

const config = {
  port: toInt(process.env.PORT, 7090),
  logLevel: process.env.LOG_LEVEL || "info",
  botIngestToken: (process.env.BOT_INGEST_TOKEN || "").trim(),
  functionUrl: (process.env.TEAMS_TRANSCRIPT_FUNCTION_URL || "").trim(),
  integrationToken: (process.env.INTEGRATION_TOKEN || "").trim(),
  requestTimeoutMs: toInt(process.env.REQUEST_TIMEOUT_MS, 15000),
  tipMinSecondsBetweenPosts: toInt(process.env.TIP_MIN_SECONDS_BETWEEN_POSTS, 25),
  tipMinChars: toInt(process.env.TIP_MIN_CHARS, 20),
  tipDedupeWindow: toInt(process.env.TIP_DEDUPE_WINDOW, 5),
  teamsTipWebhookUrl: (process.env.TEAMS_TIP_WEBHOOK_URL || "").trim(),
  mediaFlushSeconds: toInt(process.env.MEDIA_FLUSH_SECONDS, 4),
  mediaMaxChunkChars: toInt(process.env.MEDIA_MAX_CHARS_PER_CHUNK, 1200),
  mediaOverlapWords: toInt(process.env.MEDIA_OVERLAP_WORDS, 12),
  sttAdapter: (process.env.STT_ADAPTER || "passthrough").trim(),
  azureSpeechKey: (process.env.AZURE_SPEECH_KEY || "").trim(),
  azureSpeechRegion: (process.env.AZURE_SPEECH_REGION || "").trim(),
  sttLanguage: (process.env.STT_LANGUAGE || "en-US").trim(),
  sttSampleRateHz: toInt(process.env.STT_SAMPLE_RATE_HZ, 16000),
  sttBitsPerSample: toInt(process.env.STT_BITS_PER_SAMPLE, 16),
  sttChannels: toInt(process.env.STT_CHANNELS, 1),
  sttMinConfidence: Number.parseFloat(process.env.STT_MIN_CONFIDENCE || "0"),
};

function validateConfig() {
  const missing = [];
  if (!config.functionUrl) missing.push("TEAMS_TRANSCRIPT_FUNCTION_URL");
  if (!config.integrationToken) missing.push("INTEGRATION_TOKEN");
  if (missing.length) {
    throw new Error(`Missing required environment variables: ${missing.join(", ")}`);
  }
}

module.exports = { config, validateConfig };

