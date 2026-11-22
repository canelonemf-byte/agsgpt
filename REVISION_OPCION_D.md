# Revisión de la opción D · agsgpt

> Autoría: Lázaro López Paz, El Prat de Llobregat, Barcelona, España, con asistencia de IA · ORCID 0000-0001-8601-1963 · Licencia del documento: CC BY 4.0

Este árbol sustituye al `setup.sh` pegado. No hace falta ejecutar el script: copia los archivos en `/workspace/agsgpt`, con copias `.bak` de lo que ya exista.

## Cambios respecto a la versión pegada

- **Caso de contexto excedido.** Trunca los mensajes y reintenta una vez en el mismo modelo. El reintento no consume `max_retries`. Si vuelve a fallar, pasa al siguiente modelo.
- **El contexto excedido no abre el circuito.** Antes, cada error de contexto contaba como fallo del proveedor.
- **`timeout` se pasa a `call_fn`.** Antes `ModelConfig.timeout` no se usaba.
- **Una sola versión de `fallback.py` y de los tests.** La de tipos es la canónica.
- **Tests de contexto ajustados.** El umbral del test pasa de 3 a 4 mensajes, porque un truncado deja el 30 % de los mensajes no sistema y con 3 no cabía. Revisa si te parece bien.
- **Tests nuevos:** reintento transitorio con `max_retries`, un solo reintento por contexto, contexto que no abre el circuito y paso de `timeout`.
- **Makefile con tabuladores reales** en las recetas.
- **`pytest` y `httpx` salen de `requirements.txt`** y van a `requirements-dev.txt`.
- **`.dockerignore` nuevo.** Evita copiar `.env`, `monitoring/secrets/` y `tests/` a la imagen. Antes `COPY . .` los incluía.
- **Grafana sin contraseña por defecto.** `GRAFANA_PASSWORD` es obligatoria en `.env`.
- **`scripts/set-smtp-password.sh`.** Pide la app password sin eco y la guarda con permisos 600.

## Cómo aplicarlo en tu equipo

1. Copia cada archivo en `/workspace/agsgpt` con un `.bak` previo si ya existe.
2. `pip install -r requirements-dev.txt`
3. `cp .env.example .env` y rellena las claves y `GRAFANA_PASSWORD`.
4. `bash scripts/set-smtp-password.sh`
5. `make test` y revisa que pasan los 12 tests.
6. `make up`, después `make ps`, `make health` y `make metrics`.

## Verificado en esta revisión

- Los 12 tests pasan, pero con un sustituto de `pytest` y otro de `prometheus_client`. **Ejecuta `make test` en tu equipo** con las dependencias reales.
- Todos los `.py` compilan. Los scripts pasan `bash -n`. Los YAML son válidos.
- El Makefile tiene tabuladores reales, y `make -n` reconoce las recetas.
- No se ha ejecutado `docker compose`, ni `main.py` con FastAPI, ni los clientes reales de OpenAI y Anthropic.

## Pendiente, sin decidir

- **Imágenes sin versión fija.** Prometheus, Alertmanager y Grafana siguen en `latest`. Conviene fijar versiones tras comprobarlas.
- **Un circuito por proceso.** Con `2 × CPU + 1` workers de gunicorn, cada worker tiene su propio estado. La detección de un corte es más lenta.
- **Cron cada 5 minutos.** El `health-check.sh` envía un email en cada fallo, sin deduplicación.
- **Alertmanager.** Comprueba que tu versión admite `smtp_auth_password_file`.
