from immo_radar.config import apply_overrides, coerce, load_config
from immo_radar.finance.cashflow import construire_scenarios
from immo_radar.finance.loan import construire_plan, mensualite
from immo_radar.finance.scoring import calculer_score
from immo_radar.finance.tax import analyser_scenario
from immo_radar.models import Listing, MarketData


def listing(**kw) -> Listing:
    base = dict(id="t:1", source="test", url="", titre="T2 lumineux", description="", prix=120000, surface=45, pieces=2,
                type_bien="flat", ville="Saint-Etienne", code_postal="42000", categorie_ville="ville_moyenne", dpe="D",
                charges_copro_annuelles=900)
    base.update(kw)
    return Listing(**base)


def market(**kw) -> MarketData:
    base = dict(code_insee="42218", commune="Saint-Etienne", population=170000, loyer_m2=10.5, loyer_nb_obs=800,
                prix_m2_dvf_median=1500, prix_m2_dvf_p25=1200, prix_m2_dvf_p75=1900, dvf_nb_ventes=400)
    base.update(kw)
    return MarketData(**base)


def test_mensualite_reference():
    # 100 000 EUR sur 20 ans a 3 % : 554,60 EUR (valeur de reference des simulateurs)
    assert abs(mensualite(100000, 0.03, 20) - 554.60) < 0.1
    assert mensualite(100000, 0.0, 10) == 100000 / 120


def test_plan_financement_110_pct():
    cfg = load_config()["financement"]
    cfg["apport_pct"] = 0.10
    plan = construire_plan(100000, 8500, 0, 4000, cfg)
    assert abs(plan.apport - 11250) < 1
    assert plan.capital_emprunte > 100000  # notaire et garantie finances
    assert plan.mensualite_totale > plan.mensualite_hors_assurance
    assert plan.interets_annee_1 > 0 and plan.interets_annee_1 < plan.capital_emprunte * plan.taux


def test_scenarios_et_fiscalite_coherents():
    cfg = load_config()
    lst, md = listing(), market()
    plan = construire_plan(lst.prix, lst.prix * 0.085, 0, 6000, cfg["financement"])
    scs = construire_scenarios(lst, md, plan, cfg)
    noms = {s.nom for s in scs}
    assert {"nue", "meuble", "courte_duree"} <= noms
    assert "colocation" not in noms  # 45 m2 / 2 pieces : trop petit
    nue = next(s for s in scs if s.nom == "nue")
    meuble = next(s for s in scs if s.nom == "meuble")
    assert meuble.loyer_mensuel_brut > nue.loyer_mensuel_brut
    assert nue.revenus_nets_avant_credit < nue.revenus_annuels
    for s in scs:
        a = analyser_scenario(s, plan, cfg)
        assert a.meilleur_regime
        for r in a.resultats:
            if r.eligible:
                assert r.impot_total >= -5000  # un deficit foncier peut produire une economie, bornee
    reel = next(r for r in analyser_scenario(meuble, plan, cfg).resultats if r.regime == "reel_lmnp")
    assert reel.amortissement_annuel > 3000
    assert reel.impot_total <= next(r for r in analyser_scenario(meuble, plan, cfg).resultats if r.regime == "micro_bic").impot_total


def test_colocation_sur_grande_surface():
    cfg = load_config()
    lst, md = listing(surface=80, pieces=4, prix=160000), market()
    plan = construire_plan(lst.prix, lst.prix * 0.085, 0, 9600, cfg["financement"])
    scs = construire_scenarios(lst, md, plan, cfg)
    assert any(s.nom == "colocation" for s in scs)


def test_score_penalise_dpe_g_et_procedure():
    cfg = load_config()
    md = market()

    def score(l):
        plan = construire_plan(l.prix, l.prix * 0.085, 0, 6000, cfg["financement"])
        scs = construire_scenarios(l, md, plan, cfg)
        an = {s.nom: analyser_scenario(s, plan, cfg) for s in scs}
        return calculer_score(l, md, plan, scs, an, cfg)

    bon, mauvais = score(listing()), score(listing(dpe="G", copro_en_procedure=True))
    assert bon.total > mauvais.total
    assert any("DPE G" in f for f in mauvais.red_flags)
    assert 0 <= bon.total <= 100


def test_courte_duree_contrainte_ne_score_pas():
    cfg = load_config()
    lst = listing(ville="Paris 11e", code_postal="75011", prix=250000, surface=25, categorie_ville="metropole")
    md = market(loyer_m2=32, prix_m2_dvf_median=10500, courte_duree_faisable=False, courte_duree_note="compensation", encadrement_loyers=True)
    plan = construire_plan(lst.prix, lst.prix * 0.085, 0, 4000, cfg["financement"])
    scs = construire_scenarios(lst, md, plan, cfg)
    an = {s.nom: analyser_scenario(s, plan, cfg) for s in scs}
    sc = calculer_score(lst, md, plan, scs, an, cfg)
    assert sc.composantes["option_courte_duree"] == 0
    assert any("Encadrement" in f for f in sc.red_flags)


def test_overrides_depuis_sheet():
    cfg = load_config()
    new = apply_overrides(cfg, {"financement.apport_pct": "15%", "fiscalite.tmi": "0,41", "recherche.prix_max": "200000"})
    assert new["financement"]["apport_pct"] == 0.15
    assert new["fiscalite"]["tmi"] == 0.41
    assert new["recherche"]["prix_max"] == 200000
    assert coerce("oui") is True and coerce("abc") == "abc"


def test_loyer_en_place_implausible_ignore():
    from immo_radar.finance.cashflow import loyer_longue_duree
    cfg = load_config()["exploitation"]["longue_duree"]
    lst = listing(loue_actuellement=True, loyer_actuel=2365)  # 45 m2 a 10,5 EUR/m2 : marche ~435 EUR
    assert loyer_longue_duree(lst, market(), cfg) < 600 and lst.loyer_actuel is None
    lst2 = listing(loue_actuellement=True, loyer_actuel=480)
    assert loyer_longue_duree(lst2, market(), cfg) == 480


def test_colocation_seulement_avec_demande():
    cfg = load_config()
    lst = listing(surface=100, pieces=5, prix=120000)
    plan = construire_plan(lst.prix, lst.prix * 0.08, 0, 12000, cfg["financement"])
    petite = market(population=25000, zone_tendue=False)
    assert not any(s.nom == "colocation" for s in construire_scenarios(lst, petite, plan, cfg))
    grande = market(population=170000)
    assert any(s.nom == "colocation" for s in construire_scenarios(lst, grande, plan, cfg))
