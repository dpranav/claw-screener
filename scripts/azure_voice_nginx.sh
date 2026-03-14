set -eu

sudo tee /etc/nginx/sites-available/voice.proqaai.net.conf >/dev/null <<'EOF'
server {
    listen 80;
    server_name voice.proqaai.net;

    location / {
        proxy_pass http://127.0.0.1:8787;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/voice.proqaai.net.conf /etc/nginx/sites-enabled/voice.proqaai.net.conf
sudo nginx -t
sudo systemctl reload nginx
curl -s http://127.0.0.1:8787/health
