"""Tableau de bord HTML statique (GitHub Pages) : docs/index.html + docs/data.json."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES = Path(__file__).parent / "templates"


def rendre(opportunites: list[dict[str, Any]], etats: dict[str, dict[str, Any]], cfg: dict[str, Any], stats: dict[str, Any]) -> None:
    out = cfg["sorties"]
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    tpl = env.get_template("dashboard.html.j2")
    for o in opportunites:
        o["etat"] = etats.get(o["listing"]["id"], {})
    payload = {
        "genere_le": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "stats": stats,
        "hypotheses": {
            "financement": cfg["financement"],
            "acquisition": cfg["acquisition"],
            "exploitation": cfg["exploitation"],
            "fiscalite": {k: v for k, v in cfg["fiscalite"].items() if k != "amortissement"},
            "scoring": cfg["scoring"],
        },
        "opportunites": opportunites,
    }
    data_path = Path(out.get("export_json_path", "docs/data.json"))
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    html_path = Path(out.get("html_path", "docs/index.html"))
    html_path.write_text(tpl.render(payload_json=json.dumps(payload, ensure_ascii=False), genere_le=payload["genere_le"], stats=stats), encoding="utf-8")
