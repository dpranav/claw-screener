set -eu

sudo certbot --nginx -d teamsrt.proqaai.net --redirect --agree-tos -m info@ucan.ai --non-interactive

