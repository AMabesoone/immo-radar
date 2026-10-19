"""Import manuel d'annonces (off-market, alertes e-mail Leboncoin / SeLoger copiees, chasseur immo).

Fichier : data/annonces_manuelles.csv, colonnes minimales :
id,url,titre,prix,surface,pieces,type_bien,ville,code_postal,categorie_ville,dpe,charges_copro_annuelles,taxe_fonciere,description
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from ..models import Listing

log = logging.getLogger(__name__)


def _num(v: str | None) -> float | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def load(path: str | Path) -> list[Listing]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[Listing] = []
    with open(p, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            prix, surface = _num(row.get("prix")), _num(row.get("surface"))
            if not prix or not surface:
                continue
            out.append(Listing(
                id=f"manuel:{row.get('id') or row.get('url')}",
                source=row.get("source") or "manuel",
                url=row.get("url") or "",
                titre=row.get("titre") or "",
                description=row.get("description") or "",
                prix=prix,
                surface=surface,
                pieces=int(_num(row.get("pieces")) or 1),
                type_bien=row.get("type_bien") or "flat",
                ville=row.get("ville") or "",
                code_postal=str(row.get("code_postal") or ""),
                categorie_ville=row.get("categorie_ville") or "ville_moyenne",
                zone_recherche=row.get("ville") or "",
                dpe=(row.get("dpe") or None),
                charges_copro_annuelles=_num(row.get("charges_copro_annuelles")),
                taxe_fonciere=_num(row.get("taxe_fonciere")),
                loue_actuellement=str(row.get("loue", "")).lower() in {"1", "oui", "true"},
                loyer_actuel=_num(row.get("loyer_actuel")),
            ))
    log.info("Import manuel : %d annonces", len(out))
    return out
