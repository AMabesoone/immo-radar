"""Point d'entree : python scripts/run_weekly.py [--dry-run] [--limite N] [--refresh-str] [--config chemin]"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from immo_radar.pipeline import executer  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Immo Radar : scan hebdomadaire des opportunites locatives")
    ap.add_argument("--config", default=None)
    ap.add_argument("--dry-run", action="store_true", help="n'ecrit ni Sheet, ni HTML, ni etat")
    ap.add_argument("--limite", type=int, default=None, help="nombre max d'annonces analysees (tests)")
    ap.add_argument("--refresh-str", action="store_true", help="force le rafraichissement des donnees Inside Airbnb")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    res = executer(args.config, dry_run=args.dry_run, limite=args.limite, rafraichir_str=args.refresh_str)
    top = res["opportunites"][:10]
    print("\nTop opportunites :")
    for o in top:
        l, r = o["listing"], o["resume"]
        cf = r["cashflow_ld_apres_impot"]
        print(f"  {o['score']['total']:>5}  {l['ville']:<18} {l['prix']:>9,.0f} EUR {l['surface']:>5.0f} m2  CF LD {cf if cf is None else round(cf):>6} EUR/mois  {l['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
