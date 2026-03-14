set -eu

sudo certbot --nginx -d voice.proqaai.net --redirect --agree-tos -m info@ucan.ai --non-interactive
