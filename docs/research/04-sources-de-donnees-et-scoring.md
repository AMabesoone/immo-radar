# Sources de données et scoring pour un pipeline hebdomadaire d'opportunités locatives (France, 2026)

Date de la recherche : 19 octobre 2026. Les endpoints marqués "testé" ont été appelés le jour même depuis une IP datacenter non française (comparable à un runner GitHub Actions). Le budget de recherche web a été consommé intégralement (environ 60 recherches, 60 fetchs) ; les points non vérifiés sont signalés "non vérifié".

Légende "Faisabilité GitHub Actions" : Oui = appel direct depuis un runner GitHub (IP Azure, non résidentielle, non française) fonctionne aujourd'hui ; Partiel = fonctionne avec un intermédiaire (API payante, boîte mail, dataset statique) ou avec un risque de blocage ; Non = bloqué ou juridiquement intenable.

## 0. Résumé exécutif

1. Les deux portails qui concentrent le volume (Leboncoin, SeLoger / Logic-Immo) sont inaccessibles directement depuis un runner GitHub : DataDome renvoie 403 sur `api.leboncoin.fr/finder/search` et sur `seloger.com/list.htm` (testé), et la jurisprudence Jinka (CA Versailles, décembre 2025 et avril 2026 : 60 000 € pour SeLoger, 200 000 € pour Leboncoin, fondement droit sui generis du producteur de bases de données, art. L341-1 CPI) rend l'extraction systématique juridiquement toxique, même par un petit acteur.
2. Trois sources de listings sont exploitables directement, gratuitement et aujourd'hui : l'endpoint JSON interne de Bien'ici (`realEstateAds.json`, testé 200 OK, 100 annonces par page, plafond 2 500 annonces par filtre), l'API JSON publique d'immobilier.notaires.fr (`pub-services/inotr-www-annonces/v1/annonces`, testé 200 OK), et les flux d'alertes email des portails (parsing Gmail API).
3. Pour couvrir Leboncoin et SeLoger légalement, il faut passer par un agrégateur sous licence : stream.estate (ex API Melo, 0,01 € par item en pay-as-you-go, Starter 99 €/mois pour 15 000 items, 1 500+ sources, 5 € de crédits offerts) ou Moteurimmo (API réservée au plan Expert, environ 69 €/mois, 56+ portails). Budget cible : 70 à 100 €/mois.
4. L'enrichissement est entièrement couvert en open data gratuit et stable : DVF géolocalisé (files.data.gouv.fr/geo-dvf, mise à jour avril et octobre), API DVF Etalab `app.dvf.etalab.gouv.fr/api/mutations3/{insee}/{section}` (testé OK), "Carte des loyers" ANIL 2025 (4 CSV, colonne `loypredm2`), Observatoires locaux des loyers (data.gouv, mis à jour octobre 2026), zonage ABC (CSV en vigueur 26 juin 2026), DPE ADEME (API data-fair, 15,8 M lignes, 600 requêtes/minute en anonyme, testé OK), géocodage Géoplateforme `data.geopf.fr/geocodage/search` (testé OK, 50 req/s ; l'ancienne `api-adresse.data.gouv.fr` est décommissionnée depuis fin janvier 2026).
5. Pour la location courte durée, Inside Airbnb ne couvre plus que Bordeaux et Lyon en France (snapshot 17 septembre 2026, Paris absent de la page "Get the data" au 19 octobre 2026). Le meilleur rapport coût/couverture programmatique est Airroi (API 0,01 $ par appel, 10 $ de crédits offerts, 28 endpoints dont Markets API occupancy/ADR/RevPAR, société parisienne). AirDNA et Airbtics sont en devis entreprise pour l'API (Airbtics : datasets à partir de 15 000 $).
6. Formule de scoring proposée (section 6) : 0 à 100 points, 7 composantes pondérées (décote vs DVF 25, rendement brut 20, cash-flow 15, tension 10, DPE 10, upside courte durée 10, signaux d'annonce et qualité de donnée 10), avec filtres durs en amont.

## 1. Sources d'annonces de vente

### 1.1 Tableau de synthèse

| Source | API officielle | Endpoint non officiel connu | Anti-bot | CGU / droit | Coût | GitHub Actions | Verdict |
|---|---|---|---|---|---|---|---|
| Leboncoin | Non | `api.leboncoin.fr/finder/search` (POST JSON), `__NEXT_DATA__` dans les pages | DataDome (JA3/TLS, fingerprint, réputation IP) ; 403 testé | Base de données protégée (jurisprudence Jinka 2026) | Gratuit mais inaccessible | Non | Via agrégateur sous licence ou alertes email |
| SeLoger / Logic-Immo | Non | `list.htm` + JSON embarqué | DataDome ; 403 testé | Idem (Jinka, déc. 2025) | Inaccessible | Non | Via agrégateur ou alertes email |
| Bien'ici | Non | `https://www.bienici.com/realEstateAds.json?filters={json}` | Faible aujourd'hui (200 OK depuis IP datacenter) | CGU non consultables (404) ; même risque sui generis théorique | Gratuit | Oui (risque de rupture) | Source directe n°1 |
| PAP | Non | Pages HTML ; sitemap `liste_annonces.xml` (403 depuis datacenter) ; robots.txt interdit `/*?*` et `/annonce/liste/` | Modérée (403 sur sitemap) | Robots.txt restrictif | Gratuit | Partiel | Alertes email PAP |
| Figaro Immobilier | Non | Pages HTML (fetch impossible depuis l'outil) | Bloqué | Idem | Gratuit | Non | Via agrégateur |
| Jinka | Non (app grand public) | Aucun | s.o. | Condamnée 3 fois en 7 mois | s.o. | Non | À exclure |
| Castorus | Non (extension navigateur, données communautaires) | Aucun | s.o. | Données communautaires, pas d'export | Gratuit | Non | Inspiration seulement (historique de prix) |
| Moteurimmo | Oui (plan Expert) | s.o. | s.o. | Agrégateur commercial, liens vers annonces d'origine | Découverte gratuit, Pro ~9 €, Business ~39 €, Expert ~69 €/mois ; essai 10 jours | Oui | Option B |
| Melo / stream.estate | Oui (REST + webhooks) | s.o. | s.o. | Agrégateur commercial B2B | 0,01 €/item PAYG ; Starter 99 €/mois (15 000 items) ; Growth 399 € (150 000) ; Scale 799 € (350 000) ; 5 € offerts ; Starter gratuit 3 mois pour startups | Oui | Option A |
| Immo-data | Oui (APIs DVF, estimation, prix, DPE, serveur MCP) | s.o. | s.o. | B2B | Non public (pages tarifs 404) | Partiel | Enrichissement, pas d'annonces |
| Yanport | Oui (API + MCP : annonces, DVF, estimations, loyers) | s.o. | s.o. | B2B, foncières, banques | Sur devis ; essai 15 jours | Partiel | Trop cher pour un side project (non vérifié) |
| PriceHubble | Oui (AVM B2B, FR couvert, token 2 h) | s.o. | s.o. | Entreprise | Sur devis | Non | Hors budget |
| Hosman | Non | s.o. | s.o. | Agence en ligne, ~560 biens, diffusés sur SeLoger, Leboncoin, Jinka | s.o. | Non | Redondant |
| immobilier.notaires.fr | Oui de facto (JSON public, non documenté) | `/pub-services/inotr-www-annonces/v1/annonces` | Aucun (200 OK testé) | Pas de licence explicite ; conserver le lien source | Gratuit | Oui | Source directe n°2 |
| Licitor (ventes judiciaires) | Non | Pages HTML `/ventes-judiciaires-immobilieres/tj-{ville}/{date}.html` | Non testé | Mentions "Droits d'auteur" | Gratuit | Partiel | Niche, scraping HTML léger |
| encheres-publiques.com | Non (open data historique seulement) | CSV résultats 2006-2024 sur data.gouv (LOV2) | s.o. | Licence Ouverte | Gratuit | Oui (historique) | Benchmark enchères, pas de flux live |
| Agorastore | Non | Aucun trouvé | Non testé | Plateforme privée | Gratuit | Partiel | Niche collectivités |
| Ventes domaniales (DNID) | Non | Site `ventes-domaniales.fr` injoignable depuis l'outil (connexion refusée) | Probable géoblocage | Service public | Gratuit | Partiel | Non vérifié |
| BOAMP (DILA) | Oui (API BOAMP, dépôt `echanges.dila.gouv.fr/OPENDATA`) | s.o. | s.o. | Licence Ouverte | Gratuit | Oui | Marchés publics, quasi aucune vente immobilière : inutile |
| Hektor | Flux XML / CSV Poliris (FTP) réservés aux agences clientes | s.o. | s.o. | Logiciel d'agence | s.o. | Non | Pas une source tierce |

### 1.2 Détails par source

#### Leboncoin
- Pas d'API publique. L'app et le site appellent `https://api.leboncoin.fr/finder/search` en POST ; un GET nu renvoie 403 (testé le 19/10/2026). Les pages sont en Next.js : le JSON `__NEXT_DATA__` contient `list_id`, `subject`, `price`, `location` (city, zipcode, region), `body`, `attributes` (square, rooms, energy_rate), `owner`. Source : article Scrapfly du 5 octobre 2026 (https://scrapfly.io/blog/posts/how-to-scrape-leboncoin-marketplace-real-estate).
- Protection : DataDome évalue l'empreinte TLS/JA3, l'empreinte navigateur (navigator, WebGL) et la réputation IP. Les clients Python par défaut et les navigateurs headless "stealth" sont détectés ; il faut des IP résidentielles françaises et de vraies empreintes, la simple rotation de proxys ne suffit pas (même source). Les runners GitHub (IP Azure, souvent US) sont bloqués d'office.
- Bibliothèque `lbc` (https://github.com/etienne-hd/lbc, 221 étoiles, Python 3.10+) : client non officiel couvrant la catégorie 9 immobilier avec filtres prix, surface, pièces ; le README recommande délais, proxys propres de préférence français, résidentiels ou mobiles. Donc inutilisable tel quel depuis GitHub Actions.
- Droit : CA Versailles, avril 2026, condamne Jinka à 200 000 € pour extraction et réutilisation d'annonces Leboncoin, les annonces constituant une base de données protégée (CPI L341-1). Tribunal des activités économiques de Versailles, 2 juillet 2026 : pratique commerciale trompeuse (slogan "1 app, tous les sites immo"). Jinka annonce un pourvoi en cassation. Sources : https://www.mysweetimmo.com/2026/04/15/annonces-immobilieres-jinka-condamnee-a-payer-200-000-e-a-leboncoin-en-appel/ et https://www.mysweetimmo.com/2026/07/02/annonces-immobilieres-jinka-condamnee-pour-pratique-commerciale-trompeuse-face-a-seloger/.
- Les CGU (`leboncoin.fr/dc/cgu`) sont elles-mêmes derrière DataDome (403), mais la protection sui generis s'applique indépendamment des CGU dès lors que l'extraction est "qualitativement ou quantitativement substantielle" ou "répétée et systématique" (L342-1 et L342-2 CPI). Un pipeline hebdomadaire sur un marché entier coche la case "répétée et systématique".
- Conclusion : Non en direct. Couvrir Leboncoin via stream.estate ou Moteurimmo (qui assument la licence ou le risque), ou via les alertes email Leboncoin envoyées à une boîte Gmail dédiée (usage personnel, volume faible).

#### SeLoger et Logic-Immo
- Même groupe (AVIV / Groupe SeLoger, Axel Springer ; MeilleursAgents racheté 200 M€). Logic-Immo décline depuis 2018 (5e portail, 3,5 M visites/mois) et partage la stack. `seloger.com/list.htm` renvoie 403 depuis IP datacenter (testé). DataDome.
- Droit : CA Versailles, décembre 2025, 60 000 € contre Jinka (même fondement).
- Dépôts GitHub taggés "seloger" : `SelogerScraper` (déc. 2025), `seloger-real-estate-scraper` (oct. 2026), `FrenchRentalScanner` (mai 2026) existent mais sont de petits projets qui tournent en local avec navigateur réel ; aucun n'annonce fonctionner depuis un CI. Liste : https://github.com/topics/seloger.
- Conclusion : Non en direct. Alertes email SeLoger ou agrégateur.

#### Bien'ici
- Endpoint interne testé OK le 19/10/2026 depuis IP datacenter : `GET https://www.bienici.com/realEstateAds.json?filters=<JSON URL-encodé>`. Exemple de filtre : `{"size":100,"from":0,"filterType":"buy","propertyType":["flat","house"],"page":1,"sortBy":"publicationDate","sortOrder":"desc","onTheMarket":[true],"zoneIdsByTypes":{"zoneIds":["-7444"]}}` (zoneId -7444 = Paris). Réponse : `total` (9 662 appartements à vendre sur Paris), `from`, `perPage`, `realEstateAds[]` avec `id`, `reference`, `price`, `surfaceArea`, `city`, `postalCode`, `energyClassification`, `adType`, `propertyType`, `roomsQuantity`, `bedroomsQuantity`, `floor`, `floorQuantity`, `annualCondominiumFees`, `publicationDate` (ISO), `accountDisplayName`, `blurInfo` (position floutée : type, radius, bbox, position), photos, description. Le `blurInfo.position` donne une géolocalisation approximative exploitable pour le code INSEE.
- Les zoneIds s'obtiennent via l'endpoint de suggestion de zones utilisé par la barre de recherche du site (non vérifié ici ; la bibliothèque `bieniciscraper` sur PyPI, dernière version 1.1.3 du 11 septembre 2023, convertit une URL de recherche en requête API ; dépendances `requests` et `retry`). Plafond : 100 pages de 100 soit 2 500 annonces par filtre, contourné en découpant par zone ou par tranche de prix. Sources : https://pypi.org/project/bieniciscraper et https://apify.com/crawlerbros/bienici-scraper.md.
- Faisabilité GitHub Actions : Oui aujourd'hui ; prévoir un détecteur de rupture (statut 403 / HTML au lieu de JSON) et un fallback agrégateur. Rester sobre : une passe hebdomadaire, quelques centaines de requêtes, User-Agent de navigateur, pause 1 à 2 s. Ne stocker que les champs utiles, ne pas republier photos ni descriptions (droit d'auteur des agences). Bien'ici appartient à un consortium de professionnels (FNAIM, SNPI, etc.) ; le risque juridique est le même en théorie qu'avec Leboncoin, le risque pratique est plus faible tant que l'usage reste personnel et non republié.

#### PAP
- `robots.txt` : `Disallow: /*?*` (toute URL avec query string), `/annonce/liste/`, combinaisons de filtres d'équipement et `location-`/`vente-` croisés. Sitemaps : `https://www.pap.fr/download/sitemap/liste_annonces.xml` (403 depuis IP datacenter lors du test), `immobilier.xml`, `prixm2.xml`.
- Pas d'API ni de RSS confirmé en 2026. Alertes email natives (recherches enregistrées) : c'est la voie recommandée. Un acteur Apify `clearpath/pap-scraper` existe (téléphones et DPE) : hors périmètre juridique souhaité.
- Faisabilité : Partiel (alertes email).

#### Moteurimmo
- Agrégateur français, 56+ portails (Leboncoin, SeLoger, Bien'ici, PAP, ParuVendu, agences indépendantes), données DVF et transactions notaires intégrées, historique de prix, "indicateur de négociation", adresse réelle et DPE sur les plans payants.
- Plans (avis juin 2026, https://investissement-locatif-avis.fr/moteur-immo-avis/) : Découverte gratuit (très limité), Pro ~9 €/mois, Business ~39 €/mois (export CSV/PDF), Expert ~69 €/mois (seul plan avec API). Essai 10 jours sans CB. Documentation API accessible depuis le tableau de bord après abonnement ; un serveur MCP tiers (`MOTEUR_IMMO_API_TOKEN`) expose recherche par prix/surface/localisation, détail par id, analyse de négociation et historique (https://mcp.so/servers/moteurimmo-mcp-server).
- Faisabilité : Oui. Point d'attention : Moteurimmo scrape lui-même Leboncoin et SeLoger ; le risque juridique est porté par Moteurimmo, pas par vous, mais la pérennité du service dépend de l'issue de l'affaire Jinka.

#### Melo / stream.estate
- `melo.io/api` redirige (301) vers `stream.estate` : l'API Melo est commercialisée sous cette marque. Promesse : 1 500+ sources temps réel, 50 M+ annonces dédupliquées, 50 000 nouvelles annonces par jour, 99 % de disponibilité, Search API granulaire (géoloc GPS, références cadastrales, historique des transactions, kWh/m²/an et kgCO2/m²/an, photos dédupliquées, suivi multi-source, "publisher intelligence"), Market Price Evolution (prix au m² historique), webhooks temps réel.
- Tarifs (https://stream.estate/fr/pricing) : pay-as-you-go 0,01 € par item sans engagement ; Starter 99 €/mois pour 15 000 items (0,003 € au-delà) ; Growth 399 €/mois pour 150 000 (0,002 €) ; Scale 799 €/mois pour 350 000 (0,0015 €) ; Enterprise sur devis ; 5 € de crédits offerts à l'inscription ; programme startup : Starter gratuit 3 mois. L'application Melo (interface web) démarre à 24 €/mois avec 14 jours d'essai.
- Un serveur MCP communautaire (`neil-ac/melo-mcp`) existe. Faisabilité : Oui. Pour un pipeline hebdomadaire sur 5 à 10 villes, 5 000 à 15 000 items par mois : 50 à 100 €/mois en PAYG, ou Starter.

#### Immo-data
- Plateforme DVF grand public (explorateur de transactions, estimation gratuite) et offre pro : "API immobilière", "API DVF", "API estimation", "API prix immobilier", "API DPE", serveur MCP. Les pages tarifaires produit renvoient 404 ; tarifs non publics. Un package tiers `immodata-fr` (REST, prix au m² médian/min/max pour 35+ villes et arrondissements, estimation, calcul de rendement) annonce un plan gratuit. Immo-data ne fournit pas d'annonces : c'est de l'enrichissement, redondant avec DVF open data. Faisabilité : Partiel.

#### Yanport
- API et MCP pour développeurs : annonces des grands portails payants, DVF ("prix réels, adresses exactes"), estimations, loyers (ADB 360), permis de construire, données INSEE. Cinq offres (Agent 360, ADB 360, Invest 360, Data 360, API), tarifs sur devis, essai 15 jours, statut sur status.yanport.com, documentation à `/solutions/fournisseur-donnees-immobilieres/api/documentation`. Positionnement foncières, banques, réseaux. Non vérifié : probablement plusieurs centaines d'euros par mois. Faisabilité : Partiel.

#### immobilier.notaires.fr
- Endpoint public testé OK : `GET https://www.immobilier.notaires.fr/pub-services/inotr-www-annonces/v1/annonces?offset=0&page=1&parPage=50&perimetre=0&typeTransaction=VENTE&typeBien=APP&departements=33`. Clés : `annonceResumeDto[]`, `page`, `nbPages`, `parPage`, `nbTotalAnnonces`, `dateServeur`. Champs par annonce : `prix` (hors et avec honoraires), honoraires (montant et pourcentage), `surface`, `codePostal`, `commune`, `typeBien` (APP, MAI, IMM, TER, GAR, LOC, BUR...), `dateCreation`, `urlDetailAnnonceFr`, référence, statut (`LIGNE`), `variation` (`BAISSE`), contact, photos ; DPE, coordonnées GPS et contact notaire sont dans le détail. Un acteur Apify facture 1 à 1,5 $ pour 1 000 annonces en lisant cette même API : inutile, appelez-la directement.
- Volume faible (172 annonces de vente en Gironde toutes catégories au moment du test) mais qualité élevée : prix justes, biens de succession, ventes interactives notariales (enchères en ligne). Portail du Conseil supérieur du notariat, mission de service public de diffusion des prix. Faisabilité : Oui.

#### Enchères et ventes publiques
- Licitor : pas d'API ni de flux ; alertes par compte utilisateur ; pages HTML structurées par tribunal et par date (`/ventes-judiciaires-immobilieres/tj-paris/jeudi-29-octobre-2026.html`) avec mise à prix, adresse, surface, date d'adjudication, avocat. Mention "Droits d'auteur" sans licence ouverte. Un scraping HTML léger hebdomadaire est techniquement simple ; juridiquement gris. Partiel.
- encheres-publiques.com : jeu de données "Distribution des prix de vente des biens immobiliers des tribunaux judiciaires français" (id data.gouv 633444ff817ce64215aac631, LOV2) : `resultats-vente-2006-2024.csv` (3,4 Mo) et `tribunaux-judiciaires.csv`. Utile pour calibrer la décote moyenne obtenue aux enchères par département, pas pour un flux.
- Vench (data.gouv, 0 API), Agorastore (collectivités, 1 500 vendeurs publics, pas d'API trouvée), ventes-domaniales.fr (DNID, injoignable depuis l'outil) : à traiter en V2 par scraping HTML sobre si pertinent.
- BOAMP : API DILA et dépôt OPENDATA (`https://echanges.dila.gouv.fr/OPENDATA/`) couvrent les marchés publics, pas les cessions immobilières : hors sujet.

#### Alertes email comme fallback (approche Gmail)
- Principe : créer des recherches enregistrées sur Leboncoin, SeLoger, PAP, Bien'ici, Figaro Immo avec alerte "instantanée" ou "quotidienne" vers une boîte Gmail dédiée ; le job GitHub Actions lit les mails non lus via l'API Gmail (OAuth client desktop + refresh token stockés en secrets GitHub, scope `gmail.readonly` ou `gmail.modify`), parse le HTML (titre, prix, surface, ville, lien) et marque le mail comme traité (label).
- Avantages : zéro anti-bot, les portails poussent la donnée volontairement vers un utilisateur ; volume faible donc pas d'"extraction substantielle". Limites : champs partiels (DPE et charges souvent absents), tracking links à résoudre, format HTML changeant, environ 20 à 50 annonces par alerte et par jour. Pour un pipeline hebdomadaire ciblant quelques villes, c'est suffisant comme complément.

### 1.3 Classement par faisabilité GitHub Actions

1. immobilier.notaires.fr (Oui, gratuit, stable, légal).
2. Bien'ici `realEstateAds.json` (Oui, gratuit, risque de rupture technique et risque juridique théorique).
3. stream.estate / Melo (Oui, payant, couvre Leboncoin et SeLoger, licence portée par l'agrégateur).
4. Moteurimmo API Expert (Oui, ~69 €/mois, mêmes remarques).
5. Alertes email parsées via Gmail API (Partiel, gratuit, couvre tous les portails en volume limité).
6. Licitor et ventes publiques (Partiel, HTML, niche).
7. Leboncoin, SeLoger, Logic-Immo, Figaro Immo en direct (Non).

## 2. Référentiels de prix et de marché

| Source | URL | Auth | Format | Coût | Licence | GitHub Actions | Notes |
|---|---|---|---|---|---|---|---|
| DVF géolocalisé (Etalab) | `https://files.data.gouv.fr/geo-dvf/latest/csv/{année}/full.csv.gz`, sous-dossiers `communes/` et `departements/` | Aucune | CSV gz | Gratuit | Licence Ouverte 2.0 | Oui | 2021 à 2025 en ligne ; `2025/full.csv.gz` = 98,3 Mo daté 18/05/2026 ; publications avril et octobre (14/04/2025, 22/09/2025, 20/04/2026) |
| API DVF Etalab | `https://app.dvf.etalab.gouv.fr/api/mutations3/{code_insee}/{section}` | Aucune | JSON | Gratuit | LO 2.0 | Oui (testé OK) | Renvoie `mutations[]` : `date_mutation`, `valeur_fonciere`, `surface_reelle_bati`, `type_local`, `nombre_pieces_principales`, adresse, lat/lon ; granularité section cadastrale |
| api.cquest.org/dvf | `https://api.cquest.org/dvf?lat=&lon=&dist=` ou `?code_commune=&type_local=&nature_mutation=` | Aucune | JSON | Gratuit | Communautaire | Partiel | 502 à deux tests le 19/10/2026 : ne pas en dépendre ; code source https://github.com/cquest/dvf_as_api |
| Cerema apidf (DVF+ open data) | `https://apidf-preprod.cerema.fr/dvf_opendata/mutations/?code_insee=` et `geomutations` ; swagger `/swagger/` | Aucune pour dvf_opendata ; token pour DV3F et Fichiers fonciers | JSON | Gratuit | LO 2.0 | Partiel | 503 et timeout aux tests ; wrapper Python `py.apifoncier` (https://github.com/rcadot/py.apifoncier) ; DVF+ 2025-1 (juillet 2025) couvre 2010-2024 ; DV3F par département sur data.gouv (PostgreSQL, CSV, GPKG, fév. 2025) |
| Carte des loyers 2025 (ANIL / DHUP) | Dataset `693aa2feed1bf4da603faa49` ; CSV : `pred-app-mef-dhup.csv`, `pred-app12-mef-dhup.csv`, `pred-app3-mef-dhup.csv`, `pred-mai-mef-dhup.csv` sous `https://static.data.gouv.fr/resources/carte-des-loyers-indicateurs-de-loyers-dannonce-par-commune-en-2025/20251211-14xxxx/` | Aucune | CSV (~4,8 Mo chacun) | Gratuit | LO 2.0, attribution obligatoire "Estimations ANIL, à partir des données du Groupe SeLoger et de leboncoin" | Oui | Publié 11/12/2025 ; 9,1 M annonces 2019-2025 ; loyers charges comprises, non meublé, T3 2025 ; colonnes `INSEE_C`, `LIBGEO`, `EPCI`, `DEP`, `REG`, `loypredm2`, `lwr.IPm2`, `upr.IPm2`, `TYPPRED`, `nbobs_com`, `nbobs_mail`, `R2_adj` ; biens de référence 52 m² (app), 37 m² (T1-T2), 72 m² (T3+), 92 m² (maison) ; prudence si `R2_adj` < 0,5, `nbobs_com` < 30 ou intervalle large |
| Observatoires locaux des loyers (OLL) | Datasets data.gouv `56fd8e8788ee387079c352f7` (national) et `56fd90e8c751df174ac485cb` (par agglomération, ZIP 2024-2025) | Aucune | CSV / ZIP | Gratuit | LO 2.0 | Oui | Mis à jour 15/10/2026 ; loyers médians observés (pas d'annonce) par type, époque, pièces, ancienneté d'occupation ; 37 observatoires, 67 agglomérations ; zones de calcul infra-communales |
| Encadrement des loyers Paris | opendata.paris.fr dataset `logement-encadrement-des-loyers` (data.gouv `5d6f392a06e3e743b4d78afd`), API Opendatasoft `parisdata.opendatasoft.com/api/explore/v2.1/catalog/datasets/logement-encadrement-des-loyers/records` | Aucune | JSON, CSV, GeoJSON | Gratuit | Ouverte | Oui | Champs `annee`, `id_zone`, `nom_quartier`, `piece`, `epoque`, `meuble_txt`, `ref`, `max`, `min` (€/m²) ; mise à jour annuelle au 1er juillet ; référence opposable sur le site DRIHL `referenceloyer.drihl.ile-de-france.developpement-durable.gouv.fr` |
| Encadrement autres villes | data.gouv : Lille, Montpellier, Bordeaux, Plaine Commune, Est Ensemble (jeux déposés par des particuliers, 2023), secteurs Bordeaux (DDTM 33, shapefile/WMS) | Aucune | JSON/CSV/SHP | Gratuit | Variable | Oui | Fraîcheur inégale ; pour Lyon/Villeurbanne, Grand Lyon publie sur data.grandlyon.com (non vérifié) ; utiliser le `max` (loyer majoré) comme plafond du loyer LT dans les zones encadrées |
| Zonage ABC | CSV `https://static.data.gouv.fr/resources/liste-des-communes-selon-le-zonage-abc/20260703-091314/liste-ensemble-des-communes-zonage-abc-en-vigueur-26-juin-2026.csv` | Aucune | CSV | Gratuit | LO 2.0 | Oui | Colonnes code INSEE, nom commune, zone (Abis, A, B1, B2, C) ; 468 communes reclassées et 19 déclassées le 05/09/2025 |
| Géocodage Géoplateforme (BAN) | `https://data.geopf.fr/geocodage/search?q=...&limit=1` ; batch CSV `/geocodage/search/csv` (50 Mo) ; reverse `/geocodage/reverse` | Aucune | GeoJSON | Gratuit | LO 2.0 | Oui (testé OK) | 50 req/s par IP, 429 avec retry-after 5 s au-delà ; propriétés `citycode` (code INSEE), `postcode`, `score`, `type`, `label`, `context`, `x`, `y` ; `api-adresse.data.gouv.fr` décommissionnée fin janvier 2026 |
| DPE ADEME (logements existants) | `https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines?size=&select=&qs=` ; doc `/api-docs.json` | Aucune (clé optionnelle) | JSON | Gratuit | LO 2.0 | Oui (testé OK) | 15,8 M lignes, mise à jour hebdomadaire ; `size` max 10 000, pagination `after`, filtres `qs` (Lucene), `bbox`, `geo_distance` ; quotas anonymes 600 req/60 s, 20 s CPU/60 s, 8 Mo/s ; authentifié 1 200 req/60 s ; champs `adresse_ban`, `identifiant_ban`, `code_postal_ban`, `nom_commune_ban`, `_geopoint`, `etiquette_dpe`, `etiquette_ges`, `surface_habitable_logement`, `type_batiment`, `periode_construction`, `annee_construction`, `conso_5_usages_par_m2_ep`, `emission_ges_5_usages_par_m2`, `date_etablissement_dpe`, `numero_dpe` ; les annonces affichent souvent le `numero_dpe` (13 caractères), sinon matcher par adresse BAN + surface à ±3 m² |
| INSEE (recensement, logement) | Portail `portail-api.insee.fr` : API Melodi, API Données locales, BDM, Sirene ; fichiers statiques "base-cc-logement" sur insee.fr | Clé API (inscription gratuite) pour les API ; aucune pour les CSV | JSON / CSV | Gratuit | LO | Oui | Indicateurs utiles par commune : part de locataires, part de résidences secondaires, taux de logements vacants, population et évolution, part des 15-29 ans ; le portail est une SPA (contenu non lu par fetch), consulter la doc Melodi (`https://www.insee.fr/fr/information/8184146`) ; non vérifié : noms exacts des datasets Melodi |
| MeilleursAgents / SeLoger prix au m² | Site grand public, pas d'API ouverte (AVIV) | s.o. | s.o. | Payant pros | Base protégée | Non | Remplacer par médianes DVF calculées en interne |
| Indices notaires-INSEE | insee.fr séries BDM (indices trimestriels prix logements anciens) | Clé API BDM ou CSV | SDMX / CSV | Gratuit | LO | Oui | Tendance de marché par zone (France, IdF, province) ; peu utile au niveau commune |
| Castorus (historique prix) | Extension, pas d'export | s.o. | s.o. | Gratuit | Communautaire | Non | Reconstituer l'historique en interne (section 5.4) |
| LocService tensiomètre | `https://www.locservice.fr/tensiometre/tensiometre-{id}.html` | Aucune | HTML | Gratuit | Pas de licence | Partiel | Score = demandes / offres sur 12 mois, sans plafond ; pages vides pour les petites communes ("marché pas suffisamment actif") ; observatoire national annuel en PDF (édition 2026 sur données 2025, 100 000+ offres et demandes) ; usage ponctuel seulement |
| Bien'ici indice de tension | Non vérifié | s.o. | s.o. | s.o. | s.o. | Non | Préférer les proxys ci-dessous |

Proxy de tension locative gratuit et reproductible : combiner (a) zonage ABC, (b) taux de vacance INSEE, (c) largeur relative de l'intervalle `upr.IPm2 - lwr.IPm2` sur `loypredm2` et `nbobs_com` de la carte des loyers (marché actif = intervalle étroit, beaucoup d'observations), (d) ratio loyer annuel / prix au m² DVF (rendement de zone), (e) part de locataires INSEE. Voir pondération en section 6.

Benchmark prix au m² recommandé : calculer soi-même, à partir de `full.csv.gz` des deux dernières années, la médiane et les quartiles de `valeur_fonciere / surface_reelle_bati` par (code_commune, type_local) et par (code_commune, section cadastrale, type_local) en filtrant `nature_mutation = Vente`, mono-lot ou `nombre_lots <= 2`, surface entre 9 et 400 m², prix au m² entre 300 et 30 000 €, puis stocker le résultat en Parquet dans le dépôt (quelques Mo). Rafraîchir le Parquet à chaque publication DVF (avril, octobre). Pour un bien précis, l'API `mutations3/{insee}/{section}` donne les comparables de la section en temps réel.

## 3. Données location courte durée

| Source | URL | Auth | Format | Coût | Couverture France | GitHub Actions | Notes |
|---|---|---|---|---|---|---|---|
| Inside Airbnb | `https://insideairbnb.com/get-the-data/` ; fichiers `https://data.insideairbnb.com/france/{region}/{ville}/{date}/data/listings.csv.gz` (+ calendar, reviews) | Aucune | CSV gz | Gratuit | Bordeaux et Lyon seulement (snapshot 17/09/2026) ; Paris absent de la page au 19/10/2026 ; archives France sur demande | Oui | CC BY 4.0 ; trimestriel ; `listings.csv.gz` contient `price`, `availability_365`, `number_of_reviews_ltm`, `reviews_per_month`, `room_type`, `bedrooms`, `neighbourhood`, lat/lon, `estimated_occupancy_l365d` et `estimated_revenue_l365d` sur les snapshots récents (modèle "San Francisco" : avis × taux d'avis 50 % × séjour moyen, plafonné à 70 %) |
| Airroi | `https://www.airroi.com/api`, doc `/api/documentation` | Clé API | JSON | 0,01 $ par appel minimum, 10 $ offerts, pas d'abonnement | 190+ pays, 20 M+ biens, 15 ans d'historique | Oui | 28 endpoints : Listings API (recherche par marché, rayon, polygone, comparables, tarifs futurs 365 j), Markets API (occupation, ADR, RevPAR, revenus, saisonnalité), Calculator API (projection de revenus à partir d'une adresse et de specs), Price Recommendation ; société basée à Paris ; meilleur rapport coût/utilité pour ce projet |
| AirDNA | `airdna.co` | Compte / contrat | Web, API entreprise | Gratuit limité (Rentalizer bridé, 1 an d'historique) ; plans Research, Host, Property Manager sur devis ; API sur Order Form, facturée à l'unité (jusqu'à 25 résultats par unité) ; +10 % au renouvellement | 13 625 villes FR, mise à jour mensuelle | Non (API hors budget) | Anciens tarifs publics 19,95 / 39,95 / 99,95 $ par mois selon taille de marché ; pages marché publiques (`/vacation-rental-data/app/fr/...`) donnent ADR, occupation, revenus par ville (ex. Paris juillet 2026 : 76 096 annonces actives, 65 % d'occupation, ADR 240 $, revenu TTM 27,3 k$) mais scraping contraire aux CGU |
| Airbtics | `airbtics.com/pricing` | Compte | Web, CSV, API | Expert 29 $/mois (349 $/an), Scale 239 $/mois (750 $/an, export 1 000 lignes/mois) ; API et datasets à partir de 15 000 $ | Rapport France 2025 : Paris 80 % d'occupation, ADR 164 €, 45 098 annonces ; Lyon 72 %, 94 € ; Bordeaux 72 %, 106 € | Non (API) / Partiel (export CSV manuel) | Utile pour calibrer des ratios nationaux |
| PriceLabs Market Dashboards | `hello.pricelabs.co/market-data` | Compte | Web | 1 dashboard offert, puis 9,99 $ par dashboard et par mois | Monde | Non | Pas d'API marché ; lecture manuelle |
| Transparent, Mashvisor | s.o. | Entreprise | s.o. | Devis / Mashvisor US seulement | Non | Non | À écarter |
| Airbnb (API non officielle) | GraphQL `StaysSearch` via `pyairbnb` (dernière release février 2026, 126 étoiles) : `get_details`, `get_price`, `get_calendar`, `get_reviews` | Aucune | JSON | Gratuit | Monde | Partiel | Blocage par empreinte TLS sans `curl_cffi` ; quelques centaines d'annonces par recherche ; donne prix affichés et disponibilités, pas les réservations ; mainteneur unique ; depuis un runner GitHub, taux de succès incertain : utiliser seulement pour un échantillon d'ADR |
| INSEE tourisme | Enquête de fréquentation hôtels, campings, AHCT (mensuelle, niveau département et grandes villes) | CSV / BDM | Gratuit | LO | Oui | Oui | Pas de donnée meublés de tourisme au niveau commune ; sert de saisonnalité départementale |
| Taxe de séjour | Jeux épars sur data.gouv (ex. "SLA - Taxe de séjour depuis 2018") et sites d'offices de tourisme | Aucune | CSV | Gratuit | LO | Partiel | Hétérogène ; utile ponctuellement pour valider le poids des meublés dans une commune |

### 3.1 Estimer ADR et occupation par commune gratuitement (méthode proxy)

1. Occupation : si la commune est dans Inside Airbnb (Lyon, Bordeaux et leurs communes limitrophes dans le périmètre du snapshot), prendre la médiane d'`estimated_occupancy_l365d` des logements entiers de même typologie (chambres) dans un rayon de 1 km. Sinon, appliquer un taux régional de référence issu des rapports publics Airbtics/AirDNA 2025-2026 (grandes métropoles 65 à 75 %, littoral et montagne saisonniers 45 à 55 %, villes moyennes 40 à 50 %, rural 25 à 35 %), pondéré par la saisonnalité INSEE du département.
2. ADR : interroger Airroi Markets API pour la commune (0,01 $ par appel : pour 500 communes, 5 $) ; à défaut, échantillonner 50 annonces Airbnb via `pyairbnb` sur une date hors saison et une date haute saison et prendre la médiane pondérée. Vérifier la cohérence avec la règle empirique ADR mensuel ≈ 1,8 à 2,5 fois le loyer LT mensuel au m² dans les métropoles.
3. Revenu net CD annuel = ADR × 365 × occupation × (1 − 0,15 commission et frais de plateforme) − ménage et consommables (≈ 12 % du CA) − charges fixes (énergie, internet, assurance PNO, abonnement de gestion) ; appliquer une décote de 30 % si le bien n'est pas la résidence principale et si la commune impose changement d'usage avec compensation (Paris, Lyon, Nice, Bordeaux, Lille et une partie du littoral basque) ou un plafond à 90 nuits (loi Le Meur, novembre 2024). Depuis 2025, un meublé de tourisme nouvellement mis en location doit avoir un DPE entre A et E (D exigé en 2034) et l'abattement micro-BIC est tombé à 30 % (non classé) ou 50 % (classé) : intégrer ces règles comme filtres dans la composante "upside CD".

## 4. Méthodologies de scoring des outils investisseurs

| Outil | Métriques affichées | Formules ou seuils publics | Source |
|---|---|---|---|
| Lybox | Rendement brut, rendement net, cash-flow, positionnement marché (historique de prix sur republications, comparaison au prix de marché local, tension par secteur) | Brut = 12 × loyer / (prix + frais de notaire) ; Net = 12 × (loyer − charges) / (prix + notaire) ; cash-flow avec crédit 20 ans, 10 % d'apport, taux standard ; les rendements affichés servent de pré-filtre ; plans 11 / 29 / 59 € par mois ; 1 500 portails agrégés | https://investissement-locatif-avis.fr/lybox-avis/ |
| Horiz.io (ex Rendement Locatif) | Rendement net, cash-flow mensuel, rendement patrimonial, enrichissement, TAEG ; rapport en 9 sections (coûts, revenus, fiscalité, crédit, régime, plus-value, adéquation prix, loyer adéquat) ; rendement brut moyen par ville (Paris 3,9 %, Saint-Étienne 9,8 %) ; plugin navigateur sur Leboncoin et SeLoger affichant loyer estimé et prix au m² | Pas de note sur 10 publique ; premium à partir de 9,99 €/mois (engagement 12 mois) ; clé en main 5,5 % TTC du prix FAI (min 7 000 €) | https://horiz.io/ et https://www.immobilier-danger.com/avis-horiz-io.html |
| Bevouac | Trois critères : rentable, facile à louer, prend de la valeur ; sélection de villes sur part de locataires, part d'étudiants, évolution du prix au m² sur 5 ans, rendement brut | Promesse 6 à 10 % brut | https://www.mysweetimmo.com/2021/10/26/investissement-locatif-bevouac-promet-entre-entre-6-et-10-de-rendement-locatif-brut/ |
| Moteurimmo | Indicateur de négociation (écart prix d'annonce vs DVF et historique de baisse), historique de prix, calculateur de rendement | Non publié | https://moteurimmo.fr/ |
| Beanstock, Masteos, Flatlooker, Investimmob | Sites inaccessibles lors du test (certificat expiré, 403) | Non vérifié ; d'après leur communication passée : rendement brut cible 5 à 8 % en métropoles, sélection sur décote, tension et travaux valorisants | Non vérifié |

Ce qui fait une "bonne affaire" dans ces outils, par ordre d'importance observé : (1) décote du prix demandé par rapport au marché (DVF et annonces comparables), (2) rendement brut cible par type de ville (≥ 6 % hors Paris et grandes métropoles, ≥ 4,5 % à Paris et Lyon), (3) cash-flow proche de zéro ou positif avec financement à 100 % sur 20 ans, (4) tension locative (facile à louer, faible vacance), (5) DPE non F ou G (interdiction de location des G depuis 2025, F en 2028, E en 2034 ; décote de 10 à 20 % des passoires), (6) travaux : les outils valorisent un bien à rénover acheté avec décote supérieure au coût des travaux, (7) signaux d'annonce : baisse de prix, ancienneté, mots-clés (succession, divorce, urgent, travaux, "à rafraîchir"), vendeur particulier, honoraires inclus.

## 5. Stack technique

### 5.1 GitHub Actions cron
- Syntaxe : `on: schedule: - cron: '30 5 * * 1'` (lundi 05:30 UTC). Depuis mars 2026, champ optionnel `timezone: Europe/Paris` à côté de chaque entrée cron. Intervalle minimum 5 minutes. Retards fréquents de 15 à 30 minutes aux heures pleines : ne jamais dépendre de l'heure exacte.
- Les workflows planifiés d'un dépôt public sont désactivés après 60 jours sans activité : faire committer au workflow lui-même un fichier de données (`data/latest.json`, horodatage) à chaque run, ou utiliser une action keepalive. Prévoir `workflow_dispatch` pour relance manuelle.
- Les runners hébergés sortent sur des IP Azure, majoritairement US : DataDome bloque, et certains sites français géobloquent (ventes-domaniales.fr injoignable). Pas de proxy résidentiel dans le périmètre choisi.
- Limites utiles : 6 h par job, 2 000 minutes/mois gratuites sur dépôt privé (illimité sur dépôt public), cache `actions/cache` jusqu'à 10 Go pour stocker le Parquet DVF et l'état de déduplication.

### 5.2 Écriture Google Sheets
- Créer un projet GCP, activer Google Sheets API et Google Drive API, créer un compte de service, télécharger la clé JSON, partager la feuille avec l'email du compte de service en éditeur.
- Stocker le JSON entier dans un secret `GOOGLE_SERVICE_ACCOUNT_JSON` ; en Python : `gc = gspread.service_account_from_dict(json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]))` puis `ws.update(range, values)` ou `ws.batch_update([...])`.
- Quotas Sheets API : 300 requêtes par minute et par projet, 60 par minute et par utilisateur ; grouper les écritures (une requête `update` par onglet), éviter les `append_row` unitaires. Limite 10 M cellules par classeur : purger l'historique brut au-delà de 12 mois ou le déporter dans un onglet archivé. Référence : https://docs.gspread.org/en/master/oauth2.html.
- Alternative sans Google : CSV commité dans le dépôt + dashboard Pages lisant le CSV.

### 5.3 GitHub Pages
- Le job écrit `docs/data/opportunites.json` et `docs/index.html` (HTML statique + JS vanilla ou Alpine, tableau triable, filtres ville/type/score), puis commit sur `main` (Pages configuré sur `/docs`) ou déploiement via `actions/upload-pages-artifact` + `actions/deploy-pages`. Pas de données personnelles (téléphone, nom du vendeur) dans le JSON public ; lien vers l'annonce d'origine plutôt que reproduction des photos et descriptions (droit d'auteur et jurisprudence Jinka).

### 5.4 Déduplication et historique inter-semaines
- Clé primaire : `(source, id_source)`. Clé de rapprochement multi-sources : hachage de (`code_insee`, `type_bien`, `round(surface)`, `round(prix / 2500)`, `nb_pieces`) plus comparaison des 300 premiers caractères normalisés de la description (similarité de Jaccard ≥ 0,6) et, si disponible, perceptual hash de la première photo. Les agrégateurs payants fournissent déjà un id dédupliqué.
- État persistant : table SQLite ou Parquet commitée dans `data/state/` (quelques Mo) avec `first_seen`, `last_seen`, `price_history` (liste de couples date/prix), `status` (active, disparue après 2 runs manqués, vendue si le prix réapparaît dans DVF 6 à 12 mois plus tard). Cela reconstitue l'équivalent de l'historique Castorus.
- Signaux dérivés : nombre de jours en ligne, nombre et amplitude des baisses, réapparition sous un autre id (relisting).

### 5.5 Projets open source comparables (état 2026)
- `untoitpourcaramel` (Python, 51 étoiles, mis à jour janvier 2026) : agrège des annonces vers Trello ; `immosheets` (46 étoiles, octobre 2025) : annonces vers Google Sheets ; `FrenchRentalScanner` (mai 2026) : tableau de bord de sites de location ; `Hobo-Sapiens` (60 étoiles, 2023) : bot Telegram SeLoger, Leboncoin, Figaro ; `api-immo-scrapper-leboncoin-pap` (71 étoiles, 2020, mort) ; `lbc` (221 étoiles) client Leboncoin non officiel nécessitant proxys ; `scrapfly-scrapers/leboncoin-scraper` (dépend du service payant Scrapfly) ; `bieniciscraper` (2023, principe toujours valide) ; `py.apifoncier` (Cerema), `cquest/dvf_as_api`, `etalab/DVF-app` ; `Leboncoin-Investment-Opportunity` (notebook, calcul de rentabilité). Listes : https://github.com/topics/leboncoin, https://github.com/topics/seloger, https://github.com/topics/immobilier.
- Enseignement commun : tout ce qui touche Leboncoin et SeLoger en direct casse régulièrement ou exige un navigateur réel et une IP française ; les projets durables s'appuient sur Bien'ici, les alertes email, ou un agrégateur.

## 6. Architecture recommandée

```
GitHub Actions (cron lundi 05:30 Europe/Paris, workflow_dispatch)
  |
  |-- 1. Collecte des annonces (parallèle, tolérante aux pannes)
  |     a. Bien'ici realEstateAds.json (par zone, par tranche de prix, 100/page)     gratuit
  |     b. immobilier.notaires.fr /v1/annonces (par département, VENTE, APP+MAI+IMM) gratuit
  |     c. stream.estate Search API ou Moteurimmo API (Leboncoin, SeLoger, PAP...)   70 à 100 €/mois
  |     d. Gmail API : alertes email Leboncoin, SeLoger, PAP, Figaro (fallback)       gratuit
  |     e. (V2) Licitor HTML, ventes interactives notaires, Agorastore
  |
  |-- 2. Normalisation + déduplication (schéma unique, clés de rapprochement, état SQLite/Parquet)
  |
  |-- 3. Enrichissement
  |     a. Géocodage data.geopf.fr -> code INSEE, coordonnées (50 req/s)
  |     b. Prix de référence : Parquet DVF médianes par commune/section/type (rafraîchi avril, octobre)
  |        + API mutations3 pour les comparables de section
  |     c. Loyer LT : carte des loyers 2025 (loypredm2 selon type et T1-T2 / T3+ / maison),
  |        plafonné par l'encadrement (max) dans les villes encadrées, recoupé OLL si disponible
  |     d. DPE : ADEME lines (numero_dpe ou adresse BAN + surface)
  |     e. Tension : zonage ABC, INSEE vacance et part locataires, largeur d'intervalle carte des loyers
  |     f. Courte durée : Airroi Markets/Calculator API (0,01 $/appel) ; Inside Airbnb pour Lyon, Bordeaux
  |
  |-- 4. Scoring 0-100 (section 7) + filtres durs + explication par composante
  |
  |-- 5. Sorties
        a. Google Sheets (gspread, compte de service) : onglets Opportunités, Historique, Référentiels
        b. GitHub Pages : docs/index.html + docs/data/opportunites.json (liens vers annonces d'origine)
        c. Commit de l'état (data/state) -> maintient le cron actif
```

Règles de prudence : respecter robots.txt et un rythme sobre (1 à 2 s entre requêtes, moins de 1 000 requêtes par source et par run) ; ne stocker que les champs nécessaires au scoring ; jamais de coordonnées de vendeurs particuliers (RGPD) ; pas de republication des textes et photos ; conserver et afficher la source et le lien ; détecter les ruptures (JSON attendu, taux de 403) et basculer sur l'agrégateur ; journaliser les volumes par source dans un onglet "Santé du pipeline".

Budget mensuel : 0 € (Bien'ici, notaires, open data, Gmail) à environ 100 € (stream.estate PAYG ou Starter, ou Moteurimmo Expert, plus 5 à 10 $ d'Airroi).

## 7. Formule de scoring recommandée

### 7.1 Filtres durs (exclusion avant scoring)
- Prix > 20 000 € et surface ≥ 9 m² ; type ∈ {appartement, maison, immeuble} ; exclure viager, nue-propriété, parking, terrain, commerce (sauf immeuble de rapport).
- Prix au m² de l'annonce entre 0,3 et 3 fois la médiane DVF de la commune (élimine erreurs de saisie et biens hors norme).
- Données minimales : prix, surface, code INSEE, loyer de référence disponible (`loypredm2` avec `nbobs_com` ≥ 10 ou OLL).
- DPE G exclu pour la stratégie LT sauf si "travaux" déjà pris en compte et budget rénovation estimé.

### 7.2 Variables calculées
- `prix_total = prix × 1,075` (frais de notaire ancien ~7,5 %) `+ travaux_estimes` (0 par défaut ; 400 €/m² si DPE F ou mots-clés "à rénover", 800 €/m² si "gros travaux").
- `prix_m2_ref` = médiane DVF 24 mois (section si ≥ 8 ventes, sinon commune, sinon EPCI) ajustée par type ; `decote = 1 − (prix / surface) / prix_m2_ref`.
- `loyer_mensuel_LT = loypredm2 × surface × 0,93` (passage charges comprises vers hors charges, approximation ; affiner avec OLL quand disponible), plafonné par `max` d'encadrement le cas échéant.
- `rendement_brut = 12 × loyer_mensuel_LT / prix_total`.
- `cash_flow = loyer_mensuel_LT × (1 − 0,08 vacance − 0,07 gestion − 0,10 entretien et charges non récupérables) − taxe_fonciere / 12 (≈ 1 mois de loyer / 12) − mensualité(prix_total, 20 ans, 3,4 %, apport 0)`.
- `revenu_CD = ADR × 365 × occupation × 0,85 − 0,12 × CA − 1 800 € fixes` ; `ratio_CD = revenu_CD / (12 × loyer_mensuel_LT)`.
- `tension` ∈ [0,1] = 0,35 × zone (Abis 1, A 0,9, B1 0,7, B2 0,4, C 0,2) + 0,25 × (1 − min(vacance_INSEE / 0,12, 1)) + 0,2 × part_locataires normalisée + 0,2 × (1 − min((upr − lwr) / loypredm2 / 0,5, 1)).
- `dpe_score` : A, B, C = 1 ; D = 0,8 ; E = 0,5 ; F = 0,2 ; G = 0 ; inconnu = 0,5.
- `signaux` ∈ [0,1] : +0,3 si baisse de prix ≥ 5 % dans l'historique interne ou flag `variation = BAISSE` ; +0,2 si en ligne depuis > 60 jours ; +0,2 si mots-clés "succession", "divorce", "urgent", "travaux", "à rafraîchir" ; +0,15 si vendeur particulier ou notaire ; +0,15 si honoraires inclus et charges de copropriété connues (qualité de donnée) ; plafonné à 1.

### 7.3 Pondération (total 100)

| Composante | Points | Fonction de score | Justification |
|---|---|---|---|
| Décote vs marché DVF | 25 | 0 pt à décote ≤ −10 % (surcote), linéaire jusqu'à 25 pt à décote ≥ +25 % ; si décote > 40 %, plafonner à 20 pt et marquer "à vérifier" (erreur ou vice probable) | C'est le premier critère de tous les outils (Lybox, Moteurimmo, Castorus) et le seul gain certain à l'achat |
| Rendement brut LT | 20 | < 4 % : 0 ; 4 à 6 % : 0 à 10 ; 6 à 9 % : 10 à 18 ; ≥ 9 % : 20 ; > 13 % : 15 et drapeau "suspect" | Seuils alignés sur les cibles Bevouac (6 à 10 %), Horiz (villes 3,9 à 9,8 %) et Beanstock |
| Cash-flow net estimé | 15 | ≤ −300 €/mois : 0 ; −300 à 0 : 0 à 10 ; 0 à +200 : 10 à 15 | Mesure l'effort d'épargne ; critère n°2 chez Lybox et Horiz |
| Tension et liquidité | 10 | 10 × tension | Facile à louer et à revendre (Bevouac) ; limite la vacance |
| DPE et travaux | 10 | 10 × dpe_score, moins 3 si travaux estimés > 15 % du prix et décote < travaux | Calendrier d'interdiction G 2025, F 2028, E 2034 ; condition DPE A à E pour les meublés de tourisme depuis 2025 |
| Upside courte durée | 10 | 0 si commune non éligible (changement d'usage avec compensation, plafond 90 nuits non compatible) ; sinon ratio_CD ≤ 1 : 0 ; 1 à 2 : 0 à 8 ; ≥ 2 : 10 | Capture la valeur optionnelle de la CD sans la rendre nécessaire |
| Signaux d'annonce et qualité | 10 | 10 × signaux | Baisse de prix et ancienneté sont les signaux de négociabilité les plus prédictifs (Moteurimmo, Castorus) |

Score final = somme, arrondi à l'entier. Affichage par paliers : ≥ 75 "opportunité forte", 60 à 74 "à étudier", 45 à 59 "marché", < 45 "passer". Chaque bien conserve le détail des 7 composantes et des hypothèses (loyer retenu, prix de référence, nombre de ventes DVF utilisées, DPE source) pour que l'utilisateur puisse contester une hypothèse dans la feuille.

### 7.4 Variantes de profil
- Profil "cash-flow" (investisseur LMNP/colocation) : rendement 25, cash-flow 20, décote 20, tension 10, DPE 10, CD 5, signaux 10.
- Profil "patrimonial" (métropole, revente) : décote 30, tension 15, DPE 15, rendement 15, cash-flow 5, CD 5, signaux 15.
- Profil "courte durée" (littoral, montagne, villes touristiques éligibles) : CD 25, décote 20, rendement 10, cash-flow 10, DPE 15 (seuil E obligatoire), tension 10, signaux 10.

### 7.5 Validation du scoring
- Backtest : rejouer le score sur les annonces disparues puis retrouvées dans DVF (prix de vente réel) pour vérifier que les scores élevés correspondent à des négociations faibles et des rendements effectifs plus hauts ; recalibrer les bornes des fonctions par quantiles par type de ville tous les six mois.
- Contrôle de cohérence : alerter si plus de 5 % des annonces d'une source obtiennent une décote > 30 % (signe d'un mauvais référentiel ou d'un changement de format).

## 8. Sources principales consultées

- Scrapfly, Leboncoin scraping guide (5 octobre 2026) : https://scrapfly.io/blog/posts/how-to-scrape-leboncoin-marketplace-real-estate
- Jinka vs Leboncoin, CA Versailles avril 2026 : https://www.mysweetimmo.com/2026/04/15/annonces-immobilieres-jinka-condamnee-a-payer-200-000-e-a-leboncoin-en-appel/ ; Jinka vs SeLoger, juillet 2026 : https://www.mysweetimmo.com/2026/07/02/annonces-immobilieres-jinka-condamnee-pour-pratique-commerciale-trompeuse-face-a-seloger/ ; analyse : https://blog.qoridor.fr/article/annonces-immobilieres-cour-condamne
- Bien'ici : https://pypi.org/project/bieniciscraper ; https://apify.com/crawlerbros/bienici-scraper.md ; endpoint testé `https://www.bienici.com/realEstateAds.json`
- Notaires : endpoint testé `https://www.immobilier.notaires.fr/pub-services/inotr-www-annonces/v1/annonces` ; https://apify.com/webdata_labs/france-notaires-property-api.md
- stream.estate (API Melo) : https://stream.estate/fr/pricing ; https://www.melo.io/tarifs
- Moteurimmo : https://moteurimmo.fr/ ; https://investissement-locatif-avis.fr/moteur-immo-avis/ ; https://mcp.so/servers/moteurimmo-mcp-server
- Yanport : https://www.yanport.com/ ; Immo-data : https://www.immo-data.fr/ ; PriceHubble : https://rubydoc.info/gems/pricehubble
- Lybox : https://investissement-locatif-avis.fr/lybox-avis/ ; Horiz.io : https://horiz.io/ et https://www.immobilier-danger.com/avis-horiz-io.html ; Bevouac : https://www.mysweetimmo.com/2021/10/26/investissement-locatif-bevouac-promet-entre-entre-6-et-10-de-rendement-locatif-brut/
- DVF : https://files.data.gouv.fr/geo-dvf/latest/csv/ ; `https://app.dvf.etalab.gouv.fr/api/mutations3/33063/000AB` (testé) ; https://github.com/cquest/dvf_as_api ; https://github.com/rcadot/py.apifoncier ; https://www.data.gouv.fr/datasets/dvf-open-data ; https://www.data.gouv.fr/datasets/cerema-dv3f
- Carte des loyers 2025 : https://www.data.gouv.fr/datasets/693aa2feed1bf4da603faa49/ et guide des variables (PDF) ; OLL : datasets data.gouv 56fd8e8788ee387079c352f7 et 56fd90e8c751df174ac485cb ; ANIL : https://www.anil.org/etudes-loyers-parc-prive-en-france-oll-edition-2026/
- Encadrement Paris : https://opendata.paris.fr/explore/dataset/logement-encadrement-des-loyers/information/ ; DRIHL : http://www.referenceloyer.drihl.ile-de-france.developpement-durable.gouv.fr/
- Zonage ABC : https://www.data.gouv.fr/datasets/liste-des-communes-selon-le-zonage-abc
- Géocodage : `https://data.geopf.fr/geocodage/search` (testé) ; https://www.data.gouv.fr/dataservices/api-geoplateforme-geocodage ; https://dev.to/outsendxyz/batch-geocoding-at-scale-with-frances-free-ban-api-thresholds-chunks-and-zero-lock-contention-42lo
- DPE ADEME : https://data.ademe.fr/datasets/dpe03existant ; `https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines` (testé) ; `/api-docs.json`
- INSEE API : https://www.insee.fr/fr/information/8184146 ; https://www.data.gouv.fr/dataservices/api-melodi
- LocService : https://www.locservice.fr/_media/LocService%20fr%20-%20Observatoire_2026_National.pdf
- Inside Airbnb : https://insideairbnb.com/get-the-data/ ; Airroi : https://www.airroi.com/api ; AirDNA : https://checkthat.ai/brands/airdna/pricing ; Airbtics : https://airbtics.com/pricing/ et https://airbtics.com/short-term-rental-market-report-2025-france ; PriceLabs : https://help.pricelabs.co/portal/en/kb/articles/market-intel-dashboard ; pyairbnb : https://www.airroi.com/blog/best-airbnb-scrapers
- Enchères : https://www.licitor.com/ ; https://www.data.gouv.fr/organizations/encheres-publiques ; BOAMP : https://www.data.gouv.fr/datasets/boamp
- GitHub Actions : https://github.com/orgs/community/discussions/185355 ; https://dev.to/gautamkrishnar/how-to-prevent-github-from-suspending-your-cronjob-based-triggers-knf ; https://cronuru.com/dialects/github-actions
- gspread : https://docs.gspread.org/en/master/oauth2.html ; https://fulowa.medium.com/how-to-update-a-google-sheet-with-github-actions-using-python-3126669d73a8
- Dépôts : https://github.com/topics/leboncoin ; https://github.com/topics/seloger ; https://github.com/topics/immobilier ; https://github.com/etienne-hd/lbc
