# Méthodologie : l'approche 360 derrière Immo Radar

Date : 19 octobre 2026. Ce document résume ce que les meilleurs investisseurs, courtiers, fiscalistes et gestionnaires font avant d'acheter un bien locatif financé à crédit, et comment le module le traduit en calculs. Les quatre rapports de recherche détaillés (avec une URL par chiffre) sont dans `docs/research/`.

## 1. Le verdict de la recherche en six points

1. **L'autofinancement en 100 % crédit exige 8,5 à 10 % de rendement brut sur coût total.** Aux taux d'octobre 2026 (3,55 à 3,75 % hors assurance, +0,2 point de surcote investisseur), 100 000 € empruntés coûtent environ 585 €/mois sur 20 ans et 511 €/mois sur 25 ans. Pour que loyers moins charges couvrent la mensualité, il faut 8,4 à 9,7 % brut sur 25 ans et 9,6 à 11 % sur 20 ans. Pour être neutre dans le calcul bancaire (70 % des loyers retenus), environ 9,9 %.
2. **Ce niveau n'existe pas dans les métropoles.** Paris 3,9 %, Lyon 3,8 à 4,5 %, Bordeaux 4 à 4,5 %. Il se trouve dans les villes moyennes à prix bas (Saint-Étienne, Mulhouse, Limoges, Le Havre, Perpignan : 8 à 11 % brut), via l'immeuble de rapport (décote en bloc 15 à 25 %), la colocation (1,5 à 2,5 fois le loyer classique), la division, ou l'achat décoté (DPE F/G, succession, enchères, bien occupé).
3. **La banque est la contrainte structurante.** Règles HCSF : 35 % de taux d'effort assurance comprise, 25 ans maximum (27 avec différé si travaux ≥ 10 %), loyers pondérés à 70 %, méthode "classique" obligatoire. Le 110 % existe mais reste exceptionnel : bon profil, bien à rendement élevé, bonne banque (Crédit Mutuel, Caisse d'Épargne, Banque Populaire cités comme les plus souples). Délégation d'assurance : 0,08 à 0,22 % contre 0,34 à 0,55 % en contrat groupe.
4. **Le LMNP au réel domine fiscalement à crédit, même après la réforme 2025.** Sur un bien à 250 000 € financé à 100 % sur 20 ans, le LMNP réel produit 146 000 € de patrimoine net contre 99 000 € en nu réel et 74 000 € en SCI IS avec sortie du cash. Zéro impôt sur les loyers pendant 15 à 20 ans grâce aux amortissements, quel que soit le TMI. La SCI à l'IS n'a de sens qu'en capitalisation pure sans distribution. Le micro-foncier est à exclure dès qu'il y a du crédit.
5. **La courte durée est devenue une option sous conditions, pas une stratégie par défaut.** Loi Le Meur : enregistrement national obligatoire, 90 nuits en résidence principale dans les grandes villes, DPE E minimum (D en 2034), quotas communaux, interdiction votable en copropriété aux deux tiers. Paris, Lyon, Villeurbanne, Bordeaux, Marseille, Annecy, Saint-Malo, Biarritz sont de fait fermées à l'investisseur (compensation). Airbnb facture 15,5 % côté hôte depuis le 13 octobre 2026. Le micro-BIC des meublés non classés est tombé à 30 % avec un plafond de 15 000 €. Et le PLF 2027 propose de supprimer l'amortissement des meublés de tourisme achetés à partir de 2027. Toute opération courte durée doit avoir un repli crédible en longue durée.
6. **Les coûts réels sont supérieurs aux coûts affichés.** Conciergerie : 24 à 38 % du chiffre d'affaires tout compris (contre 15 à 25 % annoncés). Prélèvements sociaux sur les BIC meublés : 18,6 % depuis la LFSS 2026. Frais de notaire : 8 % dans 84 départements (DMTO à 5 % jusqu'en 2028). Taxe d'habitation sur résidence secondaire majorée de 60 % dans 1 666 communes, due sur un meublé de tourisme en plus de la CFE.

## 2. Ce que le module fait chaque semaine

