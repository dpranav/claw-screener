#!/usr/bin/env bash
set -euo pipefail

# VM-side hardening script for OpenClaw deployment.
# - Installs nginx + basic tools
# - Proxies OpenClaw/ClawMetry behind nginx
# - Optionally enables TLS via certbot
# - Restricts docker-compose published ports to localhost
# - Enables OpenClaw auth token in .env
# - Enables UFW for 22/80/443
#
# Example:
#   sudo ./hardening.sh --domain bot.example.com --email you@example.com --with-certbot

DOMAIN=""
EMAIL=""
WITH_CERTBOT=false
PROJECT_DIR="${PROJECT_DIR:-$HOME/apps/claw-screener}"
NGINX_CONF="/etc/nginx/sites-available/openclaw.conf"
HTPASSWD_FILE="/etc/nginx/.htpasswd"
BASIC_AUTH_USER="${BASIC_AUTH_USER:-openclawadmin}"

log() { printf "\n[harden] %s\n" "$*"; }
die() { printf "\n[harden][error] %s\n" "$*" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --domain <fqdn>         Public domain (required for certbot mode)
  --email <email>         Let's Encrypt email (required for certbot mode)
  --with-certbot          Run certbot nginx installer and enforce HTTPS redirect
  --project-dir <path>    Path to project directory (default: $PROJECT_DIR)
  --auth-user <name>      HTTP basic auth username (default: $BASIC_AUTH_USER)
  -h, --help              Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="${2:-}"; shift 2;;
    --email) EMAIL="${2:-}"; shift 2;;
    --with-certbot) WITH_CERTBOT=true; shift;;
    --project-dir) PROJECT_DIR="${2:-}"; shift 2;;
    --auth-user) BASIC_AUTH_USER="${2:-}"; shift 2;;
    -h|--help) usage; exit 0;;
    *) die "Unknown argument: $1";;
  esac
done

[[ -d "$PROJECT_DIR" ]] || die "Project directory not found: $PROJECT_DIR"
[[ -f "$PROJECT_DIR/docker-compose.yml" ]] || die "docker-compose.yml not found in $PROJECT_DIR"
[[ -f "$PROJECT_DIR/.env" ]] || die ".env not found in $PROJECT_DIR"

if $WITH_CERTBOT; then
  [[ -n "$DOMAIN" ]] || die "--domain is required when --with-certbot is used"
  [[ -n "$EMAIL" ]] || die "--email is required when --with-certbot is used"
fi

if [[ $EUID -ne 0 ]]; then
  die "Run as root (sudo)."
fi

install_packages() {
  log "Installing nginx, certbot, ufw, and utilities..."
  apt-get update
  apt-get install -y nginx certbot python3-certbot-nginx apache2-utils ufw
}

ensure_auth_token() {
  log "Ensuring OPENCLAW_AUTH_TOKEN exists in .env..."
  local env_file="$PROJECT_DIR/.env"
  local token
  token="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
  python3 - "$env_file" "$token" <<'PY'
from pathlib import Path
import re
import sys

env_path = Path(sys.argv[1])
token = sys.argv[2]
text = env_path.read_text(encoding="utf-8")

if re.search(r'^\s*OPENCLAW_AUTH_TOKEN\s*=', text, flags=re.MULTILINE):
    text = re.sub(r'^\s*OPENCLAW_AUTH_TOKEN\s*=.*$', f'OPENCLAW_AUTH_TOKEN={token}', text, flags=re.MULTILINE)
else:
    if not text.endswith('\n'):
        text += '\n'
    text += f'OPENCLAW_AUTH_TOKEN={token}\n'

env_path.write_text(text, encoding="utf-8")
PY
}

bind_ports_to_localhost() {
  log "Restricting docker-compose published ports to localhost..."
  local compose_file="$PROJECT_DIR/docker-compose.yml"
  python3 - "$compose_file" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
text = p.read_text(encoding="utf-8")

text = text.replace('"${OPENCLAW_PORT:-18789}:18789"', '"127.0.0.1:${OPENCLAW_PORT:-18789}:18789"')
text = text.replace('"8900:8900"', '"127.0.0.1:8900:8900"')

p.write_text(text, encoding="utf-8")
PY
}

configure_nginx() {
  log "Configuring nginx reverse proxy..."
  local server_name="${DOMAIN:-_}"
  cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    server_name ${server_name};

    location / {
        proxy_pass http://127.0.0.1:18789;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /clawmetry/ {
        auth_basic "Restricted";
        auth_basic_user_file ${HTPASSWD_FILE};
        proxy_pass http://127.0.0.1:8900/;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

  ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/openclaw.conf
  rm -f /etc/nginx/sites-enabled/default
}

setup_basic_auth() {
  log "Setting nginx basic auth for /clawmetry ..."
  if [[ ! -f "$HTPASSWD_FILE" ]]; then
    printf "\nCreate password for basic auth user '%s'\n" "$BASIC_AUTH_USER"
    htpasswd -c "$HTPASSWD_FILE" "$BASIC_AUTH_USER"
  else
    printf "\nBasic auth file exists. Update/add user '%s' now? [y/N]: " "$BASIC_AUTH_USER"
    read -r ans
    if [[ "${ans,,}" == "y" ]]; then
      htpasswd "$HTPASSWD_FILE" "$BASIC_AUTH_USER"
    fi
  fi
}

restart_services() {
  log "Restarting app stack and nginx..."
  (cd "$PROJECT_DIR" && docker compose up -d --build)
  nginx -t
  systemctl enable nginx
  systemctl restart nginx
}

configure_firewall() {
  log "Configuring UFW (allow 22, 80, 443)..."
  ufw allow 22/tcp
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw --force enable
}

run_certbot() {
  if ! $WITH_CERTBOT; then
    return
  fi
  log "Running certbot for ${DOMAIN}..."
  certbot --nginx -d "$DOMAIN" --redirect --agree-tos -m "$EMAIL" --non-interactive
}

health_check() {
  log "Health checks..."
  curl -s -o /dev/null -w "OpenClaw local HTTP %{http_code}\n" "http://127.0.0.1:18789/" || true
  curl -s -o /dev/null -w "Nginx HTTP %{http_code}\n" "http://127.0.0.1/" || true
}

summary() {
  cat <<EOF

[harden] Complete.

What was applied:
- OpenClaw auth token enforced in .env
- Docker published ports bound to localhost
- Nginx reverse proxy enabled
- Basic auth on /clawmetry
- UFW enabled (22, 80, 443)
$( $WITH_CERTBOT && echo "- TLS certificate installed for ${DOMAIN}" || true )

Endpoints:
- OpenClaw via nginx: http://${DOMAIN:-<server-ip-or-domain>}/
- ClawMetry via nginx: http://${DOMAIN:-<server-ip-or-domain>}/clawmetry/

Recommended Azure NSG:
- Allow inbound 22, 80, 443 only
- Remove/deny public 18789 and 8900
EOF
}

install_packages
ensure_auth_token
bind_ports_to_localhost
configure_nginx
setup_basic_auth
restart_services
configure_firewall
run_certbot
health_check
summary
