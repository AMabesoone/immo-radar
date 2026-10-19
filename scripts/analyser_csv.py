"""Analyse 360 d'un fichier CSV d'annonces (export Jinka, liste de chasseur) sans toucher aux sorties du radar.

Usage : python scripts/analyser_csv.py data/jinka/invest-nord.csv [--top 20] [--json sortie.json]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from immo_radar.analysis import Analyseur  # noqa: E402
from immo_radar.config import ROOT, load_config  # noqa: E402
from immo_radar.pipeline import filtrer  # noqa: E402
from immo_radar.sources import csv_import  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--json", default=None)
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    cfg = load_config(args.config)
    listings = filtrer(csv_import.load(args.csv), cfg["recherche"], cfg.get("sources_speciales", {}))
    analyseur = Analyseur(cfg, str(ROOT / "data" / "cache"))
    analyseur.preparer()
    opps = [o for o in (analyseur.analyser(l) for l in listings) if o]
    opps.sort(key=lambda o: o.score.total, reverse=True)
    print(f"\n{len(listings)} annonces analysees. Hypotheses : apport {cfg['financement']['apport_pct']:.0%}, {cfg['financement']['duree_ans']} ans, TMI {cfg['fiscalite']['tmi']:.0%}.\n")
    print(f"{'Score':>5} {'Ville':<22} {'Prix':>8} {'m2':>5} {'P':>2} {'DPE':>3} {'EUR/m2':>6} {'DVF/m2':>6} {'Loyer':>6} {'Rdt brut':>8} {'CF LD':>7} {'Scenario':<10} {'Regime':<12} Titre")
    for o in opps[: args.top]:
        l, m, r = o.listing, o.market, o.to_dict()["resume"]
        best = o.meilleur_scenario_ld
        print(f"{o.score.total:>5} {l.ville[:22]:<22} {l.prix:>8,.0f} {l.surface:>5.0f} {l.pieces:>2} {(l.dpe or '?'):>3} {l.prix_m2:>6,.0f} {(m.prix_m2_dvf_median or 0):>6,.0f} {(best.loyer_mensuel_brut if best else 0):>6,.0f} {(r['rendement_brut'] or 0):>8.1%} {(r['cashflow_ld_apres_impot'] or 0):>7,.0f} {(r['meilleur_scenario'] or ''):<10} {(r['meilleur_regime'] or ''):<12} {l.titre[:50]}")
    if opps:
        flags = {}
        for o in opps:
            for f in o.score.red_flags:
                flags[f.split(":")[0]] = flags.get(f.split(":")[0], 0) + 1
        print("\nAlertes les plus frequentes :", ", ".join(f"{k} ({v})" for k, v in sorted(flags.items(), key=lambda x: -x[1])[:6]))
    if args.json:
        Path(args.json).write_text(json.dumps([o.to_dict() for o in opps], ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
