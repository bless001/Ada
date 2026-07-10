setup:
	python scripts/generate_env.py
	mkdir -p models workspace

up:
	docker compose up -d --build

up-llm:
	docker compose --profile llm up -d --build

logs:
	docker compose logs -f openproject-provision agent-webhook agent-worker

provision-logs:
	docker compose logs openproject-provision

down:
	docker compose down

clean:
	docker compose down -v

restart-provision:
	docker compose rm -f openproject-provision || true
	docker compose up openproject-provision

test-webhook:
	bash scripts/test_webhook.sh

show-token:
	bash scripts/show_bot_token.sh
