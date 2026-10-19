from datetime import date

from immo_radar.analysis import categorie_par_population
from immo_radar.models import Listing
from immo_radar.pipeline import filtrer
from immo_radar.sources import etat, immo_interactif, licitor

HOME = '<a href="/ventes-judiciaires-immobilieres/tj-lyon/jeudi-22-octobre-2026.html">x</a><a href="/ventes-judiciaires-immobilieres/tj-meaux/jeudi-1er-octobre-2026.html">y</a>'
PAGE = '''<ul class="AdResults"> <li> <a class="Ad First" href="/annonce/11/00/90/vente-aux-encheres/une-maison-d-habitation/sainte-foy-les-lyon/rhone/110090.html" title="t"> <p class="Location"> <span class="Number">69</span> <span class="City">Sainte-Foy-lès-Lyon</span> </p> <p class="Description"> <span class="Name">Une maison d'habitation</span> <span class="Text">de 235,64 m², sur deux étages, comprenant : 6 pièces [...]</span> </p> <div class="Footer"> <div class="Price"> <p class="Initial">Mise à prix : <span class="PriceNumber">607 200 €</span></p> </div> </div> </a> </li>
<li> <a class="Ad" href="/annonce/11/00/91/vente-aux-encheres/un-appartement/lyon-3eme/rhone/110091.html" title="t"> <p class="Location"> <span class="Number">69</span> <span class="City">Lyon 3ème</span> </p> <p class="Description"> <span class="Name">Un appartement</span> <span class="Text">de 62,10 m², au 2e étage, occupé</span> </p> <div class="Footer"> <div class="Price"> <p class="Initial">Mise à prix : <span class="PriceNumber">80 000 €</span></p> </div> </div> </a> </li>
<li> <a class="Ad" href="/annonce/11/00/92/vente-aux-encheres/un-terrain/genay/rhone/110092.html" title="t"> <p class="Location"> <span class="Number">69</span> <span class="City">Genay</span> </p> <p class="Description"> <span class="Name">Un terrain</span> <span class="Text">de 800 m²</span> </p> <div class="Footer"> <div class="Price"> <p class="Initial">Mise à prix : <span class="PriceNumber">20 000 €</span></p> </div> </div> </a> </li></ul>'''


def test_licitor_audiences_et_lots():
    aud = licitor.audiences(HOME)
    assert aud[0][1] == "tj-meaux" and aud[0][2] == date(2026, 10, 1)
    assert aud[1][2] == date(2026, 10, 22)
    ads = licitor.parse_audience(PAGE, "/x", "tj-lyon", date(2026, 10, 22))
    assert len(ads) == 3 and ads[0]["mise_a_prix"] == 607200 and ads[0]["surface"] == 235.64
    lots = [licitor.to_listing(a, "Lyon", "metropole") for a in ads]
    assert lots[2] is None  # terrain
    appt = lots[1]
    assert appt.mode_vente == "enchere_judiciaire" and appt.occupe and appt.mise_a_prix == 80000 and appt.type_bien == "flat"
    assert appt.date_vente == "2026-10-22" and "TJ Lyon" in appt.titre


def test_immo_interactif_normalize():
    a = {"propertyType": "APP", "localityName": "MARSEILLE 11", "urlSeo": "encheres-en-ligne/appartement/marseille-11-13011/2019502", "nbRooms": 4,
         "area": 82.0, "postalCode": "13011", "offerStartDate": "2026-10-19T11:00:00Z", "firstOfferAmount": 165000, "reference": "MARSEILLE11", "vniStatus": "IN_PROGRESS"}
    lst = immo_interactif.normalize(a, "Marseille", "metropole")
    assert lst.mode_vente == "vente_interactive" and lst.mise_a_prix == 165000 and lst.ville == "Marseille 11" and lst.date_vente == "2026-10-19"
    assert immo_interactif.normalize({**a, "propertyType": "TER"}, "x", "y") is None


