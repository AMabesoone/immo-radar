"""Carte des loyers (Ministere du Logement / DHUP) : loyer d'annonce par commune, millesime 2025.

Source : https://www.data.gouv.fr/datasets/carte-des-loyers-indicateurs-de-loyers-dannonce-par-commune-en-2025
Colonnes : id_zone;INSEE_C;LIBGEO;EPCI;DEP;REG;loypredm2;lwr.IPm2;upr.IPm2;TYPPRED;nbobs_com;nbobs_mail;R2_adj
loypredm2 est un loyer mensuel charges comprises au m2 (appartements, maisons, 1-2 pieces, 3 pieces et plus).
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

import requests

log = logging.getLogger(__name__)

BASE = "https://static.data.gouv.fr/resources/carte-des-loyers-indicateurs-de-loyers-dannonce-par-commune-en-2025/"
FILES = {
    "app": BASE + "20251211-145010/pred-app-mef-dhup.csv",
    "app12": BASE + "20251211-144934/pred-app12-mef-dhup.csv",
    "app3": BASE + "20251211-144951/pred-app3-mef-dhup.csv",
    "mai": BASE + "20251211-145039/pred-mai-mef-dhup.csv",
}


def _num(v: str) -> float | None:
    try:
        return float(v.replace(",", "."))
    except (ValueError, AttributeError):
        return None


class CarteLoyers:
    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._tables: dict[str, dict[str, dict]] = {}

    def _load(self, key: str) -> dict[str, dict]:
        if key in self._tables:
            return self._tables[key]
        path = self.cache_dir / f"loyers_2025_{key}.csv"
        if not path.exists():
            log.info("Telechargement carte des loyers %s", key)
            r = requests.get(FILES[key], timeout=120)
            r.raise_for_status()
            path.write_bytes(r.content)
        table: dict[str, dict] = {}
        with open(path, encoding="latin-1", newline="") as fh:
            for row in csv.DictReader(fh, delimiter=";"):
                insee = row.get("INSEE_C")
                if not insee:
                    continue
                table[insee] = {
                    "commune": row.get("LIBGEO"),
                    "loyer_m2": _num(row.get("loypredm2", "")),
                    "bas": _num(row.get("lwr.IPm2", "")),
                    "haut": _num(row.get("upr.IPm2", "")),
                    "nb_obs": int(float(row.get("nbobs_com") or 0)),
                    "type_pred": row.get("TYPPRED"),
                }
        self._tables[key] = table
        return table

    def lookup(self, code_insee: str, type_bien: str, pieces: int) -> dict | None:
        if type_bien == "house":
            key = "mai"
        elif pieces <= 2:
            key = "app12"
        else:
            key = "app3"
        row = self._load(key).get(code_insee)
        if row is None:
            row = self._load("app").get(code_insee)
            key = "app"
        if row:
            row = dict(row)
            row["source"] = f"carte_loyers_2025_{key}"
        return row
