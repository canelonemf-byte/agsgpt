# agsgpt · Opción D

Servicio FastAPI con una cadena de fallback entre modelos de lenguaje (OpenAI, Anthropic), circuit breaker por proveedor, métricas Prometheus, alertas (Alertmanager y health-check) y despliegue con Docker Compose o systemd.

- **Autoría:** Lázaro López Paz, El Prat de Llobregat, Barcelona, España, con asistencia de inteligencia artificial. ORCID [0000-0001-8601-1963](https://orcid.org/0000-0001-8601-1963).
- **Licencias:** código MIT (ver `LICENSE`); documentación CC BY 4.0.

## Estructura

| Ruta | Contenido |
|---|---|
| `app/` | API (`main.py`), agente, cadena de fallback y circuit breaker (`fallback.py`), métricas y clientes LLM |
| `tests/` | Tests de la cadena de fallback (`pytest`) |
| `monitoring/` | Prometheus, reglas de alerta y Alertmanager |
| `docker/` | `Dockerfile` y `docker-compose.yml` |
| `systemd/` | Unidad `agsgpt.service` |
| `scripts/` | Arranque, health-check y guardado de la contraseña SMTP |

## Uso rápido

```bash
pip install -r requirements-dev.txt
cp .env.example .env            # rellena las claves y GRAFANA_PASSWORD
bash scripts/set-smtp-password.sh
make test                        # 12 tests
make up && make ps && make health
```

`.env` y `monitoring/secrets/` están excluidos de git. Detalle de cambios y pendientes: `REVISION_OPCION_D.md`.

## Estado verificado (2026-11-22)

- 12 tests pasan con las dependencias reales (`pytest`, `prometheus-client`, `fastapi`).
- Pendiente: no se ha ejecutado `docker compose` ni llamadas reales a OpenAI o Anthropic; imágenes de monitorización en `latest` sin fijar.
