from immo_radar.sources.email_alerts import extraire_annonces, to_listing, Cache

MAIL = """<html><body><h1>Nouvelles annonces pour votre recherche "Maison Nord"</h1>
<table><tr><td>
<a href="https://www.leboncoin.fr/ad/ventes_immobilieres/2987654321"><img src="x"></a>
<p><a href="https://www.leboncoin.fr/ad/ventes_immobilieres/2987654321">Maison 5 pièces 120 m² avec jardin</a></p>
<p>129 000 €</p><p>Roubaix 59100</p><p>Classe énergie : D</p>
</td></tr><tr><td>
<p><a href="https://www.leboncoin.fr/ad/ventes_immobilieres/2987000001">Appartement T2</a></p>
<p>45 000 €</p><p>Tourcoing 59200</p>
</td></tr></table>
<p>Se désabonner : <a href="https://www.leboncoin.fr/compte/alertes">ici</a></p>
</body></html>"""


def test_extraction_leboncoin():
    ads = extraire_annonces(MAIL, source_hint="noreply@leboncoin.fr")
    ids = {a["id"]: a for a in ads}
    assert set(ids) == {"2987654321", "2987000001"}
    a = ids["2987654321"]
    assert a["prix"] == 129000 and a["surface"] == 120 and a["pieces"] == 5 and a["code_postal"] == "59100" and a["dpe"] == "D"
    assert a["ville"].lower().startswith("roubaix") and "Maison 5" in a["titre"]
    lst = to_listing(a)
    assert lst.type_bien == "house" and lst.source == "leboncoin" and lst.id == "leboncoin:2987654321"
    assert to_listing(ids["2987000001"]) is None  # pas de surface dans le mail : non analysable


def test_cache_retention(tmp_path):
    c = Cache(tmp_path / "c.json", retention_jours=45)
    assert c.ajouter([{"id": "1", "source": "leboncoin", "prix": 1}]) == 1
    assert c.ajouter([{"id": "1", "source": "leboncoin", "prix": 2}]) == 0
    c.sauvegarder()
    c2 = Cache(tmp_path / "c.json")
    assert len(c2.actives()) == 1 and c2.actives()[0]["prix"] == 2
