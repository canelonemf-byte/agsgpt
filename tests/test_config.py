"""Configuración: puertos en 127.0.0.1, imágenes fijadas, correo fuera de los archivos versionados."""
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent


def test_compose_ports_localhost_and_pinned_images():
    c = yaml.safe_load((REPO / "docker/docker-compose.yml").read_text(encoding="utf-8"))
    for name, svc in c["services"].items():
        for p in svc.get("ports", []):
            assert str(p).startswith("127.0.0.1:"), (name, p)
        img = svc.get("image", "")
        if img:
            assert ":" in img and not img.endswith(":latest"), img


def test_no_personal_email_in_tracked_config():
    pat = re.compile(r"[A-Za-z0-9._%+-]+@gmail\.com")
    for rel in ["monitoring/alertmanager.yml", "scripts/health-check.sh", ".env.example", "docker/docker-compose.yml"]:
        assert not pat.search((REPO / rel).read_text(encoding="utf-8")), rel


def test_gitignore_covers_env_and_backups():
    out = subprocess.run(["git", "check-ignore", ".env", ".env.bak_x", "x.py.bak_1", "monitoring/alertmanager.rendered.yml",
                          ".state/health_state"], cwd=REPO, capture_output=True, text=True)
    assert len(out.stdout.split()) == 5
    assert subprocess.run(["git", "check-ignore", "-q", ".env.example"], cwd=REPO).returncode == 1


def test_render_alertmanager(tmp_path, monkeypatch):
    sys.path.insert(0, str(REPO / "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("render", REPO / "scripts/render-alertmanager.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "REPO", tmp_path)
    out = tmp_path / "am.yml"
    mod.render(REPO / "monitoring/alertmanager.yml", out, {"AGSGPT_ALERT_EMAIL": "prueba@example.com"})
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["global"]["smtp_from"] == "prueba@example.com"
    assert data["receivers"][0]["email_configs"][0]["to"] == "prueba@example.com"
    assert "${" not in out.read_text(encoding="utf-8")
