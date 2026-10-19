"""Ecriture dans Google Sheets via un compte de service (gspread).

Variables d'environnement :
- GOOGLE_SERVICE_ACCOUNT_JSON : contenu JSON de la cle du compte de service
- GSHEET_ID : identifiant du classeur (partage en edition avec l'e-mail du compte de service)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date
from typing import Any

log = logging.getLogger(__name__)

COLONNES = [
    "Date", "Score", "Verdict", "Mode de vente", "Mise a prix", "Date vente", "Ville", "CP", "Titre", "Prix retenu", "Surface", "Pieces", "Prix/m2", "DVF median/m2", "Decote",
    "DPE", "Travaux", "Cout total projet", "Apport", "Mensualite", "Meilleur scenario LD", "Loyer LD", "Rendement brut",
    "Rendement net", "Regime fiscal", "Cash-flow LD apres impot", "Courte duree faisable", "ADR", "Occupation",
    "Cash-flow CD apres impot", "Points forts", "Red flags", "Nouvelle", "Baisse prix", "URL",
]


def _client():
    import gspread
    from google.oauth2.service_account import Credentials

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    info = json.loads(raw)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)


def _pct(v: float | None) -> str:
    return f"{v:.1%}" if isinstance(v, (int, float)) else ""


def _eur(v: float | None) -> float | str:
    return round(v) if isinstance(v, (int, float)) else ""


def ligne(opp: dict[str, Any], etat: dict[str, Any]) -> list[Any]:
    lst, md, plan, res, sc = opp["listing"], opp["market"], opp["plan"], opp["resume"], opp["score"]
    best = next((s for s in opp["scenarios"] if s["nom"] == res["meilleur_scenario"]), None)
    cd = next((s for s in opp["scenarios"] if s["nom"] == "courte_duree"), None)
    decote = (1 - lst["prix"] / lst["surface"] / md["prix_m2_dvf_median"]) if md.get("prix_m2_dvf_median") and lst["surface"] else None
    return [
        date.today().isoformat(), sc["total"], sc["verdict"], lst.get("mode_vente", "classique"), _eur(lst.get("mise_a_prix")), lst.get("date_vente") or "",
        lst["ville"], lst["code_postal"], lst["titre"][:80],
        _eur(lst["prix"]), lst["surface"], lst["pieces"], _eur(lst["prix"] / lst["surface"] if lst["surface"] else None),
        _eur(md.get("prix_m2_dvf_median")), _pct(decote), lst.get("dpe") or "", opp["niveau_travaux"],
        _eur(plan["cout_total"]), _eur(plan["apport"]), _eur(plan["mensualite_totale"]),
        res["meilleur_scenario"] or "", _eur(best["loyer_mensuel_brut"] if best else None), _pct(res["rendement_brut"]),
        _pct(res["rendement_net"]), res["meilleur_regime"] or "", _eur(res["cashflow_ld_apres_impot"]),
        "oui" if res["cd_faisable"] else "non", _eur(cd["hypotheses"].get("adr") if cd else None),
        _pct(cd["hypotheses"].get("occupation") if cd else None), _eur(res["cashflow_cd_apres_impot"]),
        " | ".join(sc["points_forts"]), " | ".join(sc["red_flags"]),
        "oui" if etat.get("nouvelle") else "non", _pct(etat.get("baisse_prix_pct")), lst["url"],
    ]


def lire_parametres(sheet_id: str, onglet: str) -> dict[str, str]:
    """Lit un onglet cle / valeur pour surcharger la config (colonne A = cle pointee, B = valeur)."""
    gc = _client()
    if not gc or not sheet_id:
        return {}
    try:
        ws = gc.open_by_key(sheet_id).worksheet(onglet)
    except Exception:
        return {}
    out: dict[str, str] = {}
    for row in ws.get_all_values()[1:]:
        if len(row) >= 2 and row[0].strip() and row[1].strip():
            out[row[0].strip()] = row[1].strip()
    log.info("Parametres surcharges depuis le Sheet : %d", len(out))
    return out


def publier(sheet_id: str, cfg_out: dict[str, Any], opportunites: list[dict[str, Any]], etats: dict[str, dict[str, Any]]) -> bool:
    gc = _client()
    if not gc or not sheet_id:
        log.info("Google Sheets non configure (GOOGLE_SERVICE_ACCOUNT_JSON / GSHEET_ID absents) : etape ignoree")
        return False
    sh = gc.open_by_key(sheet_id)
    rows = [ligne(o, etats.get(o["listing"]["id"], {})) for o in opportunites]

    def _ws(nom: str):
        try:
            return sh.worksheet(nom)
        except Exception:
            return sh.add_worksheet(nom, rows=1000, cols=len(COLONNES) + 2)

    ws = _ws(cfg_out.get("onglet_opportunites", "Opportunites"))
    ws.clear()
    ws.update([COLONNES] + rows, value_input_option="USER_ENTERED")
    ws.freeze(rows=1)
    hist = _ws(cfg_out.get("onglet_historique", "Historique"))
    if not hist.get_all_values():
        hist.append_row(COLONNES)
    if rows:
        hist.append_rows(rows, value_input_option="USER_ENTERED")
    params = _ws(cfg_out.get("onglet_parametres", "Parametres"))
    if not params.get_all_values():
        params.update([["Cle (notation pointee)", "Valeur", "Exemple"],
                       ["financement.apport_pct", "", "0.10"],
                       ["financement.duree_ans", "", "25"],
                       ["financement.taux_25_ans", "", "0.0325"],
                       ["fiscalite.tmi", "", "0.30"],
                       ["recherche.prix_max", "", "350000"],
                       ["exploitation.longue_duree.gestion_locative_pct", "", "0 pour autogestion"],
                       ["exploitation.courte_duree.conciergerie_pct", "", "0.20"],
                       ["scoring.score_minimum_publication", "", "55"]])
    log.info("Google Sheet mis a jour : %d opportunites", len(rows))
    return True
