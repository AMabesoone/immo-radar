"""Scenarios d'exploitation : longue duree (nue, meublee, colocation) et courte duree."""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any

from ..models import Listing, MarketData
from .loan import PlanFinancement


@dataclass
class Scenario:
    nom: str                                  # nue | meuble | colocation | courte_duree
    loyer_mensuel_brut: float                 # hors charges recuperables
    revenus_annuels: float
    vacance: float
    gestion: float
    charges_copro_non_recup: float
    taxe_fonciere: float
    assurance: float
    gli: float
    entretien_capex: float
    autres_charges: float                     # energie, plateforme, linge, comptable, CFE...
    detail_charges: dict[str, float] = field(default_factory=dict)
    revenus_nets_avant_credit: float = 0.0
    rendement_brut: float = 0.0
    rendement_net: float = 0.0
    cashflow_mensuel_avant_impot: float = 0.0
    dscr: float = 0.0                         # revenus nets / annuite de credit
    hypotheses: dict[str, Any] = field(default_factory=dict)
    faisable: bool = True
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _taxe_fonciere(listing: Listing, loyer_mensuel: float, cfg_ld: dict[str, Any]) -> float:
    if listing.taxe_fonciere:
        return float(listing.taxe_fonciere)
    return loyer_mensuel * float(cfg_ld.get("taxe_fonciere_defaut_mois_loyer", 1.0))


def _charges_copro_non_recup(listing: Listing, cfg_ld: dict[str, Any]) -> float:
    if listing.en_copropriete is False and listing.type_bien in {"house", "building"}:
        return 0.0
    total = listing.charges_copro_annuelles
    if not total:
        total = listing.surface * float(cfg_ld.get("charges_copro_defaut_par_m2_an", 30))
    return float(total) * float(cfg_ld.get("charges_copro_non_recuperables_pct", 0.30))


def loyer_longue_duree(listing: Listing, market: MarketData, cfg_ld: dict[str, Any]) -> float | None:
    """Loyer mensuel hors charges estime pour une location nue classique."""
    estime = None
    if market.loyer_m2:
        estime = market.loyer_m2 * 0.92 * listing.surface
    externe = (listing.extra or {}).get("loyer_marche")
    if externe:
        return float(externe)  # estimation externe saisie a la main (agence, MeilleursAgents) : prioritaire
    if listing.loue_actuellement and listing.loyer_actuel:
        # garde-fou : un loyer "en place" lu dans l'annonce doit rester plausible (0,4 a 2 fois le marche)
        if estime is None or 0.4 * estime <= float(listing.loyer_actuel) <= 2.0 * estime:
            return float(listing.loyer_actuel)
        listing.loyer_actuel = None
    if not market.loyer_m2:
        return None
    # La carte des loyers donne un loyer charges comprises : on retire ~8 % de charges.
    loyer_hc_m2 = market.loyer_m2 * 0.92
    # Decote de surface : les grandes surfaces se louent moins cher au m2 que la moyenne, les petites plus cher.
    if listing.surface <= 25:
        coef = 1.15
    elif listing.surface <= 40:
        coef = 1.05
    elif listing.surface <= 70:
        coef = 1.0
    else:
        coef = 0.90
    return loyer_hc_m2 * listing.surface * coef


