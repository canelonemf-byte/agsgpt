import multiprocessing
import os

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120
graceful_timeout = 30
keepalive = 5

os.environ.setdefault("PROMETHEUS_MULTIPROC_DIR", "/tmp/prometheus_metrics")


def child_exit(server, worker):
    """Marca el worker como muerto para que Prometheus no lo sume."""
    from prometheus_client import multiprocess
    multiprocess.mark_process_dead(worker.pid)
