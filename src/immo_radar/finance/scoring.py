"""Score 0-100 et drapeaux rouges d'une opportunite."""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any

from ..models import Listing, MarketData
from .cashflow import Scenario
from .loan import PlanFinancement
from .tax import AnalyseFiscale


@dataclass
class Score:
    total: float
    composantes: dict[str, float] = field(default_factory=dict)
    red_flags: list[str] = field(default_factory=list)
    points_forts: list[str] = field(default_factory=list)
    verdict: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _lin(x: float, x0: float, x1: float) -> float:
    """0 en x0, 1 en x1, lineaire entre (x1 peut etre < x0)."""
    if x1 == x0:
        return 1.0 if x >= x1 else 0.0
    return _clamp((x - x0) / (x1 - x0))


def calculer_score(
    listing: Listing,
    market: MarketData,
    plan: PlanFinancement,
    scenarios: list[Scenario],
    analyses: dict[str, AnalyseFiscale],
    cfg: dict[str, Any],
) -> Score:
    poids = cfg["scoring"]["poids"]
    comp: dict[str, float] = {}
    flags: list[str] = []
    forts: list[str] = []

    ld = [s for s in scenarios if s.nom != "courte_duree"]
    cd = next((s for s in scenarios if s.nom == "courte_duree"), None)
    meilleur_ld = max(ld, key=lambda s: analyses[s.nom].meilleur_cashflow_mensuel) if ld else None

    # 1. Autofinancement : cash-flow apres impot du meilleur scenario longue duree rapporte a la mensualite.
    if meilleur_ld:
        cf = analyses[meilleur_ld.nom].meilleur_cashflow_mensuel
        ratio = cf / plan.mensualite_totale if plan.mensualite_totale else 0
        comp["autofinancement"] = poids["autofinancement"] * _lin(ratio, -0.25, 0.20)
        if cf >= 0:
            forts.append(f"Autofinance en {meilleur_ld.nom} ({analyses[meilleur_ld.nom].meilleur_regime}) : +{cf:,.0f} EUR/mois apres impot")
        elif cf < -0.15 * plan.mensualite_totale:
            flags.append(f"Effort d'epargne eleve : {cf:,.0f} EUR/mois en longue duree")
    else:
        comp["autofinancement"] = 0.0
        flags.append("Pas d'indicateur de loyer pour cette commune")

    # 2. Rendement net (meilleur scenario LD).
    rn = meilleur_ld.rendement_net if meilleur_ld else 0.0
    comp["rendement_net"] = poids["rendement_net"] * _lin(rn, 0.03, 0.08)
    if meilleur_ld and meilleur_ld.rendement_brut >= 0.08:
        forts.append(f"Rendement brut {meilleur_ld.rendement_brut:.1%}")

    # 3. Decote vs marche DVF.
    if market.prix_m2_dvf_median and listing.surface:
        decote = 1 - listing.prix_m2 / market.prix_m2_dvf_median
        comp["decote_marche"] = poids["decote_marche"] * _lin(decote, -0.10, 0.25)
        if decote >= 0.15:
            forts.append(f"Prix/m2 {decote:.0%} sous la mediane DVF de la commune ({market.prix_m2_dvf_median:,.0f} EUR/m2)")
        elif decote <= -0.15:
            flags.append(f"Prix/m2 {-decote:.0%} au-dessus de la mediane DVF ({market.prix_m2_dvf_median:,.0f} EUR/m2)")
    else:
        comp["decote_marche"] = poids["decote_marche"] * 0.4

    # 4. Robustesse du loyer / tension.
    rob = 0.5
    if market.loyer_nb_obs:
        rob = _lin(market.loyer_nb_obs, 30, 1000)
    if market.population and market.population < 20000:
        rob *= 0.7
        flags.append("Commune < 20 000 habitants : marche locatif etroit")
    if market.zone_tendue:
        rob = min(1.0, rob + 0.15)
    if listing.loue_actuellement:
        rob = min(1.0, rob + 0.2)
        forts.append("Bien deja loue : loyer reel connu, pas de vacance a l'achat")
    comp["robustesse_loyer"] = poids["robustesse_loyer"] * rob

    # 5. Risque technique.
    risque = 1.0
    dpe = (listing.dpe or "").upper()
    if dpe == "G":
        risque -= 0.6
        flags.append("DPE G : interdit a la location longue duree depuis le 1er janvier 2025 (travaux obligatoires)")
    elif dpe == "F":
        risque -= 0.4
        flags.append("DPE F : interdit a la location a partir du 1er janvier 2028")
    elif dpe == "E":
        risque -= 0.15
        flags.append("DPE E : interdit a la location a partir de 2034, prevoir renovation energetique")
    elif dpe in {"A", "B", "C"}:
        forts.append(f"DPE {dpe}")
    if listing.copro_en_procedure:
        risque -= 0.5
        flags.append("Copropriete en procedure (syndic judiciaire / plan de sauvegarde)")
    if listing.annee_construction and listing.annee_construction < 1949:
        risque -= 0.1
    if listing.charges_copro_annuelles and listing.surface and listing.charges_copro_annuelles / listing.surface > 45:
        risque -= 0.2
        flags.append(f"Charges de copropriete elevees : {listing.charges_copro_annuelles / listing.surface:,.0f} EUR/m2/an")
    if listing.surface < 14:
        risque -= 0.2
        flags.append("Tres petite surface : liquidite et decence a verifier (9 m2 / 20 m3 minimum)")
    comp["risque_technique"] = poids["risque_technique"] * _clamp(risque)

    # 6. Liquidite / revente.
    liq = 0.5
    if listing.prix_a_baisse:
        liq += 0.25
        forts.append("Prix deja baisse : vendeur ouvert a la negociation")
    if market.prix_m2_dvf_p25 and listing.prix_m2 <= market.prix_m2_dvf_p25:
        liq += 0.25
    if listing.pieces >= 2 and 30 <= listing.surface <= 80:
        liq += 0.1
    texte = f"{listing.titre} {listing.description}".lower()
    signaux = [k for k in cfg["recherche"].get("mots_cles_bonus", []) if k.lower() in texte]
    if signaux:
        liq += 0.1 * min(len(signaux), 2)
        forts.append("Signaux vendeur / potentiel : " + ", ".join(sorted(set(signaux))[:4]))
    comp["liquidite_revente"] = poids["liquidite_revente"] * _clamp(liq)

    # 7. Option courte duree.
    if cd and cd.faisable:
        cf_cd = analyses["courte_duree"].meilleur_cashflow_mensuel
        ratio_cd = cf_cd / plan.mensualite_totale if plan.mensualite_totale else 0
        facteur_risque = {0: 1.0, 1: 0.85, 2: 0.5}.get(market.courte_duree_risque, 0.0)
        comp["option_courte_duree"] = poids["option_courte_duree"] * _lin(ratio_cd, 0.0, 0.5) * facteur_risque
        if cf_cd > 0:
            forts.append(f"Courte duree : +{cf_cd:,.0f} EUR/mois apres impot ({cd.hypotheses.get('occupation', 0):.0%} d'occupation, {cd.hypotheses.get('adr', 0):,.0f} EUR/nuit)")
            if market.courte_duree_risque >= 2:
                flags.append(f"Courte duree sous autorisation : {market.courte_duree_note}")
            if cfg["fiscalite"].get("plf_2027_risque_amortissement_tourisme"):
                flags.append("PLF 2027 (projet) : suppression ou plafonnement de l'amortissement LMNP des meubles de tourisme ; prevoir un repli en longue duree")
    else:
        comp["option_courte_duree"] = 0.0
        if cd and not cd.faisable:
            flags.append(f"Courte duree contrainte : {cd.note}")
    if market.encadrement_loyers:
        flags.append("Encadrement des loyers : verifier le loyer de reference majore avant de retenir le loyer estime")

    # 8. Mode de vente particulier : information, pas de penalite de score (le prix attendu integre deja la decote).
    if listing.mode_vente == "enchere_judiciaire":
        forts.append(f"Vente aux encheres judiciaires le {listing.date_vente} : mise a prix {listing.mise_a_prix:,.0f} EUR ({listing.prix_estime_note})")
        flags.append("Encheres : pas de condition suspensive de pret, consignation 10 %, frais 10 a 15 %, surenchere possible 10 jours")
        if (listing.extra or {}).get("surface_estimee"):
            flags.append(f"Surface non communiquee : {listing.surface:.0f} m2 estimes d'apres le nombre de pieces, loyers et prix/m2 a recalculer avec le PV descriptif")
        if listing.occupe:
            flags.append("Bien occupe : procedure d'expulsion ou bail a reprendre, 12 a 24 mois sans loyer possible")
    elif listing.mode_vente == "vente_interactive":
        forts.append(f"Vente notariale interactive (ouverture {listing.date_vente}) : premiere offre {listing.mise_a_prix:,.0f} EUR ({listing.prix_estime_note})")
    elif listing.mode_vente == "cession_etat":
        forts.append(f"Bien de l'Etat (Domaines) : {listing.prix_estime_note}")
        if not listing.mise_a_prix:
            flags.append("Prix non communique par l'Etat : le cash-flow repose sur une hypothese d'offre a valider")
        if listing.extra.get("jours_restants") is not None:
            flags.append(f"Date limite de la procedure dans {listing.extra['jours_restants']} jours")

    total = round(sum(comp.values()), 1)
    if total >= 75:
        verdict = "A visiter en priorite"
    elif total >= 60:
        verdict = "Interessant, a creuser"
    elif total >= 45:
        verdict = "Moyen, negociation necessaire"
    else:
        verdict = "A ecarter"
    return Score(total=total, composantes={k: round(v, 1) for k, v in comp.items()}, red_flags=flags, points_forts=forts, verdict=verdict)
