"""Comparaison des regimes fiscaux applicables a chaque scenario d'exploitation.

Regimes couverts :
- Location nue : micro-foncier (abattement 30 %) et reel foncier (deficit foncier imputable).
- Location meublee (LMNP) : micro-BIC et reel avec amortissements (bati, travaux, meubles).
- SCI a l'IS : amortissement + IS a taux reduit puis normal (impot au niveau de la societe).
Les montants sont des estimations annuelles en regime de croisiere (annee 1 pour les interets).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any

from .cashflow import Scenario
from .loan import PlanFinancement


@dataclass
class ResultatFiscal:
    regime: str
    base_imposable: float
    impot_revenu: float
    prelevements_sociaux: float
    impot_total: float
    cashflow_mensuel_apres_impot: float
    amortissement_annuel: float = 0.0
    deficit_reportable: float = 0.0
    commentaire: str = ""
    eligible: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalyseFiscale:
    scenario: str
    resultats: list[ResultatFiscal] = field(default_factory=list)
    meilleur_regime: str = ""
    meilleur_cashflow_mensuel: float = 0.0
    impot_meilleur_regime: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "resultats": [r.to_dict() for r in self.resultats],
            "meilleur_regime": self.meilleur_regime,
            "meilleur_cashflow_mensuel": self.meilleur_cashflow_mensuel,
            "impot_meilleur_regime": self.impot_meilleur_regime,
        }


def _charges_deductibles(sc: Scenario, plan: PlanFinancement) -> float:
    """Charges reelles deductibles hors amortissement : charges d'exploitation + interets + assurance."""
    charges_exploitation = sc.revenus_annuels - sc.revenus_nets_avant_credit
    # la vacance et la provision CAPEX ne sont pas des charges deductibles (ce sont des manques a gagner / provisions)
    charges_exploitation -= sc.vacance + sc.entretien_capex
    interets = plan.interets_annee_1 + plan.assurance_mensuelle * 12
    return max(charges_exploitation, 0.0) + interets


def amortissement_annuel(plan: PlanFinancement, cfg_am: dict[str, Any]) -> float:
    base_bati = plan.prix_achat
    if cfg_am.get("frais_acquisition_amortis", True):
        base_bati += plan.frais_notaire
    bati = base_bati * (1 - float(cfg_am.get("part_terrain", 0.15))) / float(cfg_am.get("duree_bati_ans", 30))
    travaux = plan.travaux / float(cfg_am.get("duree_travaux_ans", 12)) if plan.travaux else 0.0
    meubles = plan.ameublement / float(cfg_am.get("duree_meubles_ans", 7)) if plan.ameublement else 0.0
    return bati + travaux + meubles


def _cf_apres_impot(sc: Scenario, impot: float) -> float:
    return sc.cashflow_mensuel_avant_impot - impot / 12.0


def analyser_nue(sc: Scenario, plan: PlanFinancement, cfg_f: dict[str, Any]) -> AnalyseFiscale:
    tmi = float(cfg_f["tmi"])
    ps = float(cfg_f["prelevements_sociaux"])
    revenus = sc.revenus_annuels - sc.vacance  # loyers reellement encaisses
    res: list[ResultatFiscal] = []
    # Micro-foncier
    if revenus <= float(cfg_f["micro_foncier_plafond"]):
        base = revenus * (1 - float(cfg_f["micro_foncier_abattement"]))
        ir, pss = base * tmi, base * ps
        res.append(ResultatFiscal("micro_foncier", base, ir, pss, ir + pss, _cf_apres_impot(sc, ir + pss),
                                  commentaire="Abattement forfaitaire 30 %"))
    else:
        res.append(ResultatFiscal("micro_foncier", 0, 0, 0, 0, 0, eligible=False,
                                  commentaire="Loyers > 15 000 EUR : reel obligatoire"))
    # Reel foncier
    charges = _charges_deductibles(sc, plan) + plan.travaux  # travaux d'entretien/amelioration deductibles l'annee 1
    base = revenus - charges
    if base >= 0:
        ir, pss = base * tmi, base * ps
        com = "Benefice foncier impose au TMI + 17,2 % PS"
        deficit = 0.0
    else:
        deficit_global = min(-base, float(cfg_f["deficit_foncier_plafond"]))
        # le deficit hors interets s'impute sur le revenu global : economie d'impot au TMI
        ir = -deficit_global * tmi
        pss = 0.0
        deficit = -base - deficit_global
        com = f"Deficit foncier : {deficit_global:,.0f} EUR imputes sur le revenu global (economie IR), reste reportable 10 ans"
    res.append(ResultatFiscal("reel_foncier", base, ir, pss, ir + pss, _cf_apres_impot(sc, ir + pss),
                              deficit_reportable=deficit, commentaire=com))
    # Dispositif Jeanbrun (LF 2026) : amortissement en location nue si neuf ou ancien avec travaux >= 30 % du prix
    jb = cfg_f.get("jeanbrun") or {}
    if jb.get("actif"):
        neuf = plan.frais_notaire < 0.05 * plan.prix_achat
        eligible = neuf or (plan.travaux >= float(jb.get("travaux_min_pct_prix", 0.30)) * plan.prix_achat)
        if eligible:
            taux = float(jb.get("taux_neuf", 0.035) if neuf else jb.get("taux_ancien_renove", 0.03))
            part_terrain = float(cfg_f.get("amortissement", {}).get("part_terrain", 0.15))
            amort = min(plan.prix_achat * (1 - part_terrain) * taux, float(jb.get("plafond_annuel", 8000)))
            base_jb = revenus - charges - amort
            if base_jb >= 0:
                ir_jb, ps_jb = base_jb * tmi, base_jb * ps
            else:
                imput = min(-base_jb, float(cfg_f["deficit_foncier_plafond"]))
                ir_jb, ps_jb = -imput * tmi, 0.0
            res.append(ResultatFiscal("reel_foncier_jeanbrun", base_jb, ir_jb, ps_jb, ir_jb + ps_jb, _cf_apres_impot(sc, ir_jb + ps_jb),
                                      amortissement_annuel=amort,
                                      commentaire=f"Amortissement Jeanbrun {amort:,.0f} EUR/an ; contrepartie : loyer intermediaire plafonne 9 ans, acquisition avant le 31/12/2028"))
    return _conclure("nue", res)


