"""Calculs de credit immobilier : mensualite, cout total, plan de financement."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


def mensualite(capital: float, taux_annuel: float, duree_ans: int) -> float:
    """Mensualite constante hors assurance."""
    n = int(duree_ans * 12)
    if n <= 0 or capital <= 0:
        return 0.0
    if taux_annuel <= 0:
        return capital / n
    t = taux_annuel / 12.0
    return capital * t / (1.0 - (1.0 + t) ** (-n))


def interets_annee(capital: float, taux_annuel: float, duree_ans: int, annee: int) -> tuple[float, float]:
    """Retourne (interets payes, capital rembourse) pour l'annee donnee (1 = premiere annee)."""
    n = int(duree_ans * 12)
    t = taux_annuel / 12.0
    m = mensualite(capital, taux_annuel, duree_ans)
    crd = capital
    interets = 0.0
    amorti = 0.0
    for mois in range(1, n + 1):
        i = crd * t
        a = m - i
        if (annee - 1) * 12 < mois <= annee * 12:
            interets += i
            amorti += a
        crd -= a
        if mois >= annee * 12:
            break
    return interets, amorti


@dataclass
class PlanFinancement:
    prix_achat: float
    frais_notaire: float
    travaux: float
    ameublement: float
    frais_dossier: float
    frais_garantie: float
    cout_total: float
    apport: float
    capital_emprunte: float
    duree_ans: int
    taux: float
    mensualite_hors_assurance: float
    assurance_mensuelle: float
    mensualite_totale: float
    cout_total_credit: float
    interets_annee_1: float
    capital_rembourse_annee_1: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def construire_plan(
    prix_achat: float,
    frais_notaire: float,
    travaux: float,
    ameublement: float,
    cfg_fin: dict[str, Any],
) -> PlanFinancement:
    """Construit le plan de financement a partir de la config `financement`."""
    duree = int(cfg_fin.get("duree_ans", 25))
    taux = float(cfg_fin.get("taux_25_ans" if duree > 20 else "taux_20_ans", 0.033))
    frais_dossier = float(cfg_fin.get("frais_dossier", 1000))
    base_projet = prix_achat + frais_notaire + travaux + ameublement
    apport_pct = float(cfg_fin.get("apport_pct", 0.10))
    apport = base_projet * apport_pct
    if not cfg_fin.get("financer_frais_notaire", True):
        apport = max(apport, frais_notaire)
    capital_hors_garantie = max(base_projet - apport, 0.0)
    frais_garantie = capital_hors_garantie * float(cfg_fin.get("frais_garantie_pct", 0.012))
    capital = capital_hors_garantie + frais_garantie + frais_dossier
    m = mensualite(capital, taux, duree)
    assurance = capital * float(cfg_fin.get("assurance_emprunteur_pct_capital", 0.0025)) / 12.0
    interets_1, amorti_1 = interets_annee(capital, taux, duree, 1)
    cout_credit = m * duree * 12 - capital + assurance * duree * 12
    return PlanFinancement(
        prix_achat=prix_achat,
        frais_notaire=frais_notaire,
        travaux=travaux,
        ameublement=ameublement,
        frais_dossier=frais_dossier,
        frais_garantie=frais_garantie,
        cout_total=base_projet + frais_garantie + frais_dossier,
        apport=apport,
        capital_emprunte=capital,
        duree_ans=duree,
        taux=taux,
        mensualite_hors_assurance=m,
        assurance_mensuelle=assurance,
        mensualite_totale=m + assurance,
        cout_total_credit=cout_credit,
        interets_annee_1=interets_1,
        capital_rembourse_annee_1=amorti_1,
    )


def taux_effort(plan: PlanFinancement, loyer_mensuel: float, cfg_fin: dict[str, Any]) -> float | None:
    """Taux d'effort HCSF si les revenus de l'emprunteur sont renseignes, sinon None."""
    revenus = float(cfg_fin.get("revenus_nets_mensuels_emprunteur", 0) or 0)
    if revenus <= 0:
        return None
    ponderation = float(cfg_fin.get("ponderation_loyers_banque", 0.70))
    charges = plan.mensualite_totale + float(cfg_fin.get("charges_credits_existants", 0) or 0)
    return charges / (revenus + loyer_mensuel * ponderation)
