"""Deduplicación de health-check.sh (modo AGSGPT_ALERT_DRY_RUN: no envía correos)."""
import http.server
import os
import socket
import subprocess
import threading
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "health-check.sh"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run(url, state_dir, repeat="3600"):
    env = {**os.environ, "AGSGPT_HEALTH_URL": url, "AGSGPT_STATE_DIR": str(state_dir),
           "AGSGPT_ALERT_DRY_RUN": "1", "AGSGPT_ALERT_REPEAT_SECONDS": repeat,
           "AGSGPT_HEALTH_TIMEOUT": "2", "HEALTHCHECKS_URL": ""}
    return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30)


def test_dedup_then_resolved_then_new_alert(tmp_path):
    port = _free_port()
    url = f"http://127.0.0.1:{port}/health"
    r1 = _run(url, tmp_path)
    assert r1.returncode == 1 and "AVISO: [CRITICAL]" in r1.stdout
    r2 = _run(url, tmp_path)
    assert r2.returncode == 1 and "AVISO" not in r2.stdout and "ya avisado" in r2.stdout

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", port), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    try:
        r3 = _run(url, tmp_path)
        assert r3.returncode == 0 and "AVISO: [RESOLVED]" in r3.stdout
        r4 = _run(url, tmp_path)
        assert r4.returncode == 0 and "AVISO" not in r4.stdout
    finally:
        srv.shutdown()
    r5 = _run(url, tmp_path)
    assert "AVISO: [CRITICAL]" in r5.stdout


def test_repeat_interval_zero_realerts(tmp_path):
    url = f"http://127.0.0.1:{_free_port()}/health"
    assert "AVISO" in _run(url, tmp_path, "0").stdout
    assert "AVISO" in _run(url, tmp_path, "0").stdout
