"""Demandes de valeurs foncieres geolocalisees (Etalem / DGFiP) : prix de vente reels par commune.

Fichiers par commune : https://files.data.gouv.fr/geo-dvf/latest/csv/{annee}/communes/{dep}/{insee}.csv
On calcule la mediane et les quartiles du prix au m2 (appartements et maisons) sur les 2 derniers millesimes.
Les resultats sont mis en cache dans data/cache/dvf/{insee}.json (regeneres tous les 60 jours).
"""
from __future__ import annotations

import csv
import io
import json
import logging
import statistics
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

BASE = "https://files.data.gouv.fr/geo-dvf/latest/csv/{annee}/communes/{dep}/{insee}.csv"
ANNEES = [2024, 2025, 2026]
TTL_S = 60 * 86400


def _quartiles(values: list[float]) -> tuple[float, float, float] | None:
    if len(values) < 8:
        return None
    vals = sorted(values)
    q = statistics.quantiles(vals, n=4)
    return q[0], statistics.median(vals), q[2]


class DVF:
    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir) / "dvf"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _download(self, insee: str) -> dict[str, list[float]]:
        dep = insee[:2]
        if dep == "97":
            dep = insee[:3]
        if insee.startswith("2A") or insee.startswith("2B"):
            dep = insee[:2]
        prix: dict[str, list[float]] = {"Appartement": [], "Maison": []}
        annees_ok: list[int] = []
        for annee in ANNEES:
            url = BASE.format(annee=annee, dep=dep, insee=insee)
            try:
                r = requests.get(url, timeout=120)
            except requests.RequestException as exc:
                log.warning("DVF %s %s : %s", insee, annee, exc)
                continue
            if r.status_code != 200 or not r.text.startswith("id_mutation"):
                continue
            annees_ok.append(annee)
            seen: set[str] = set()
            for row in csv.DictReader(io.StringIO(r.text)):
                if row.get("nature_mutation") != "Vente" or row.get("type_local") not in prix:
                    continue
                try:
                    vf = float(row["valeur_fonciere"])
                    surf = float(row["surface_reelle_bati"])
                    lots = int(float(row.get("nombre_lots") or 0))
                except (TypeError, ValueError):
                    continue
                if row["id_mutation"] in seen or surf < 9 or vf < 10000 or lots > 3:
                    continue
                seen.add(row["id_mutation"])
                ppm = vf / surf
                if 300 <= ppm <= 25000:
                    prix[row["type_local"]].append(ppm)
        prix["_annees"] = annees_ok  # type: ignore[assignment]
        return prix

    def stats(self, insee: str) -> dict:
        path = self.cache_dir / f"{insee}.json"
        if path.exists():
            data = json.loads(path.read_text())
            if time.time() - data.get("_ts", 0) < TTL_S:
                return data
        raw = self._download(insee)
        out: dict = {"_ts": time.time(), "annees": raw.get("_annees", [])}
        for typ in ("Appartement", "Maison"):
            q = _quartiles(raw.get(typ, []))
            out[typ] = {"p25": q[0], "median": q[1], "p75": q[2], "n": len(raw.get(typ, []))} if q else None
        path.write_text(json.dumps(out))
        return out

    def lookup(self, insee: str, type_bien: str) -> dict | None:
        try:
            st = self.stats(insee)
        except Exception as exc:
            log.warning("DVF indisponible pour %s : %s", insee, exc)
            return None
        typ = "Maison" if type_bien == "house" else "Appartement"
        res = st.get(typ) or st.get("Appartement")
        if res:
            res = dict(res)
            res["annees"] = ",".join(str(a) for a in st.get("annees", []))
        return res
