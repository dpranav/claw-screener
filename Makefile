.PHONY: help package bootstrap deploy harden up down restart logs ps

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
	@echo "  make logs      - Tail OpenClaw container logs"
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
	@docker logs openclaw-screener --tail 120

ps:
	@docker compose ps
