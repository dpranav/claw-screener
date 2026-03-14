set -eu

sudo tee /etc/nginx/sites-available/teamsrt.proqaai.net.conf >/dev/null <<'EOF'
server {
    listen 80;
    server_name teamsrt.proqaai.net;

    location / {
        proxy_pass http://127.0.0.1:7090;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/teamsrt.proqaai.net.conf /etc/nginx/sites-enabled/teamsrt.proqaai.net.conf
sudo nginx -t
sudo systemctl reload nginx
curl -s http://127.0.0.1:7090/health