def _scenario_ld(
    nom: str,
    listing: Listing,
    market: MarketData,
    loyer: float,
    plan: PlanFinancement,
    cfg_ld: dict[str, Any],
    cfg_fisc: dict[str, Any],
    meuble: bool,
) -> Scenario:
    cat = listing.categorie_ville
    vacance_pct = float(cfg_ld.get("vacance_pct_par_categorie", {}).get(cat, 0.06))
    revenus = loyer * 12
    vacance = revenus * vacance_pct
    gestion = revenus * float(cfg_ld.get("gestion_locative_pct", 0.07))
    gli = revenus * float(cfg_ld.get("gli_pct", 0.0))
    capex = revenus * float(cfg_ld.get("entretien_capex_pct", 0.05))
    copro = _charges_copro_non_recup(listing, cfg_ld)
    tf = _taxe_fonciere(listing, loyer, cfg_ld)
    pno = float(cfg_ld.get("assurance_pno", 160))
    autres = {}
    if meuble:
        autres["comptable_lmnp"] = float(cfg_fisc.get("comptable_lmnp", 450))
        autres["cfe"] = float(cfg_fisc.get("cfe_defaut", 300))
    autres_total = sum(autres.values())
    charges = vacance + gestion + gli + capex + copro + tf + pno + autres_total
    nets = revenus - charges
    annuite = plan.mensualite_totale * 12
    return Scenario(
        nom=nom,
        loyer_mensuel_brut=loyer,
        revenus_annuels=revenus,
        vacance=vacance,
        gestion=gestion,
        charges_copro_non_recup=copro,
        taxe_fonciere=tf,
        assurance=pno,
        gli=gli,
        entretien_capex=capex,
        autres_charges=autres_total,
        detail_charges={
            "vacance": vacance, "gestion": gestion, "gli": gli, "entretien_capex": capex,
            "copro_non_recuperable": copro, "taxe_fonciere": tf, "assurance_pno": pno, **autres,
        },
        revenus_nets_avant_credit=nets,
        rendement_brut=revenus / plan.cout_total if plan.cout_total else 0.0,
        rendement_net=nets / plan.cout_total if plan.cout_total else 0.0,
        cashflow_mensuel_avant_impot=(nets - annuite) / 12.0,
        dscr=nets / annuite if annuite else 0.0,
        hypotheses={"vacance_pct": vacance_pct, "meuble": meuble},
    )


def scenario_courte_duree(
    listing: Listing,
    market: MarketData,
    plan: PlanFinancement,
    cfg_cd: dict[str, Any],
    cfg_ld: dict[str, Any],
    cfg_fisc: dict[str, Any],
    loyer_ld: float | None,
) -> Scenario:
    cat = listing.categorie_ville
    if market.str_adr and market.str_occupation:
        adr = market.str_adr
        occ = market.str_occupation
        source = market.str_source or "inside_airbnb"
    else:
        adr_base = float(cfg_cd.get("adr_base_par_categorie", {}).get(cat, 80))
        coefs = cfg_cd.get("adr_coef_par_pieces", {1: 0.8, 2: 1.0, 3: 1.3, 4: 1.6})
        adr = adr_base * float(coefs.get(min(listing.pieces, 4), coefs.get(str(min(listing.pieces, 4)), 1.0)))
        occ = float(cfg_cd.get("occupation_par_categorie", {}).get(cat, 0.5))
        source = "heuristique_categorie"
    adr = min(max(adr, float(cfg_cd.get("adr_min", 45))), float(cfg_cd.get("adr_max", 260)))
    revenus = adr * 365 * occ
    plateforme = revenus * float(cfg_cd.get("commission_plateforme_pct", 0.03))
    conciergerie = revenus * float(cfg_cd.get("conciergerie_pct", 0.20))
    linge = revenus * float(cfg_cd.get("linge_consommables_pct", 0.05))
    capex = revenus * float(cfg_cd.get("entretien_capex_pct", 0.10))
    energie = float(cfg_cd.get("energie_internet_mensuel", 170)) * 12
    assurance = float(cfg_cd.get("assurance_specifique", 250))
    # En courte duree le proprietaire supporte la totalite des charges de copropriete.
    copro_total = listing.charges_copro_annuelles or listing.surface * float(cfg_ld.get("charges_copro_defaut_par_m2_an", 30))
    if listing.en_copropriete is False and listing.type_bien in {"house", "building"}:
        copro_total = 0.0
    tf = _taxe_fonciere(listing, loyer_ld or revenus / 12 * 0.5, cfg_ld)
    th_secondaire = float(cfg_fisc.get("taxe_habitation_residence_secondaire_defaut", 0) or 0)
    if market.taxe_habitation_secondaire_majoration and tf:
        th_secondaire = max(th_secondaire, tf * 0.8 * (1 + market.taxe_habitation_secondaire_majoration))
    comptable = float(cfg_fisc.get("comptable_lmnp", 450))
    cfe = float(cfg_fisc.get("cfe_defaut", 300))
    classement = float(cfg_cd.get("classement_cout", 0)) / 5.0 if cfg_cd.get("classement_meuble_tourisme") else 0.0
    detail = {
        "classement": classement,
        "commission_plateforme": plateforme, "conciergerie": conciergerie, "linge_consommables": linge,
        "entretien_capex": capex, "energie_internet": energie, "assurance": assurance,
        "copro_totale": copro_total, "taxe_fonciere": tf, "taxe_habitation_secondaire": th_secondaire,
        "comptable_lmnp": comptable, "cfe": cfe,
    }
    charges = sum(detail.values())
    nets = revenus - charges
    annuite = plan.mensualite_totale * 12
    sc = Scenario(
        nom="courte_duree",
        loyer_mensuel_brut=revenus / 12.0,
        revenus_annuels=revenus,
        vacance=0.0,
        gestion=conciergerie,
        charges_copro_non_recup=copro_total,
        taxe_fonciere=tf,
        assurance=assurance,
        gli=0.0,
        entretien_capex=capex,
        autres_charges=plateforme + linge + energie + th_secondaire + comptable + cfe,
        detail_charges=detail,
        revenus_nets_avant_credit=nets,
        rendement_brut=revenus / plan.cout_total if plan.cout_total else 0.0,
        rendement_net=nets / plan.cout_total if plan.cout_total else 0.0,
        cashflow_mensuel_avant_impot=(nets - annuite) / 12.0,
        dscr=nets / annuite if annuite else 0.0,
        hypotheses={"adr": adr, "occupation": occ, "source": source, "nuits_louees": round(365 * occ)},
        faisable=market.courte_duree_faisable,
        note=market.courte_duree_note,
    )
    return sc


