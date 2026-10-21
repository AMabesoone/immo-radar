# Immo Radar

Radar hebdomadaire d'opportunités d'investissement locatif en France, longue et courte durée, analysées à 360 degrés : financement à crédit, cash-flow par scénario d'exploitation, fiscalité comparée, faisabilité réglementaire, risques, score. Tourne tous les jours à 7h30 (Paris) sur GitHub Actions, écrit dans un Google Sheet et publie un tableau de bord HTML sur GitHub Pages.

- Tableau de bord : `docs/index.html` (GitHub Pages, dossier `docs/`)
- Méthodologie et synthèse des bonnes pratiques : [docs/methodologie.md](docs/methodologie.md)
- Rapports de recherche sourcés : [docs/research/](docs/research/)

## Ce que fait le pipeline

1. Collecte les annonces de vente (Bien'ici, immobilier.notaires.fr, CSV manuel) pour les villes de `config/config.yaml`, plus trois circuits à prix décotés : ventes judiciaires de biens saisis (Licitor, tribunaux des villes cibles), ventes notariales interactives (immo-interactif) et cessions immobilières de l'État (Domaines / DGFiP, toute la France).
2. Enrichit chaque annonce avec le marché de sa commune : loyer au m² (Carte des loyers 2025), prix au m² des ventes réelles (DVF 2024 à 2026), prix par nuit et occupation Airbnb (Inside Airbnb), contraintes réglementaires (`config/reglementation.yaml`).
3. Construit le plan de financement (apport x %, notaire, travaux, ameublement, garantie, mensualité assurance comprise).
4. Calcule quatre scénarios (nue, meublé, colocation, courte durée) et compare les régimes fiscaux (micro-foncier, réel, Jeanbrun, micro-BIC, LMNP réel, SCI IS).
5. Note chaque bien sur 100, liste les red flags, les points forts et la checklist avant offre.
6. Publie le top dans Google Sheets et dans le tableau de bord HTML, et mémorise les annonces d'une semaine à l'autre (nouveautés, baisses de prix).

## Installation locale

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_weekly.py --dry-run --limite 30
```

Sans variables Google, le script génère uniquement `docs/index.html`, `docs/data.json` et `data/state.json`.

## Configuration Google Sheets (une fois)

1. Dans Google Cloud, créer un projet, activer les API Google Sheets et Google Drive, créer un compte de service et télécharger sa clé JSON.
2. Créer un Google Sheet vide, le partager en édition avec l'e-mail du compte de service (`xxx@xxx.iam.gserviceaccount.com`).
3. Dans le dépôt GitHub, Settings > Secrets and variables > Actions, ajouter :
   - `GOOGLE_SERVICE_ACCOUNT_JSON` : le contenu complet du fichier JSON
   - `GSHEET_ID` : l'identifiant du classeur (dans l'URL entre `/d/` et `/edit`)
4. Lancer le workflow à la main (Actions > Immo Radar hebdomadaire > Run workflow). Trois onglets sont créés : `Opportunites` (top de la semaine), `Historique` (toutes les semaines), `Parametres`.

L'onglet `Parametres` permet de surcharger n'importe quelle valeur de `config/config.yaml` sans toucher au code : colonne A la clé en notation pointée (`financement.apport_pct`), colonne B la valeur (`0.15` ou `15%`). Exemples : `fiscalite.tmi`, `recherche.prix_max`, `exploitation.longue_duree.gestion_locative_pct` (0 pour autogestion), `exploitation.courte_duree.conciergerie_pct`, `scoring.score_minimum_publication`.

## Alertes e-mail Leboncoin, SeLoger, PAP (lecture IMAP, zéro robot)

Les portails envoient eux-mêmes les nouvelles annonces par e-mail pour une recherche sauvegardée. Le pipeline lit ces e-mails en IMAP et analyse les annonces comme les autres. Aucune visite automatisée des portails.

1. Créer une boîte Gmail dédiée (recommandé, pour ne pas donner au robot l'accès à une boîte personnelle), activer la validation en deux étapes puis créer un mot de passe d'application (Compte Google > Sécurité > Mots de passe des applications).
2. Sur Leboncoin (et SeLoger, PAP...), créer les recherches sauvegardées avec alerte e-mail vers cette boîte : départements 59 et 62, maisons et appartements, budget, « alerte quotidienne » ou « instantanée ».
3. Dans le dépôt, Settings > Secrets and variables > Actions : `IMAP_USER` (l'adresse), `IMAP_PASSWORD` (le mot de passe d'application), `IMAP_HOST` facultatif (`imap.gmail.com` par défaut).
4. Lancer le workflow à la main une fois qu'un premier e-mail d'alerte est arrivé et vérifier dans le log la ligne « Alertes e-mail : N annonces nouvelles ».

Fonctionnement : seuls les e-mails non lus des expéditeurs listés dans `config/config.yaml` (`sources_speciales.alertes_email.expediteurs`) sont lus, puis marqués comme lus. Chaque annonce est extraite (lien, titre, prix, ville, surface, pièces) et conservée 45 jours dans `data/cache/alertes_email.json`. Une annonce sans surface dans l'e-mail n'est pas analysable et est ignorée (le log en donne le nombre). Le format des e-mails change parfois : si l'extraction tombe à zéro, transmettre un e-mail d'exemple pour ajuster `src/immo_radar/sources/email_alerts.py`.

## GitHub Pages

Settings > Pages > Source : Deploy from a branch, branche `main`, dossier `/docs`. Le workflow commite `docs/index.html` et `docs/data.json` à chaque scan.

## Personnaliser

- Villes et catégories, budget, surfaces, mots-clés : `config/config.yaml` section `recherche`.
- Hypothèses financières, opérationnelles et fiscales : sections `financement`, `acquisition`, `exploitation`, `fiscalite`.
- Poids du score et seuil de publication : section `scoring`.
- Règles communales (changement d'usage, compensation, quotas, encadrement des loyers, taxe d'habitation secondaire) : `config/reglementation.yaml`. À relire avant chaque offre, les règlements changent chaque semestre.
- Biens off-market ou alertes e-mail : `data/annonces_manuelles.csv` (voir l'en-tête attendu dans `src/immo_radar/sources/csv_import.py`).
- Alertes e-mail des portails (Leboncoin, SeLoger, PAP, Logic-Immo) : voir la section suivante. Les annonces reçues par e-mail ne sont pas soumises au filtre de budget.
- Alertes Jinka : ouvrir l'alerte connecté dans le navigateur, coller `scripts/jinka_export.js` dans la console (F12), déposer le CSV téléchargé dans `data/jinka/` et commiter. Les biens choisis à la main (sources `jinka` et `manuel`) ne sont pas soumis au filtre de budget. Pour analyser un CSV sans toucher au radar : `python scripts/analyser_csv.py data/jinka/mon-export.csv --top 30`.
- Enchères, ventes interactives, biens de l'État : section `sources_speciales` (activation, coefficient mise à prix vers prix attendu, frais d'enchères 12 %, décote bien occupé, tribunaux supplémentaires à suivre).

## Structure

```
config/        config.yaml (hypothèses), reglementation.yaml (règles communales)
src/immo_radar/
  sources/     bienici.py, notaires.py, licitor.py (encheres judiciaires), immo_interactif.py (VNI), etat.py (Domaines), csv_import.py, http.py
  enrich/      geocode.py, rents.py (carte des loyers), dvf.py, str_market.py (Inside Airbnb), regulation.py
  finance/     loan.py, cashflow.py, tax.py, scoring.py
  outputs/     sheets.py, html.py (+ templates/), state.py
  analysis.py  analyse 360 d'une annonce
  pipeline.py  orchestration hebdomadaire
scripts/run_weekly.py
tests/
docs/          index.html + data.json (Pages), methodologie.md, research/
data/          state.json (mémoire inter-semaines), cache/ (DVF, loyers, Airbnb)
.github/workflows/weekly.yml   cron lundi 05:30 UTC + déclenchement manuel
```

## Sources de données et limites

- Bien'ici : point d'accès JSON public utilisé par le site, sans clé. Peut casser sans préavis.
- immobilier.notaires.fr : API JSON publique du Conseil supérieur du notariat.
- Licitor : annonces légales des ventes aux enchères des tribunaux judiciaires. Lecture des seules pages d'audience des tribunaux cibles, lien vers l'annonce d'origine (cahier des conditions de vente, PV descriptif). Le prix retenu est une adjudication attendue (mise à prix × 1,6, plafonnée à la valeur DVF moins 20 %), les frais sont de 12 % et un bien occupé est décoté de 15 %.
- immo-interactif.fr : API publique des ventes notariales interactives. Prix retenu : première offre × 1,15, plafonné à la valeur DVF moins 5 %.
- cessions.immobilier-etat.gouv.fr : portail officiel des biens de l'État (anciens logements de fonction, maisons forestières). Prix souvent non publié : hypothèse d'offre à la valeur DVF moins 15 %, signalée en alerte. Le portail refuse les connexions depuis les serveurs GitHub (403 hors France) : le cloud utilise `data/cache/etat.json`, rafraîchi à chaque exécution locale (`python scripts/run_weekly.py`) et commité.
- immo-interactif refuse aussi les serveurs GitHub : dans le cloud, les ventes interactives viennent du flux notaires (même annonces, première offre, sans la date d'ouverture).
- Leboncoin et SeLoger : inaccessibles depuis un serveur (DataDome) et protégés juridiquement (jurisprudence Jinka 2026). Pour les couvrir : agrégateur sous licence (stream.estate, Moteurimmo) ou alertes e-mail copiées dans le CSV manuel.
- Carte des loyers 2025 (ministère du Logement, ANIL) : loyer d'annonce charges comprises par commune, licence ouverte.
- DVF géolocalisées (DGFiP, Etalab) : ventes réelles, licence ouverte, publication avril et octobre.
- Inside Airbnb : Paris, Lyon, Bordeaux, Pays basque. Occupation estimée au 3e quartile des logements entiers actifs.

Toutes les valeurs produites sont des estimations à valider sur place avant une offre. Ce dépôt ne constitue pas un conseil en investissement, fiscal ou juridique.
