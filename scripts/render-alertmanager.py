#!/usr/bin/env python3
"""Genera monitoring/alertmanager.rendered.yml desde la plantilla monitoring/alertmanager.yml.

Sustituye ${VAR} con el entorno y, si falta, con el .env de la raíz. Sin dependencias.
No imprime valores. Autoría: Lázaro López Paz, El Prat de Llobregat, Barcelona, España,
con asistencia de IA. Licencia: MIT.
"""
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REQUIRED = ("AGSGPT_ALERT_EMAIL",)
_VAR = re.compile(r"\$\{([A-Z0-9_]+)\}")
_EMAIL = re.compile(r"^[^@\s\"']+@[^@\s\"']+\.[^@\s\"']+$")


def read_env(path: Path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def render(template: Path, out: Path, env: dict) -> None:
    values = {**read_env(REPO / ".env"), **{k: v for k, v in env.items() if v}}
    missing = [k for k in REQUIRED if not values.get(k)]
    if missing:
        sys.exit(f"Falta {', '.join(missing)} en .env o en el entorno")
    if not _EMAIL.match(values["AGSGPT_ALERT_EMAIL"]):
        sys.exit("AGSGPT_ALERT_EMAIL no parece un correo válido")
    text = template.read_text(encoding="utf-8")
    unknown = sorted({m for m in _VAR.findall(text) if m not in values})
    if unknown:
        sys.exit(f"Variables sin valor en la plantilla: {', '.join(unknown)}")
    out.write_text(_VAR.sub(lambda m: values[m.group(1)], text), encoding="utf-8")
    out.chmod(0o644)  # Alertmanager corre como nobody dentro del contenedor
    print(f"Generado {out.relative_to(REPO)}")


if __name__ == "__main__":
    render(REPO / "monitoring" / "alertmanager.yml", REPO / "monitoring" / "alertmanager.rendered.yml", dict(os.environ))
