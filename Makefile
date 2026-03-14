.PHONY: help package bootstrap deploy harden up down restart logs ps up-teams logs-teams

SHELL := /bin/bash

help:
	@echo "Targets:"
	@echo "  make package   - Build deployable tar.gz in dist/"
	@echo "  make bootstrap - Run full local bootstrap.sh setup"
	@echo "  make deploy    - Alias for bootstrap"
	@echo "  make harden    - Run VM hardening script (nginx, auth, ufw)"
	@echo "  make up        - docker compose up -d --build"
	@echo "  make down      - docker compose down"
	@echo "  make restart   - docker compose restart"
	@echo "  make logs      - Tail OpenClaw + channel bridge logs"
	@echo "  make up-teams  - Build/start Teams real-time bot only"
	@echo "  make logs-teams- Tail Teams real-time bot logs"
	@echo "  make ps        - Show docker compose status"

package:
	@chmod +x ./create_deploy_package.sh
	@./create_deploy_package.sh

bootstrap:
	@chmod +x ./bootstrap.sh
	@./bootstrap.sh

deploy: bootstrap

harden:
	@chmod +x ./hardening.sh
	@sudo ./hardening.sh

up:
	@docker compose up -d --build

down:
	@docker compose down

restart:
	@docker compose restart

logs:
	@docker compose logs --tail 120 openclaw email-bridge voice-bridge teams-realtime-bot

up-teams:
	@docker compose up -d --build teams-realtime-bot

logs-teams:
	@docker compose logs --tail 120 teams-realtime-bot

ps:
	@docker compose ps
