COMPOSE = docker compose -f docker/docker-compose.yml

.PHONY: dev test up down logs ps health metrics alert-test

dev:
	uvicorn app.main:app --reload --port 8000

test:
	pytest tests/ -v

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f app

ps:
	$(COMPOSE) ps

health:
	bash scripts/health-check.sh

metrics:
	@curl -s http://127.0.0.1:8000/metrics | grep "^agent_"

alert-test:
	@curl -s -X POST http://localhost:9093/api/v2/alerts \
	  -H 'Content-Type: application/json' \
	  -d '[{"labels":{"alertname":"TestEmail","severity":"critical"},"annotations":{"summary":"Prueba","description":"Pipeline operativo."},"startsAt":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}]' \
	  && echo "Alerta disparada → revisa tu email"
