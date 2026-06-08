SSH_HOST ?= de-rarecloud
REMOTE_DIR ?= /opt/news-summarizer
SERVICE ?= news-summarizer
SSH := ssh $(SSH_HOST)

.PHONY: help deploy restart start stop status logs logs-follow ssh push-env pull-state

help:
	@echo "Targets:"
	@echo "  deploy       git pull on VPS, uv sync, restart service (requires pushed commits)"
	@echo "  restart      restart the systemd service"
	@echo "  start        start the service"
	@echo "  stop         stop the service"
	@echo "  status       show systemctl status"
	@echo "  logs         show last 100 journal lines"
	@echo "  logs-follow  tail -f journal"
	@echo "  ssh          open SSH session on the VPS in $(REMOTE_DIR)"
	@echo "  push-env     copy local .env to VPS (destructive; confirm before running)"
	@echo "  pull-state   fetch VPS state files to ./state-backup/"

deploy:
	@if ! git -C . diff --quiet HEAD origin/main -- 2>/dev/null; then \
		echo ">>> WARNING: local HEAD differs from origin/main. Push first."; \
		git log --oneline origin/main..HEAD; \
		exit 1; \
	fi
	$(SSH) 'set -e; cd $(REMOTE_DIR) && git fetch && git reset --hard origin/main && /root/.local/bin/uv sync --all-extras && systemctl restart $(SERVICE) && sleep 2 && systemctl is-active $(SERVICE)'
	@echo ">>> deployed. tail logs with: make logs"

restart:
	$(SSH) 'systemctl restart $(SERVICE) && systemctl is-active $(SERVICE)'

start:
	$(SSH) 'systemctl start $(SERVICE) && systemctl is-active $(SERVICE)'

stop:
	$(SSH) 'systemctl stop $(SERVICE)'

status:
	$(SSH) 'systemctl status $(SERVICE) --no-pager'

logs:
	$(SSH) 'journalctl -u $(SERVICE) -n 100 --no-pager'

logs-follow:
	$(SSH) 'journalctl -u $(SERVICE) -f'

ssh:
	$(SSH) -t 'cd $(REMOTE_DIR); exec $$SHELL -l'

push-env:
	@echo ">>> pushing local .env to $(SSH_HOST):$(REMOTE_DIR)/.env (Ctrl-C to abort)"
	@sleep 3
	scp .env $(SSH_HOST):$(REMOTE_DIR)/.env
	$(SSH) 'chmod 600 $(REMOTE_DIR)/.env && chown root:root $(REMOTE_DIR)/.env'
	@echo ">>> done. Restart service to pick up env changes: make restart"

pull-state:
	mkdir -p state-backup
	scp $(SSH_HOST):$(REMOTE_DIR)/.last_check state-backup/
	scp $(SSH_HOST):$(REMOTE_DIR)/.seen_urls state-backup/
	scp $(SSH_HOST):$(REMOTE_DIR)/.bale_retry_queue state-backup/
	-scp $(SSH_HOST):$(REMOTE_DIR)/.cadence_state state-backup/
	@echo ">>> state files saved to ./state-backup/"
