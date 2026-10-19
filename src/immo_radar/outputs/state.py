"""Memoire inter-semaines : premiere apparition, historique des prix, meilleur score."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


class Etat:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data: dict[str, Any] = {"annonces": {}}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            self.data.setdefault("annonces", {})

    def enregistrer(self, listing_id: str, prix: float, score: float, url: str, titre: str) -> dict[str, Any]:
        today = date.today().isoformat()
        entry = self.data["annonces"].setdefault(listing_id, {
            "premiere_vue": today, "prix": [], "meilleur_score": 0.0, "url": url, "titre": titre,
        })
        entry["derniere_vue"] = today
        if not entry["prix"] or entry["prix"][-1]["prix"] != prix:
            entry["prix"].append({"date": today, "prix": prix})
        entry["meilleur_score"] = max(entry.get("meilleur_score", 0.0), score)
        entry["nouvelle"] = entry["premiere_vue"] == today
        entry["baisse_prix_pct"] = 0.0
        if len(entry["prix"]) > 1 and entry["prix"][0]["prix"]:
            entry["baisse_prix_pct"] = 1 - prix / entry["prix"][0]["prix"]
        return entry

    def purger(self, jours: int = 120) -> None:
        from datetime import datetime, timedelta
        limite = (datetime.today() - timedelta(days=jours)).date().isoformat()
        self.data["annonces"] = {k: v for k, v in self.data["annonces"].items() if v.get("derniere_vue", "") >= limite}

    def sauvegarder(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
