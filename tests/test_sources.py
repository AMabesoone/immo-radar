from immo_radar.enrich.geocode import arrondissement_insee
from immo_radar.enrich.regulation import Reglementation
from immo_radar.enrich.str_market import _zone_key, _bedroom_bucket
from immo_radar.models import Listing
from immo_radar.pipeline import filtrer
from immo_radar.sources.bienici import normalize


AD = {
    "id": "agence-123", "title": "Appartement T3 à rénover", "description": "Bel appartement loué 650 € par mois, locataire en place. Travaux à prévoir.",
    "price": 99000, "surfaceArea": 62.5, "roomsQuantity": 3, "propertyType": "flat", "city": "Saint-Étienne", "postalCode": "42000",
    "energyClassification": "E", "annualCondominiumFees": 1200, "isCondominiumInProcedure": False, "priceHasDecreased": True,
    "publicationDate": "2026-10-12T10:00:00.000Z", "photos": [{}, {}], "adCreatedByPro": True,
}


def test_normalize_bienici():
    lst = normalize(AD, "Saint-Etienne", "ville_moyenne")
    assert lst and lst.prix == 99000 and lst.surface == 62.5 and lst.pieces == 3
    assert lst.loue_actuellement and lst.loyer_actuel == 650
    assert lst.prix_a_baisse and lst.dpe == "E"
    assert lst.url.startswith("https://www.bienici.com/annonce/vente/saint-etienne/appartement/3pieces/agence-123")


def test_normalize_rejette_sans_prix():
    assert normalize({**AD, "price": None}, "x", "ville_moyenne") is None


def test_arrondissements():
    assert arrondissement_insee("75011") == "75111"
    assert arrondissement_insee("69003") == "69383"
    assert arrondissement_insee("13008") == "13208"
    assert arrondissement_insee("42000") is None


def test_reglementation():
    r = Reglementation()
    paris = r.pour("Paris 11e")
    assert paris["compensation"] and paris["encadrement_loyers"]
    faisable, _, note = Reglementation.courte_duree(paris)
    assert not faisable
    ste = r.pour("Saint-Étienne")
    assert Reglementation.courte_duree(ste)[0]


def test_zone_keys_inside_airbnb():
    assert _zone_key("paris", "Buttes-Montmartre") == "75118"
    assert _zone_key("lyon", "3e Arrondissement") == "69383"
    assert _zone_key("bordeaux", "Chartrons - Grand Parc - Jardin Public") == "bordeaux:chartrons-grand-parc-jardin-public"
    assert _bedroom_bucket("0") == "0" and _bedroom_bucket("4") == "3+"


def test_filtres_exclusion():
    cfg_r = {"mots_cles_exclusion": ["viager", "parking"], "surface_min": 12, "prix_min": 40000, "prix_max": 350000}
    ok = Listing(id="a", source="t", url="", titre="T2", description="bel appartement", prix=100000, surface=40, pieces=2, type_bien="flat", ville="x", code_postal="1")
    viager = Listing(id="b", source="t", url="", titre="Vente en viager occupé", description="", prix=100000, surface=40, pieces=2, type_bien="flat", ville="x", code_postal="1")
    petit = Listing(id="c", source="t", url="", titre="Studette", description="", prix=50000, surface=9, pieces=1, type_bien="flat", ville="x", code_postal="1")
    res = filtrer([ok, viager, petit, ok], cfg_r)
    assert [l.id for l in res] == ["a"]


def test_normalize_notaires():
    from immo_radar.sources.notaires import normalize as n_norm
    a = {"annonceId": 1915052, "prixTotal": 140000, "surface": 63.14, "nbPieces": 3, "typeBien": "APP", "communeNom": "Saint-Étienne",
         "codePostal": "42000", "inseeCommune": "42218", "descriptionFr": "Succession", "urlDetailAnnonceFr": "https://x", "viager": "NON",
         "ancienNeuf": "ANCIEN", "variation": "BAISSE", "dateCreation": "2026-10-01T00:00:00Z", "nbPhoto": 3}
    lst = n_norm(a, "Saint-Etienne", "ville_moyenne")
    assert lst and lst.source == "notaires" and lst.prix_a_baisse and lst.type_bien == "flat"
    assert n_norm({**a, "viager": "OUI"}, "x", "ville_moyenne") is None


def test_filtre_titre_vs_description():
    cfg_r = {"mots_cles_exclusion": ["viager"], "mots_cles_exclusion_titre": ["parking"], "surface_min": 12, "prix_min": 40000, "prix_max": 350000}
    avec_cave = Listing(id="a", source="t", url="", titre="T2", description="avec cave et parking", prix=100000, surface=40, pieces=2, type_bien="flat", ville="x", code_postal="1")
    parking = Listing(id="b", source="t", url="", titre="Parking couvert", description="", prix=40000, surface=12, pieces=1, type_bien="flat", ville="x", code_postal="1")
    assert [l.id for l in filtrer([avec_cave, parking], cfg_r)] == ["a"]


def test_notaires_rejette_terrains_et_locaux():
    from immo_radar.sources.notaires import normalize as n_norm
    base = {"annonceId": 1, "prixTotal": 100000, "surface": 300, "nbPieces": 1, "communeNom": "Rennes", "codePostal": "35000", "viager": "NON"}
    assert n_norm({**base, "typeBien": "TER"}, "Rennes", "grande_ville") is None
    assert n_norm({**base, "typeBien": "LOC"}, "Rennes", "grande_ville") is None
    assert n_norm({**base, "typeBien": "GAR"}, "Rennes", "grande_ville") is None
    assert n_norm({**base, "typeBien": "MAI"}, "Rennes", "grande_ville") is not None


def test_arrondissement_depuis_nom():
    from immo_radar.enrich.geocode import arrondissement_depuis_nom
    assert arrondissement_depuis_nom("Lyon 3ème") == "69383"
    assert arrondissement_depuis_nom("Paris 15e") == "75115"
    assert arrondissement_depuis_nom("Marseille 11") == "13211"
    assert arrondissement_depuis_nom("Lyon") is None