1. **Collecte** : annonces de vente sur Bien'ici (JSON public, agences) et immobilier.notaires.fr (API publique, biens de succession) pour les 20 villes de `config/config.yaml`, plus un CSV manuel pour les biens off-market ou les alertes e-mail copiées. Trois circuits à prix décotés s'ajoutent : les ventes judiciaires de biens saisis (Licitor, pages d'audience des tribunaux des villes cibles, mise à prix et date d'audience), les ventes notariales interactives (API immo-interactif, première offre et date d'ouverture) et les cessions immobilières de l'État (portail des Domaines, toute la France, prix parfois non publié). Leboncoin et SeLoger sont inaccessibles depuis un serveur (DataDome, jurisprudence Jinka 2026) : les couvrir suppose un agrégateur sous licence (stream.estate ou Moteurimmo, 70 à 100 €/mois).
2. **Filtres** : prix, surface minimale (12 m²), exclusion viager, nue-propriété, résidences services, parkings et caves.
3. **Enrichissement marché** par commune ou arrondissement : loyer d'annonce au m² (Carte des loyers 2025, ministère du Logement, par typologie), médiane et quartiles du prix au m² sur les ventes réelles 2024 à 2026 (DVF géolocalisées), prix par nuit et occupation Airbnb (Inside Airbnb pour Paris, Lyon, Bordeaux, Pays basque ; hypothèses par catégorie de ville ailleurs), contraintes réglementaires (`config/reglementation.yaml`).
4. **Plan de financement** : prix négocié (marge par ville : Nantes 10 %, Lyon 3 %, défaut 5 %), notaire 8 %, travaux estimés d'après l'annonce (450, 1 200 ou 2 200 €/m²) et le DPE, ameublement 120 €/m², apport x % du coût total, garantie et frais de dossier financés, mensualité assurance comprise, intérêts de l'année 1.
5. **Quatre scénarios d'exploitation** : location nue, meublée (+12 % de loyer), colocation (+25 %, si ≥ 3 pièces et ≥ 60 m²), courte durée (ADR × 365 × occupation, moins plateforme 15,5 %, conciergerie 22 %, linge, énergie, assurance, copropriété entière, taxe foncière, taxe d'habitation secondaire, CFE, comptable, classement). Chaque scénario donne revenus, charges détaillées, rendement brut et net, DSCR, cash-flow avant impôt.
6. **Fiscalité comparée** pour chaque scénario : micro-foncier, réel foncier (déficit imputable 10 700 €), réel foncier avec amortissement Jeanbrun (si travaux ≥ 30 % du prix), micro-BIC (50 % ou 30 % selon classement), LMNP réel (amortissement par composants, règle de l'article 39 C, report illimité), SCI à l'IS (15 % puis 25 %, trésorerie bloquée). Le "meilleur régime" retenu est celui qui maximise le cash-flow après impôt parmi les régimes où le cash est disponible.
7. **Score 0 à 100** et **verdict**, red flags, points forts, checklist avant offre.
8. **Sorties** : onglets Google Sheets (Opportunités, Historique, Paramètres), tableau de bord HTML sur GitHub Pages, état inter-semaines (nouveautés, baisses de prix depuis la première vue).

## 2 bis. Les circuits à prix décotés et comment le modèle les traite

| Circuit | Source | Prix retenu dans l'analyse | Frais | Spécificités |
|---|---|---|---|---|
| Enchères judiciaires (biens saisis) | Licitor, tribunaux des villes cibles | Mise à prix × 1,6, plafonné à la valeur DVF moins 20 % ; bien occupé : moins 15 % | 12 % (droits de mutation, émoluments d'avocat, frais de poursuite) | Pas de condition suspensive de prêt, consignation 10 %, surenchère du dixième pendant 10 jours, visite unique, paiement sous 2 à 3 mois. Décote observée 10 à 40 %. |
| Ventes notariales interactives | immo-interactif (API publique) | Première offre × 1,15, plafonné à la valeur DVF moins 5 % | Notaire 8 % | Agrément préalable du notaire, le vendeur n'est pas tenu d'accepter, les enchères en ligne dépassent souvent le marché : fixer un plafond DVF. |
| Cessions de l'État (Domaines, DGFiP) | cessions.immobilier-etat.gouv.fr | Mise à prix publiée, sinon valeur DVF moins 15 % (hypothèse signalée) | Notaire 8 % | Appel d'offres, adjudication ou vente interactive ; anciens logements de fonction souvent à rénover ; cahier des charges et date limite sur la fiche. |

Le score ne pénalise pas ces modes de vente : la décote est déjà dans le prix attendu. Les contraintes (financement sans condition suspensive, occupation, date limite) sont remontées en alertes et dans la checklist.

## 3. Le score

| Composante | Poids | Ce qu'elle mesure |
|---|---|---|
| Autofinancement | 35 | Cash-flow mensuel après impôt du meilleur scénario longue durée, rapporté à la mensualité. 0 point à -25 %, plein à +20 %. |
| Rendement net | 15 | Rendement net de charges sur coût total. 0 point à 3 %, plein à 8 %. |
| Décote marché | 15 | Prix au m² de l'annonce contre la médiane DVF de la commune. 0 point à +10 %, plein à -25 %. |
| Robustesse du loyer | 10 | Nombre d'observations de la carte des loyers, taille de la commune, zone tendue, bien déjà loué. |
| Risque technique | 10 | DPE (G : -60 %, F : -40 %, E : -15 %), copropriété en procédure, charges > 45 €/m²/an, avant 1949, très petite surface. |
| Liquidité et signaux | 5 | Prix déjà baissé, prix sous le premier quartile DVF, typologie liquide (T2/T3 de 30 à 80 m²), mots-clés vendeur pressé (succession, urgent, travaux, loué, divisible). |
| Option courte durée | 10 | Cash-flow courte durée après impôt, pondéré par le risque réglementaire (libre 100 %, déclaration 85 %, autorisation ou quotas 50 %, compensation 0 %). |

Verdicts : ≥ 75 à visiter en priorité, 60 à 74 intéressant, 45 à 59 moyen (négociation nécessaire), < 45 à écarter. Le pré-filtre écarte les biens sous 5,5 % de rendement brut sauf score ≥ 70.

Pourquoi 35 points sur l'autofinancement alors que les outils du marché (Lybox, Horiz, Bevouac) pondèrent plutôt la décote et le rendement brut : l'objectif ici est explicitement un bien qui se finance seul à 100 % de crédit. La décote et le rendement sont des moyens, le cash-flow après impôt est le résultat.

## 4. La grille des meilleurs investisseurs (checklist avant offre)

1. **Marché** : tension locative (délai de relocation < 30 jours, LocService > 1,5), population > 20 000, bassin d'emploi ou université, 5 ventes DVF comparables dans la rue ou l'immeuble.
2. **Prix** : au moins 10 % sous la médiane DVF du quartier, durée en ligne > 100 jours, baisse de prix déjà passée, mention succession, divorce, urgent, travaux, loué ou occupé (décote 10 à 20 %).
3. **Copropriété** : 3 derniers PV d'AG, carnet d'entretien, fonds travaux, impayés < 25 %, pas d'administrateur provisoire, ratio charges / loyer HC < 25 %, règlement sans clause d'habitation bourgeoise si meublé de tourisme envisagé.
4. **Technique** : DPE recalculé avec le coefficient électricité 1,9 de 2026 (850 000 logements sortent du statut de passoire), électricité (5 000 à 12 000 € de mise aux normes sur un T3), plomb avant 1949, humidité, toiture, deux devis avant la fin des 10 jours de rétractation.
5. **Loyer** : validé par 2 agences locales et 3 annonces comparables, plafonné au loyer de référence majoré dans les 9 territoires d'encadrement (Paris, Lille, Lyon, Villeurbanne, Montpellier, Bordeaux, Grenoble, Plaine Commune, Est Ensemble, Pays basque), prolongé jusqu'au 31 juillet 2027.
6. **Financement** : simulation à 70 % des loyers, taux d'effort < 35 % après opération, condition suspensive de prêt 60 jours, condition suspensive d'autorisation de changement d'usage si courte durée.
7. **Fiscalité** : option au réel dès la première déclaration, frais d'acquisition en charges l'année 1 si bénéfice attendu rapidement, mise en location avant le 31 décembre, 5 ans pleins avant revente (forfait travaux 15 %), affiliation URSSAF dès 20 000 € de recettes courte durée.

## 5. Red flags qui tuent un deal

- DPE G (interdit à la location depuis 2025), F (2028), E (2034) sans budget de rénovation chiffré.
- Copropriété en procédure, taux d'impayés > 25 %, charges > 45 €/m²/an.
- Prix au m² > 15 % au-dessus de la médiane DVF.
- Commune < 20 000 habitants sans bassin d'emploi.
- Courte durée en ville à compensation, ou dans une copropriété qui l'interdit, ou avec DPE F/G.
- SCI à l'IR qui loue en meublé au-delà de 10 % des recettes (bascule automatique à l'IS).
- Dépassement du seuil de 15 000 € en meublé de tourisme non classé déclaré au micro-BIC 50 % (rapprochement DAC7 automatique).
- Engagements qui verrouillent la stratégie : déficit foncier 3 ans, Loc'Avantages 6 ans, Denormandie 6 à 12 ans, Jeanbrun 9 ans.

## 6. Limites connues du modèle

- Le loyer vient d'un indicateur d'annonce par commune, corrigé par la surface. Il ne voit pas la rue, l'étage ni l'état. À valider localement avant toute offre.
- La taxe foncière est estimée à un mois de loyer quand l'annonce ne la donne pas (proxy national).
- Les travaux sont estimés à partir des mots de l'annonce et du DPE, pas d'une visite.
- Les données Airbnb ne couvrent que quatre marchés. Ailleurs, occupation et prix par nuit sont des moyennes prudentes par catégorie de ville (les fournisseurs divergent de 20 points sur l'occupation).
- Le SCI IS est calculé au niveau de la société : la flat tax de 31,4 % à la sortie n'est pas déduite.
- La règle du 39 C et le report des amortissements sont modélisés en régime de croisière (année 1 pour les intérêts), pas en projection sur 20 ans.
- Les règlements municipaux de changement d'usage changent chaque semestre : `config/reglementation.yaml` doit être relu avant chaque offre.

## 7. Paramètres principaux et sources

| Paramètre | Valeur | Source |
|---|---|---|
| Taux 20 / 25 ans (surcote investisseur comprise) | 3,75 % / 3,90 % | Observatoire Crédit Logement septembre 2026, barèmes courtiers octobre 2026 |
| Assurance emprunteur (délégation) | 0,25 % du capital par an | Rapport 01 |
| Frais de notaire ancien | 8,0 % | DMTO 5 % dans 84 départements jusqu'au 31 mars 2028 |
| Travaux rafraîchissement / rénovation / lourde | 450 / 1 200 / 2 200 €/m² | Rapport 03, fait 92 |
| Vacance par catégorie de ville | 3 à 12 % | CLAMEUR, LocService (rapport 03) |
| Gestion locative / GLI / entretien | 7,5 % / 3 % / 5 % | Rapport 01 et 03 |
| Prime meublé / colocation | +12 % / +25 % | Rapport 03, fait 76 |
| Occupation courte durée par catégorie | 40 à 68 % | AirDNA, Airbtics, Welkeys 2025-2026 |
| Prix par nuit (T2) par catégorie | 70 à 160 € | Rapport 03, faits 32 à 35 |
| Commission plateforme / conciergerie | 15,5 % / 22 % | Airbnb EEE 13 octobre 2026, rapport 03 faits 44 et 45 |
| Prélèvements sociaux fonciers / BIC | 17,2 % / 18,6 % | LFSS 2026 art. 12 |
| Micro-BIC 2026 | 83 600 € à 50 %, 15 000 € à 30 % non classé | Rapport 02, faits 1 et 2 |
| Amortissement LMNP | 85 % du prix + notaire sur 30 ans, meubles 7 ans, travaux 12 ans | Rapport 02, fait 9 |
| Jeanbrun | 3 % ancien rénové, 3,5 % neuf, plafond 8 000 €/an | LF 2026 art. 47 |
| IS | 15 % jusqu'à 42 500 € puis 25 % | Rapport 02, fait 43 |