def test_etat_parse_fiche():
    page = "<html><body><div>Fini dans 33 jours</div><p>Descriptif du bien</p><p>Pavillon de 66,60 m² sur 626 m²</p><p>Procédure de vente</p><p>Appel d'offres, mise à prix : 145 000 €</p><p>Code INSEE</p><p>78322</p><p>Surface en m²</p><p>66</p><p>Nombre de chambres</p><p>2</p><p>Performance énergétique : G</p></body></html>"
    f = etat.parse_fiche(page)
    assert f["surface"] == 66 and f["insee"] == "78322" and f["dpe"] == "G" and f["jours_restants"] == 33 and f["chambres"] == 2
    assert f["prix"] == 145000 and f["procedure"].startswith("Appel d'offres")
    page2 = "<p>Le montant de la taxe foncière 2025 est de 2436€.</p><p>1) Mise à prix avec prix de réserve : 1 450 000 €</p><p>2) Consignation : 145 000 €</p><p>Procédure de vente</p><p>par Adjudication</p><p>Date d'adjudication : 26/10/2026</p><p>Surface en m²</p><p>236</p>"
    f2 = etat.parse_fiche(page2)
    assert f2["prix"] == 1450000 and f2["taxe_fonciere"] == 2436 and f2["date_vente"] == "2026-10-26" and f2["surface"] == 236


def test_filtre_modes_speciaux():
    cfg_r = {"mots_cles_exclusion": [], "mots_cles_exclusion_titre": [], "surface_min": 12, "prix_min": 40000, "prix_max": 350000}
    enchere = Listing(id="e", source="licitor", url="", titre="Un appartement", description="", prix=25000, surface=40, pieces=2, type_bien="flat", ville="Lyon", code_postal="",
                      mode_vente="enchere_judiciaire", mise_a_prix=25000)
    etat_sans_prix = Listing(id="s", source="etat", url="", titre="Pavillon", description="", prix=0, surface=66, pieces=3, type_bien="house", ville="Jouy", code_postal="", mode_vente="cession_etat")
    vni_doublon = Listing(id="n", source="notaires", url="https://www.immo-interactif.fr/encheres-en-ligne/appartement/x-38/2069750", titre="Appartement", description="", prix=100000, surface=50, pieces=2, type_bien="flat", ville="x", code_postal="", mode_vente="vente_interactive", mise_a_prix=100000)
    vni_source = Listing(id="v", source="immo_interactif", url="https://www.immo-interactif.fr/encheres-en-ligne/appartement/x-38/2069750", titre="Appartement", description="", prix=100000, surface=50, pieces=2, type_bien="flat", ville="x", code_postal="", mode_vente="vente_interactive", mise_a_prix=100000)
    res = filtrer([enchere, etat_sans_prix, vni_doublon, vni_source], cfg_r, {"ventes_interactives": True})
    assert [l.id for l in res] == ["e", "s", "v"]  # mise a prix a 50 % du minimum acceptee, bien Etat sans prix garde, doublon VNI ecarte au profit de la source immo-interactif
    res2 = filtrer([enchere, vni_doublon], cfg_r, {"ventes_interactives": True})
    assert [l.id for l in res2] == ["e", "n"]  # si immo-interactif n'a pas repondu (403 depuis le cloud), la VNI du flux notaires est conservee


def test_categorie_par_population():
    assert categorie_par_population(520000) == "metropole"
    assert categorie_par_population(150000) == "grande_ville"
    assert categorie_par_population(45000) == "ville_moyenne"
    assert categorie_par_population(None) == "petite_ville"


def test_etat_cache_roundtrip(tmp_path):
    from immo_radar.sources.etat import _sauver_cache, _charger_cache
    l = Listing(id="etat:1", source="etat", url="u", titre="t", description="", prix=0, surface=66, pieces=3, type_bien="house", ville="Jouy", code_postal="", mode_vente="cession_etat", extra={"insee": "78322"})
    _sauver_cache(tmp_path / "etat.json", [l])
    back = _charger_cache(tmp_path / "etat.json")
    assert len(back) == 1 and back[0].id == "etat:1" and back[0].extra["insee"] == "78322" and back[0].mode_vente == "cession_etat"
