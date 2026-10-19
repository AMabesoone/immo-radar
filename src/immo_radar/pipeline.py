"""Orchestration hebdomadaire : collecte -> filtres -> analyse 360 -> score -> Sheets + HTML."""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from .analysis import Analyseur, Opportunite
from .config import ROOT, apply_overrides, load_config
from .models import Listing
from .outputs import html, sheets
from .outputs.state import Etat
from .enrich.geocode import resolve_zone
from .sources import bienici, csv_import, notaires

log = logging.getLogger(__name__)


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def filtrer(listings: list[Listing], cfg_r: dict[str, Any]) -> list[Listing]:
    excl = [_norm(k) for k in cfg_r.get("mots_cles_exclusion", [])]
    excl_titre = [_norm(k) for k in cfg_r.get("mots_cles_exclusion_titre", [])]
    out: list[Listing] = []
    vus: set[str] = set()
    for lst in listings:
        if lst.id in vus:
            continue
        vus.add(lst.id)
        text = _norm(f"{lst.titre} {lst.description}")
        titre = _norm(lst.titre)
        if any(re.search(rf"\b{re.escape(k)}\b", text) for k in excl):
            continue
        if any(re.search(rf"\b{re.escape(k)}\b", titre) for k in excl_titre):
            continue
        if lst.surface < float(cfg_r.get("surface_min", 9)) or not (float(cfg_r.get("prix_min", 0)) <= lst.prix <= float(cfg_r.get("prix_max", 1e9))):
            continue
        out.append(lst)
    return out


def executer(config_path: str | None = None, dry_run: bool = False, limite: int | None = None, rafraichir_str: bool = False) -> dict[str, Any]:
    cfg = load_config(config_path)
    out_cfg = cfg["sorties"]
    sheet_id = out_cfg.get("google_sheet_id") or ""
    overrides = sheets.lire_parametres(sheet_id, out_cfg.get("onglet_parametres", "Parametres")) if sheet_id and not dry_run else {}
    if overrides:
        cfg = apply_overrides(cfg, overrides)
    cfg_r = cfg["recherche"]

    log.info("Collecte des annonces")
    bruts = list(bienici.fetch_all(cfg_r))
    if cfg_r.get("source_notaires", True):
        bruts += list(notaires.fetch_all(cfg_r, resolve_zone))
    bruts += csv_import.load(ROOT / "data" / "annonces_manuelles.csv")
    listings = filtrer(bruts, cfg_r)
    if limite:
        listings = listings[:limite]
    log.info("%d annonces brutes, %d apres filtres", len(bruts), len(listings))

    analyseur = Analyseur(cfg, str(ROOT / "data" / "cache"))
    analyseur.preparer(rafraichir_str=rafraichir_str)
    etat = Etat(ROOT / out_cfg.get("state_path", "data/state.json"))
    opportunites: list[Opportunite] = []
    rb_min = float(cfg["scoring"].get("rendement_brut_minimum", 0.0))
    for lst in listings:
        try:
            opp = analyseur.analyser(lst)
        except Exception as exc:
            log.exception("Analyse impossible pour %s : %s", lst.id, exc)
            continue
        if not opp:
            continue
        best = opp.meilleur_scenario_ld
        if best and best.rendement_brut < rb_min and opp.score.total < 70:
            continue
        opportunites.append(opp)

    opportunites.sort(key=lambda o: o.score.total, reverse=True)
    seuil = float(cfg["scoring"].get("score_minimum_publication", 55))
    publiees = [o for o in opportunites if o.score.total >= seuil][: int(cfg["scoring"].get("top_n", 40))]
    if not publiees and opportunites:
        publiees = opportunites[:10]

    etats: dict[str, dict[str, Any]] = {}
    for o in opportunites:
        etats[o.listing.id] = etat.enregistrer(o.listing.id, o.listing.prix, o.score.total, o.listing.url, o.listing.titre)
    etat.purger()

    dicts = [o.to_dict() for o in publiees]
    stats = {
        "annonces_brutes": len(bruts),
        "annonces_analysees": len(listings),
        "publiees": len(publiees),
        "autofinancees_ld": sum(1 for o in publiees if (o.to_dict()["resume"]["cashflow_ld_apres_impot"] or -1) >= 0),
        "autofinancees_cd": sum(1 for o in publiees if o.market.courte_duree_faisable and o.analyses["courte_duree"].meilleur_cashflow_mensuel >= 0),
        "villes": len(cfg_r.get("villes", [])),
        "nouvelles": sum(1 for o in publiees if etats[o.listing.id].get("nouvelle")),
    }
    if not dry_run:
        etat.sauvegarder()
        html.rendre(dicts, etats, cfg, stats)
        try:
            sheets.publier(sheet_id, out_cfg, dicts, etats)
        except Exception as exc:
            log.exception("Publication Google Sheets en echec : %s", exc)
    log.info("Termine : %s", stats)
    return {"stats": stats, "opportunites": dicts}
