class SessionStore {
  constructor() {
    this.state = new Map();
  }

  ensure(sessionId) {
    if (!this.state.has(sessionId)) {
      this.state.set(sessionId, {
        lastTips: [],
        lastPostedAtMs: 0,
      });
    }
    return this.state.get(sessionId);
  }

  shouldPostTip({ sessionId, tip, nowMs, minSecondsBetweenPosts, dedupeWindow }) {
    const entry = this.ensure(sessionId);
    if (!tip || !tip.trim()) return false;

    const elapsedMs = nowMs - entry.lastPostedAtMs;
    if (elapsedMs < minSecondsBetweenPosts * 1000) return false;

    const normalized = tip.trim().toLowerCase();
    if (entry.lastTips.includes(normalized)) return false;

    entry.lastPostedAtMs = nowMs;
    entry.lastTips.unshift(normalized);
    entry.lastTips = entry.lastTips.slice(0, Math.max(1, dedupeWindow));
    return true;
  }
}

module.exports = { SessionStore };

