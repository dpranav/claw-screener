class MediaBuffer {
  constructor({ flushSeconds, maxChunkChars, overlapWords }) {
    this.flushMs = Math.max(1, Number(flushSeconds || 4)) * 1000;
    this.maxChunkChars = Math.max(100, Number(maxChunkChars || 1200));
    this.overlapWords = Math.max(0, Number(overlapWords || 12));
    this.sessions = new Map();
  }

  ensure(sessionId) {
    if (!this.sessions.has(sessionId)) {
      this.sessions.set(sessionId, {
        lastFlushMs: Date.now(),
        text: "",
      });
    }
    return this.sessions.get(sessionId);
  }

  ingest(sessionId, text) {
    const entry = this.ensure(sessionId);
    const trimmed = String(text || "").trim();
    if (!trimmed) return { bufferedChars: entry.text.length, shouldFlush: false };

    entry.text = entry.text ? `${entry.text} ${trimmed}` : trimmed;
    const ageMs = Date.now() - entry.lastFlushMs;
    const shouldFlush = ageMs >= this.flushMs || entry.text.length >= this.maxChunkChars;
    return { bufferedChars: entry.text.length, shouldFlush };
  }

  flush(sessionId, { final = false } = {}) {
    const entry = this.ensure(sessionId);
    const payload = entry.text.trim();
    if (!payload) {
      return { hasChunk: false, text: "", final: Boolean(final), reason: "empty_buffer" };
    }

    entry.lastFlushMs = Date.now();

    const overlap = this.extractOverlap(payload);
    entry.text = final ? "" : overlap;

    return {
      hasChunk: true,
      text: payload,
      final: Boolean(final),
      bufferedRemainderChars: entry.text.length,
    };
  }

  extractOverlap(text) {
    if (!this.overlapWords) return "";
    const words = text.split(/\s+/).filter(Boolean);
    if (words.length <= this.overlapWords) return text;
    return words.slice(-this.overlapWords).join(" ");
  }
}

module.exports = { MediaBuffer };