def analyser_meuble(sc: Scenario, plan: PlanFinancement, cfg_f: dict[str, Any], tourisme: bool, classe: bool) -> AnalyseFiscale:
    tmi = float(cfg_f["tmi"])
    ps = float(cfg_f.get("prelevements_sociaux_bic", cfg_f["prelevements_sociaux"]))
    revenus = sc.revenus_annuels - sc.vacance
    res: list[ResultatFiscal] = []
    if tourisme and not classe:
        plafond, abattement = cfg_f["micro_bic_plafond_tourisme_non_classe"], cfg_f["micro_bic_abattement_tourisme_non_classe"]
        label = "micro_bic_tourisme_non_classe"
    elif tourisme and classe:
        plafond, abattement = cfg_f["micro_bic_plafond_tourisme_classe"], cfg_f["micro_bic_abattement_tourisme_classe"]
        label = "micro_bic_tourisme_classe"
    else:
        plafond, abattement = cfg_f["micro_bic_plafond_meuble_classique"], cfg_f["micro_bic_abattement_meuble_classique"]
        label = "micro_bic"
    if revenus <= float(plafond):
        base = revenus * (1 - float(abattement))
        ir, pss = base * tmi, base * ps
        res.append(ResultatFiscal(label, base, ir, pss, ir + pss, _cf_apres_impot(sc, ir + pss),
                                  commentaire=f"Abattement {float(abattement):.0%}, plafond {float(plafond):,.0f} EUR"))
    else:
        res.append(ResultatFiscal(label, 0, 0, 0, 0, 0, eligible=False, commentaire="Recettes au-dessus du plafond micro"))
    # Reel LMNP
    amort = amortissement_annuel(plan, cfg_f["amortissement"])
    charges = _charges_deductibles(sc, plan)
    base_avant_amort = revenus - charges
    # l'amortissement ne peut pas creer de deficit : il est limite au resultat positif, le surplus est reporte
    amort_utilise = min(max(base_avant_amort, 0.0), amort)
    base = base_avant_amort - amort_utilise
    if base > 0:
        ir, pss = base * tmi, base * ps
    else:
        ir, pss = 0.0, 0.0
    reportable = max(amort - amort_utilise, 0.0) + max(-base_avant_amort, 0.0)
    com = f"Amortissement {amort:,.0f} EUR/an ; resultat imposable {max(base, 0):,.0f} EUR"
    if reportable:
        com += f" ; {reportable:,.0f} EUR d'amortissements/deficits reportes (0 impot pendant plusieurs annees)"
    res.append(ResultatFiscal("reel_lmnp", base, ir, pss, ir + pss, _cf_apres_impot(sc, ir + pss),
                              amortissement_annuel=amort, deficit_reportable=reportable, commentaire=com))
    # SCI a l'IS (impot societe uniquement, hors flat tax sur dividendes)
    sci = cfg_f["sci_is"]
    base_is = max(revenus - charges - amort, 0.0)
    plafond_reduit = float(sci["plafond_taux_reduit"])
    is_du = min(base_is, plafond_reduit) * float(sci["taux_reduit"]) + max(base_is - plafond_reduit, 0) * float(sci["taux_normal"])
    res.append(ResultatFiscal("sci_is", base_is, is_du, 0.0, is_du, _cf_apres_impot(sc, is_du), amortissement_annuel=amort,
                              commentaire="IS 15 % puis 25 % ; tresorerie bloquee en societe (flat tax 30 % a la sortie) ; plus-value pro a la revente"))
    return _conclure(sc.nom, res)


def _conclure(nom: str, res: list[ResultatFiscal]) -> AnalyseFiscale:
    eligibles = [r for r in res if r.eligible]
    # On compare les regimes "particulier" (hors SCI IS, dont la tresorerie n'est pas disponible) pour le meilleur regime
    perso = [r for r in eligibles if r.regime != "sci_is"] or eligibles
    best = max(perso, key=lambda r: r.cashflow_mensuel_apres_impot)
    return AnalyseFiscale(nom, res, best.regime, best.cashflow_mensuel_apres_impot, best.impot_total)


def analyser_scenario(sc: Scenario, plan: PlanFinancement, cfg: dict[str, Any]) -> AnalyseFiscale:
    cfg_f = cfg["fiscalite"]
    if sc.nom == "nue":
        return analyser_nue(sc, plan, cfg_f)
    if sc.nom == "courte_duree":
        classe = bool(cfg["exploitation"]["courte_duree"].get("classement_meuble_tourisme", True))
        return analyser_meuble(sc, plan, cfg_f, tourisme=True, classe=classe)
    return analyser_meuble(sc, plan, cfg_f, tourisme=False, classe=False)