def construire_scenarios(
    listing: Listing,
    market: MarketData,
    plan: PlanFinancement,
    cfg: dict[str, Any],
) -> list[Scenario]:
    cfg_ld = cfg["exploitation"]["longue_duree"]
    cfg_cd = cfg["exploitation"]["courte_duree"]
    cfg_fisc = cfg["fiscalite"]
    loyer_nu = loyer_longue_duree(listing, market, cfg_ld)
    scenarios: list[Scenario] = []
    if loyer_nu:
        scenarios.append(_scenario_ld("nue", listing, market, loyer_nu, plan, cfg_ld, cfg_fisc, meuble=False))
        loyer_meuble = loyer_nu * (1 + float(cfg_ld.get("prime_meuble_pct", 0.12)))
        scenarios.append(_scenario_ld("meuble", listing, market, loyer_meuble, plan, cfg_ld, cfg_fisc, meuble=True))
        demande_coloc = market.population is None or market.population >= int(cfg_ld.get("colocation_population_min", 60000)) or market.zone_tendue
        if (
            demande_coloc
            and listing.surface >= float(cfg_ld.get("colocation_surface_min", 60))
            and listing.pieces >= int(cfg_ld.get("colocation_pieces_min", 3))
        ):
            loyer_coloc = loyer_nu * (1 + float(cfg_ld.get("prime_colocation_pct", 0.25)))
            sc = _scenario_ld("colocation", listing, market, loyer_coloc, plan, cfg_ld, cfg_fisc, meuble=True)
            sc.hypotheses["chambres"] = max(listing.pieces - 1, 2)
            scenarios.append(sc)
    scenarios.append(scenario_courte_duree(listing, market, plan, cfg_cd, cfg_ld, cfg_fisc, loyer_nu))
    return scenarios
