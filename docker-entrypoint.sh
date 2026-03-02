#!/bin/bash
set -e

if [ ! -f /root/.openclaw/openclaw.json ]; then
  echo "First run — initializing OpenClaw..."
  openclaw onboard --non-interactive --accept-risk 2>&1 || true
fi

if ! command -v uv &>/dev/null; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh 2>/dev/null
  export PATH="/root/.local/bin:$PATH"
fi

echo "Validating config..."
node -e "
  const fs = require('fs'), p = '/root/.openclaw/openclaw.json';
  try {
    const c = JSON.parse(fs.readFileSync(p,'utf8'));
    const stale = [
      ['commands', 'ownerDisplay'],
      ['channels.telegram', 'streaming'],
    ];
    let changed = false;
    for (const [path, key] of stale) {
      const parts = path.split('.');
      let obj = c;
      for (const part of parts) { obj = obj && obj[part]; }
      if (obj && obj[key] !== undefined) {
        delete obj[key];
        changed = true;
        console.log('  removed ' + path + '.' + key);
      }
    }
    if (changed) fs.writeFileSync(p, JSON.stringify(c, null, 2));
    else console.log('  config OK');
  } catch(e) { console.log('  skip:', e.message); }
" || true

openclaw config set gateway.bind loopback 2>/dev/null || true
openclaw config set gateway.port "${OPENCLAW_PORT:-18789}" 2>/dev/null || true
openclaw config set gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback true 2>/dev/null || true

if [ -n "$OPENCLAW_MODEL" ]; then
  openclaw models set "$OPENCLAW_MODEL" 2>/dev/null || true
fi

if [ -n "$OPENCLAW_AUTH_TOKEN" ]; then
  openclaw config set gateway.auth.token "$OPENCLAW_AUTH_TOKEN" 2>/dev/null || true
fi

if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
  echo "Configuring Telegram channel..."
  openclaw config set channels.telegram.botToken "$TELEGRAM_BOT_TOKEN" 2>/dev/null || true

  if [ -n "$TELEGRAM_ALLOWED_IDS" ]; then
    IFS=',' read -ra IDS <<< "$TELEGRAM_ALLOWED_IDS"
    IDX=0
    for ID in "${IDS[@]}"; do
      ID=$(echo "$ID" | xargs)
      openclaw config set "channels.telegram.allowFrom[$IDX]" "tg:$ID" 2>/dev/null || true
      IDX=$((IDX + 1))
    done
  fi

  # Set dmPolicy after allowFrom so allowlist validation can pass.
  openclaw config set channels.telegram.dmPolicy "${TELEGRAM_DM_POLICY:-pairing}" 2>/dev/null || true
  echo "Telegram channel configured (dmPolicy=${TELEGRAM_DM_POLICY:-pairing})"
fi

echo "Approving all pending device pairings..."
openclaw devices approve --all 2>/dev/null || true

echo "Starting OpenClaw gateway on port ${OPENCLAW_PORT:-18789}..."
exec openclaw gateway run \
  --port "${OPENCLAW_PORT:-18789}" \
  --bind lan \
  "$@"
