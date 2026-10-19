"""Analyse 360 d'une annonce : marche, financement, scenarios, fiscalite, score."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .enrich.dvf import DVF
from .enrich.geocode import resolve
from .enrich.regulation import Reglementation
from .enrich.rents import CarteLoyers
from .enrich.str_market import MarcheCourteDuree
from .finance.cashflow import Scenario, construire_scenarios
from .finance.loan import PlanFinancement, construire_plan, taux_effort
from .finance.scoring import Score, calculer_score
from .finance.tax import AnalyseFiscale, analyser_scenario
from .models import Listing, MarketData

log = logging.getLogger(__name__)

def categorie_par_population(population: int | None) -> str:
    if not population:
        return "petite_ville"
    if population >= 400000:
        return "metropole"
    if population >= 120000:
        return "grande_ville"
    if population >= 30000:
        return "ville_moyenne"
    return "petite_ville"


def _norm_ville(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+\d+(er|e|eme)\b.*$", "", text).strip()


NIVEAU_TRAVAUX = [
    ("lourde", r"a renover entierement|à rénover entièrement|gros travaux|a rehabiliter|à réhabiliter|renovation complete|rénovation complète|tout a refaire|tout à refaire"),
    ("renovation", r"travaux a prevoir|travaux à prévoir|a renover|à rénover|a rafraichir|à rafraîchir|renovation|rénovation|travaux"),
    ("rafraichissement", r"rafraichissement|rafraîchissement|quelques travaux|bon etat general|bon état général"),
]


@dataclass
class Opportunite:
    listing: Listing
    market: MarketData
    plan: PlanFinancement
    scenarios: list[Scenario]
    analyses: dict[str, AnalyseFiscale]
    score: Score
    niveau_travaux: str
    taux_effort: float | None = None
    checklist: list[str] = field(default_factory=list)

    @property
    def meilleur_scenario_ld(self) -> Scenario | None:
        ld = [s for s in self.scenarios if s.nom != "courte_duree"]
        return max(ld, key=lambda s: self.analyses[s.nom].meilleur_cashflow_mensuel) if ld else None

    def to_dict(self) -> dict[str, Any]:
        best = self.meilleur_scenario_ld
        cd = next((s for s in self.scenarios if s.nom == "courte_duree"), None)
        return {
            "listing": self.listing.to_dict(),
            "market": self.market.to_dict(),
            "plan": self.plan.to_dict(),
            "scenarios": [s.to_dict() for s in self.scenarios],
            "analyses": {k: v.to_dict() for k, v in self.analyses.items()},
            "score": self.score.to_dict(),
            "niveau_travaux": self.niveau_travaux,
            "taux_effort": self.taux_effort,
            "checklist": self.checklist,
            "resume": {
                "meilleur_scenario": best.nom if best else None,
                "meilleur_regime": self.analyses[best.nom].meilleur_regime if best else None,
                "cashflow_ld_apres_impot": self.analyses[best.nom].meilleur_cashflow_mensuel if best else None,
                "rendement_brut": best.rendement_brut if best else None,
                "rendement_net": best.rendement_net if best else None,
                "cashflow_cd_apres_impot": self.analyses["courte_duree"].meilleur_cashflow_mensuel if cd else None,
                "cd_faisable": cd.faisable if cd else False,
            },
        }


class Analyseur:
    def __init__(self, cfg: dict[str, Any], cache_dir: str):
        self.cfg = cfg
        self.loyers = CarteLoyers(cache_dir)
        self.dvf = DVF(cache_dir)
        self.str_market = MarcheCourteDuree(cache_dir)
        self.regl = Reglementation()
        self._market_cache: dict[tuple, MarketData] = {}

    def preparer(self, rafraichir_str: bool = False) -> None:
        try:
            self.str_market.refresh(force=rafraichir_str)
        except Exception as exc:
            log.warning("Rafraichissement Inside Airbnb impossible : %s", exc)

    # ------------------------------------------------------------------ marche
    def marche(self, lst: Listing) -> MarketData:
        key = (lst.code_postal, lst.ville, lst.type_bien, min(lst.pieces, 3), (lst.dpe or '').upper() in {'F', 'G'})
        if key in self._market_cache:
            return self._market_cache[key]
        insee, commune, population = resolve(lst.code_postal, lst.ville)
        if not insee and lst.extra.get("insee"):
            insee = str(lst.extra["insee"])
        md = MarketData(code_insee=insee, commune=commune, population=population)
        if insee:
            row = self.loyers.lookup(insee, lst.type_bien, lst.pieces)
            if row and row.get("loyer_m2"):
                md.loyer_m2, md.loyer_m2_bas, md.loyer_m2_haut = row["loyer_m2"], row["bas"], row["haut"]
                md.loyer_nb_obs, md.loyer_source = row["nb_obs"], row["source"]
            d = self.dvf.lookup(insee, lst.type_bien)
            if d:
                md.prix_m2_dvf_median, md.prix_m2_dvf_p25, md.prix_m2_dvf_p75 = d["median"], d["p25"], d["p75"]
                md.dvf_nb_ventes, md.dvf_annees = d["n"], d.get("annees", "")
        s = self.str_market.lookup(insee, lst.ville, lst.pieces)
        if s:
            md.str_adr, md.str_occupation, md.str_nb_annonces = s["adr"], s["occupation"], s["n"]
            md.str_source = f"inside_airbnb:{s['zone']}"
        rules = self.regl.pour(lst.ville)
        md.encadrement_loyers = bool(rules.get("encadrement_loyers"))
        md.changement_usage_requis = bool(rules.get("changement_usage"))
        md.zone_tendue = bool(rules.get("zone_tendue"))
        md.taxe_habitation_secondaire_majoration = float(rules.get("th_secondaire_majoration", 0) or 0)
        md.courte_duree_faisable, md.courte_duree_risque, md.courte_duree_note = Reglementation.courte_duree(rules, lst.dpe)
        self._market_cache[key] = md
        return md

    # --------------------------------------------------------------- travaux
    def niveau_travaux(self, lst: Listing) -> str:
        text = f"{lst.titre} {lst.description}".lower()
        for niveau, pattern in NIVEAU_TRAVAUX:
            if re.search(pattern, text):
                return niveau
        if (lst.dpe or "").upper() in {"F", "G"}:
            return "renovation"
        return "aucun"

    # -------------------------------------------------------------- analyse
    def prix_attendu(self, lst: Listing, md: MarketData) -> tuple[float, float, str]:
        """(prix retenu pour l'analyse, taux de frais d'acquisition, note) selon le mode de vente."""
        cfg = self.cfg
        acq = cfg["acquisition"]
        sp = cfg.get("sources_speciales", {})
        notaire_pct = float(acq["frais_notaire_neuf_pct"] if lst.neuf else acq["frais_notaire_ancien_pct"])
        valeur_dvf = md.prix_m2_dvf_median * lst.surface if md.prix_m2_dvf_median else None
        if lst.mode_vente == "enchere_judiciaire":
            prix = (lst.mise_a_prix or lst.prix) * float(sp.get("coef_adjudication_attendue", 1.6))
            note = f"Adjudication attendue = mise a prix {lst.mise_a_prix:,.0f} EUR x {float(sp.get('coef_adjudication_attendue', 1.6)):.2f}"
            if valeur_dvf:
                plafond = valeur_dvf * (1 - float(sp.get("decote_encheres_vs_marche", 0.20)))
                if prix > plafond:
                    prix, note = plafond, f"Adjudication attendue plafonnee a la valeur DVF ({valeur_dvf:,.0f} EUR) moins {float(sp.get('decote_encheres_vs_marche', 0.20)):.0%}"
            if lst.occupe:
                prix *= 1 - float(sp.get("decote_bien_occupe", 0.15))
                note += " ; bien occupe : decote supplementaire"
            return prix, float(sp.get("frais_encheres_pct", 0.12)), note
        if lst.mode_vente == "vente_interactive":
            prix = (lst.mise_a_prix or lst.prix) * float(sp.get("coef_premiere_offre", 1.15))
            note = f"Prix final attendu = premiere offre {lst.mise_a_prix:,.0f} EUR x {float(sp.get('coef_premiere_offre', 1.15)):.2f}"
            if valeur_dvf:
                plafond = valeur_dvf * (1 - float(sp.get("decote_vni_vs_marche", 0.05)))
                if prix > plafond:
                    prix, note = plafond, f"Prix final attendu plafonne a la valeur DVF ({valeur_dvf:,.0f} EUR) moins {float(sp.get('decote_vni_vs_marche', 0.05)):.0%}"
            return max(prix, lst.mise_a_prix or 0), notaire_pct, note
        if lst.mode_vente == "cession_etat":
            if lst.prix and lst.prix > 0:
                return lst.prix, notaire_pct, f"Mise a prix / prix annonce par l'Etat : {lst.prix:,.0f} EUR"
            if valeur_dvf:
                d = float(sp.get("decote_etat_sans_prix", 0.15))
                return valeur_dvf * (1 - d), notaire_pct, f"Prix non communique : hypothese d'offre = valeur DVF ({valeur_dvf:,.0f} EUR) moins {d:.0%}"
            return 0.0, notaire_pct, "Prix non communique et pas de reference DVF : analyse impossible"
        decote = float(acq.get("decote_negociation_cible", 0))
        for ville, marge in (acq.get("decote_negociation_par_ville") or {}).items():
            if _norm_ville(ville) == _norm_ville(lst.ville):
                decote = float(marge)
        return lst.prix * (1 - decote), notaire_pct, f"Prix affiche {lst.prix:,.0f} EUR moins {decote:.0%} de negociation"

    def analyser(self, lst: Listing) -> Opportunite | None:
        cfg = self.cfg
        md = self.marche(lst)
        if lst.categorie_ville == "a_determiner":
            lst.categorie_ville = categorie_par_population(md.population)
        niveau = self.niveau_travaux(lst)
        acq = cfg["acquisition"]
        prix_negocie, notaire_pct, note = self.prix_attendu(lst, md)
        if prix_negocie <= 0:
            return None
        lst.prix_estime_note = note
        if lst.mode_vente != "classique":
            # la mise a prix reste dans lst.mise_a_prix ; le prix "affiche" devient le prix attendu pour que
            # la decote vs DVF, le prix au m2 et les sorties portent sur un prix realiste
            lst.prix = prix_negocie
        travaux = lst.surface * float(acq["travaux_par_m2"].get(niveau, 0))
        ameublement = max(lst.surface * float(acq["ameublement_par_m2"]), float(acq["ameublement_minimum"]))
        plan = construire_plan(prix_negocie, prix_negocie * float(notaire_pct), travaux, ameublement, cfg["financement"])
        scenarios = construire_scenarios(lst, md, plan, cfg)
        if not scenarios:
            return None
        analyses = {s.nom: analyser_scenario(s, plan, cfg) for s in scenarios}
        score = calculer_score(lst, md, plan, scenarios, analyses, cfg)
        best = max((s for s in scenarios if s.nom != "courte_duree"), key=lambda s: analyses[s.nom].meilleur_cashflow_mensuel, default=None)
        te = taux_effort(plan, best.loyer_mensuel_brut if best else 0.0, cfg["financement"])
        opp = Opportunite(lst, md, plan, scenarios, analyses, score, niveau, te)
        opp.checklist = self._checklist(opp)
        return opp

    @staticmethod
    def _checklist(opp: Opportunite) -> list[str]:
        lst, md = opp.listing, opp.market
        items = [
            "Demander les 3 derniers PV d'AG, le carnet d'entretien, le montant du fonds travaux et les procedures en cours",
            "Verifier la taxe fonciere reelle (avis) et le detail des charges de copropriete (recuperables / non recuperables)",
            "Comparer le prix au m2 avec 5 ventes DVF recentes du meme immeuble ou de la rue",
            "Verifier le PLU (changement d'usage, preemption) et le reglement de copropriete (clause d'habitation bourgeoise)",
            "Obtenir 2 devis travaux avant la fin du delai de retractation (10 jours)",
            "Faire valider le loyer par 2 agences locales et 3 annonces comparables en ligne",
        ]
        if md.encadrement_loyers:
            items.append("Verifier le loyer de reference majore (encadrement des loyers) pour la surface et l'epoque de construction")
        if (lst.dpe or "").upper() in {"E", "F", "G"}:
            items.append("Faire chiffrer la renovation energetique (audit) et verifier l'eligibilite MaPrimeRenov' bailleur")
        if md.changement_usage_requis:
            items.append("Interroger la mairie sur l'autorisation de changement d'usage et le numero d'enregistrement (meuble de tourisme)")
        if lst.loue_actuellement:
            items.append("Demander le bail en cours, les 3 dernieres quittances, l'etat des lieux et le depot de garantie")
        if lst.annee_construction and lst.annee_construction < 1949:
            items.append("Diagnostic plomb et etat de la structure (immeuble d'avant 1949)")
        if lst.mode_vente == "enchere_judiciaire":
            items += [
                "Lire le cahier des conditions de vente et le PV descriptif (lien sur l'annonce Licitor) : charges, occupation, servitudes, frais",
                "Consigner 10 % de la mise a prix (minimum 3 000 EUR) par cheque de banque et mandater un avocat inscrit au barreau du tribunal",
                "Financement : pas de condition suspensive de pret ; obtenir un accord de principe bancaire AVANT l'audience (paiement sous 2 a 3 mois)",
                "Prevoir la surenchere du dixieme possible pendant 10 jours apres l'adjudication",
                "Visite collective unique organisee par l'avocat ou l'huissier : y aller avec un artisan",
            ]
            if lst.occupe:
                items.append("Bien occupe : identifier le titre d'occupation (bail, debiteur saisi) et budgeter 12 a 24 mois de procedure d'expulsion")
        if lst.mode_vente == "vente_interactive":
            items += [
                "S'inscrire sur immo-interactif et obtenir l'agrement du notaire avant l'ouverture des offres",
                "Fixer un prix plafond a partir de la valeur DVF : les encheres en ligne depassent souvent le marche",
                "Le vendeur n'est pas tenu d'accepter la meilleure offre : garder un plan B",
            ]
        if lst.mode_vente == "cession_etat":
            items += [
                "Telecharger le cahier des charges sur la fiche (procedure, date limite, depot de garantie, visites)",
                "Verifier le zonage d'urbanisme et l'etat (logement de fonction souvent a renover, parfois hors copropriete)",
                "Comparer la mise a prix a la valeur DVF : l'Etat vend au prix du marche sauf carence",
            ]
        return items
