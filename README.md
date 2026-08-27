# Philippine Airbnb Investment Scanner

Agrégateur d'annonces immobilières destiné à identifier des opportunités
d'investissement Airbnb aux Philippines (Boracay, El Nido/Palawan, Batangas),
dans un budget d'environ 100 k€ (~ 6 M PHP).

Ce dépôt contient **la couche de collecte** : récupération automatisée des
annonces depuis DotProperty, normalisation et stockage dans une base SQLite.

---

## Sommaire

1. [Objectif](#objectif)
2. [Architecture du projet](#architecture-du-projet)
3. [Détail de chaque fichier](#détail-de-chaque-fichier)
4. [Modèle de données](#modèle-de-données)
5. [Fonctionnement détaillé](#fonctionnement-détaillé)
6. [Installation](#installation)
7. [Utilisation](#utilisation)
8. [Résultats attendus](#résultats-attendus)
9. [Limites connues](#limites-connues)
10. [Prochaines étapes](#prochaines-étapes)

---

## Objectif

Le projet vise à ne plus consulter manuellement des centaines d'annonces.
Il collecte automatiquement les biens à vendre dans trois zones cibles,
les filtre par budget (≤ 6 M PHP), et les stocke de façon structurée pour
permettre ensuite une couche d'analyse (scoring Airbnb, détection de
bonnes affaires, alertes de baisse de prix).

**Périmètre actuel :** uniquement la collecte (`on verra les process après`).

---

## Architecture du projet

```
invest_tracker/
├── main.py                      # Point d'entrée CLI
├── requirements.txt             # Dépendances Python
├── .gitignore                   # Fichiers ignorés (dont data/)
├── .venv/                       # Environnement virtuel (non versionné)
├── data/
│   └── listings.db              # Base SQLite générée (non versionnée)
└── ph_scanner/
    ├── __init__.py
    ├── config.py                # Zones, types, budget, constantes
    ├── models.py                # Modèle Listing + parseurs
    ├── storage.py               # Stockage SQLite + dédup + historique
    ├── runner.py                # Orchestration CLI
    └── sources/
        ├── __init__.py
        ├── base.py              # Interface abstraite d'une source
        └── dotproperty.py       # Scraper DotProperty
```

---

## Détail de chaque fichier

### `ph_scanner/config.py`

Configuration centrale. Contient :

- **`MAX_PRICE_PHP = 6_000_000`** — budget maximum (100 k€ ≈ 6 M PHP).
- **`PROPERTY_TYPES`** — les 5 types de biens recherchés :
  `condos`, `houses`, `villas`, `hotels`, `land`.
- **`ZONES`** — la liste des zones cibles. Chaque zone associe :
  - `id` : identifiant interne (`boracay`, `el_nido`, `batangas`) ;
  - `province_slug` : le slug de province utilisé dans l'URL DotProperty
    (`aklan` pour Boracay, `palawan` pour El Nido, `batangas`) ;
  - `keywords` : mots-clés qui permettent de rattacher une annonce à la
    micro-localisation précise (ex. `nasugbu`, `calatagan`, `laiya`).
- **`DEFAULT_USER_AGENT`**, **`BASE_URL`**, **`REQUEST_TIMEOUT`**,
  **`DELAY_BETWEEN_REQUESTS`**, **`MAX_PAGES_PER_SEARCH`** : constantes de
  comportement réseau (politesse de scraping).

> **Pourquoi une province ET des mots-clés ?**
> DotProperty ne filtre que par province, pas par ville/quartier.
> « Boracay » n'existe pas comme slug → on récupère la province `aklan`
> puis on détecte Boracay via les mots-clés (`malay`, `yapak`, `balabag`…).

### `ph_scanner/models.py`

Définit le **modèle de données normalisé** et les fonctions de parsing.

- **`Listing`** (dataclass) : une annonce, indépendante de la source.
  Champs principaux : `price_php`, `price_per_sqm`, `beds`, `baths`,
  `area_sqm`, `property_type`, `location_text`, `province`, `zone_id`,
  `amenities`, `images`, `agent`, `latitude`, `longitude`, `description`…
- **`parse_price(value)`** — convertit `"₱ 4,286,528"` → `4286528` (int).
  Supprime tous les caractères non numériques.
- **`parse_area(value)`** — convertit `"179.25 m2"` → `179.25` (float).
- **`parse_int(value)`** — extrait le premier entier d'une chaîne.
- **`normalize_type(value)`** — normalise le type libre (`"Hotel / Resort"`,
  `"Condo"`, `"House and Lot"`…) vers un slug canonique (`hotel`, `condo`,
  `house`, `land`…) grâce à la table `_TYPE_ALIASES`.

### `ph_scanner/sources/base.py`

Interface abstraite `BaseSource`. Toute nouvelle source (Lamudi, Carousell,
Facebook…) devra implémenter :

- **`search(zone, property_type)`** — renvoie la liste des `Listing`.
- **`enrich(listing)`** — complète une annonce avec les données de sa page
  de détail (GPS, description).

### `ph_scanner/sources/dotproperty.py`

Le scraper concret pour DotProperty. Fonctionne sans JavaScript : les pages
de résultats sont rendues côté serveur, on les parse donc directement.

Points clés :

- **`_search_url(type, province, page)`** — construit l'URL de recherche :
  `https://www.dotproperty.com.ph/{type}-for-sale/{province}?page={n}&max_price=6000000`.
- **`search(zone, type)`** — boucle sur les pages (25 annonces/page),
  s'arrête dès qu'une page revient moins de 25 cartes, attend `delay`
  secondes entre chaque requête.
- **`_parse_card(card, zone, type)`** — parse une carte HTML :
  - le **lien** (`_find_listing_link`) gère deux formats d'URL :
    `/ads/{slug}_{hash}` et `/{slug}_{id-numérique}` ;
  - le **titre** (`div.text-2xl`) ;
  - l'**id externe** (`data-uuid`) ;
  - le **prix** et le **prix au m²** ;
  - les **chambres / salles de bain / surface / type** : repérés via
    l'icône SVG associée (`bed`, `bathtub`, `resize`, `home`) ;
  - la **localisation** (via l'icône `location`) ;
  - les **équipements** (`ul.facilities li`, en excluant `+9`…) ;
  - les **images**, l'**agent**, et les badges `Featured` / `Virtual tour`.
- **`enrich(listing)`** — récupère la page de détail et extrait les
  coordonnées GPS (micro-données schema.org `latitude`/`longitude`) et la
  description complète.

### `ph_scanner/storage.py`

Stockage SQLite avec dédoublonnage et suivi des prix.

Deux tables :

- **`listings`** — une ligne par annonce, clé primaire `(source, external_id)`.
  Champs `first_seen` / `last_seen` pour savoir quand une annonce est
  apparue puis revue.
- **`price_history`** — historique des prix observés (permet de détecter
  une baisse de prix).

La méthode **`upsert(listing)`** renvoie un statut :

| Statut         | Signification                                            |
|----------------|----------------------------------------------------------|
| `new`          | annonce jamais vue → insérée                             |
| `price_change` | le prix a changé → mise à jour + entrée dans l'historique|
| `unchanged`    | déjà vue, rien à changer → seul `last_seen` est rafraîchi|

Le module active `PRAGMA journal_mode=WAL` pour de meilleures performances,
et crée des index sur `zone_id` et `price_php`.

### `ph_scanner/runner.py`

Orchestration en ligne de commande. Parse les arguments, instancie le
scraper et le stockage, puis itère sur **zones × types** :

```
for zone in zones:
    for type in types:
        listings = source.search(zone, type)   # récupérer
        for l in listings:
            if enrich: l = source.enrich(l)    # (optionnel) GPS
            status = storage.upsert(l)         # insérer/mettre à jour
```

Affiche un résumé final (nombre de nouvelles annonces, changements de prix,
total en base).

### `main.py`

Simple point d'entrée : `from ph_scanner.runner import main` puis lance
`main()`. Sépare l'exécution du module de son packaging.

---

## Modèle de données

Table `listings` :

| Colonne          | Type    | Description                                    |
|------------------|---------|------------------------------------------------|
| `source`         | TEXT    | nom de la source (`dotproperty`)               |
| `external_id`    | TEXT    | id unique côté source (clé primaire composite) |
| `url`            | TEXT    | URL de l'annonce                               |
| `title`          | TEXT    | titre                                          |
| `price_php`      | INTEGER | prix en pesos                                  |
| `price_per_sqm`  | REAL    | prix au m² en pesos                            |
| `beds`           | INTEGER | nombre de chambres                             |
| `baths`          | INTEGER | nombre de salles de bain                       |
| `area_sqm`       | REAL    | surface en m²                                  |
| `property_type`  | TEXT    | type normalisé (`condo`, `house`, `land`…)     |
| `location_text`  | TEXT    | ville/municipalité (ex. « Malay, Aklan »)      |
| `province`       | TEXT    | province (`aklan`, `palawan`, `batangas`)      |
| `zone_id`        | TEXT    | zone cible si mots-clés trouvés, sinon `NULL`  |
| `amenities`      | TEXT    | équipements (JSON)                             |
| `images`         | TEXT    | URLs des photos (JSON)                         |
| `agent`          | TEXT    | nom de l'agent / agence                        |
| `is_featured`    | INTEGER | badge « Featured »                             |
| `has_virtual_tour`| INTEGER| dispose d'une visite virtuelle                 |
| `latitude`       | REAL    | GPS (uniquement si `--enrich`)                 |
| `longitude`      | REAL    | GPS (uniquement si `--enrich`)                 |
| `description`    | TEXT    | description complète (uniquement si `--enrich`)|
| `first_seen`     | TEXT    | date de première apparition                    |
| `last_seen`      | TEXT    | date de dernière observation                   |

---

## Fonctionnement détaillé

1. **Construction des URLs** : pour chaque zone et chaque type, on construit
   l'URL `/{type}-for-sale/{province}?page=1&max_price=6000000`.

2. **Pagination** : on avance page par page (`?page=2`, `?page=3`…) tant que
   la page contient 25 annonces (page pleine). Une page incomplète signale
   la dernière page.

3. **Parsing** : chaque carte `article.listing-snippet` est transformée en
   objet `Listing`. Les champs numériques (prix, surface…) passent par les
   parseurs de `models.py`.

4. **Zonage** : `province` est toujours renseigné. `zone_id` n'est renseigné
   que si le titre ou la localisation contient un des mots-clés de la zone
   (sinon `NULL`, signalant un bien « même province, mais hors zone cible »).

5. **Stockage** : `upsert` insère les nouveautés, détecte les changements de
   prix (avec historique) et rafraîchit `last_seen` pour les autres.

6. **Résumé** : la commande affiche le décompte par zone/type puis un
   résumé global.

---

## Installation

Prérequis : **Python 3.11+**.

```powershell
# 1. Créer et activer l'environnement virtuel
python -m venv .venv
.\.venv\Scripts\activate

# 2. Installer les dépendances
pip install -r requirements.txt
```

Dépendances : `requests` (HTTP), `beautifulsoup4` + `lxml` (parsing HTML).

---

## Utilisation

Depuis la racine du projet, avec le venv activé :

```powershell
# Collecte complète (toutes zones, tous types)
python main.py

# Uniquement certaines zones
python main.py --zones el_nido batangas

# Uniquement certains types
python main.py --types houses condos

# Avec enrichissement des pages de détail (GPS + description, plus lent)
python main.py --enrich

# Réglages fins
python main.py --delay 2 --max-pages 10 --db data/listings.db
```

| Option        | Défaut            | Rôle                                   |
|---------------|-------------------|----------------------------------------|
| `--zones`     | toutes            | zone(s) à collecter                    |
| `--types`     | tous              | type(s) à collecter                    |
| `--enrich`    | désactivé         | récupérer GPS + description            |
| `--delay`     | `1.0`             | pause entre requêtes (secondes)        |
| `--max-pages` | `40`              | pages max par recherche                |
| `--db`        | `data/listings.db`| chemin de la base SQLite               |

> Les relances sont **idempotentes** : relancer la commande ne duplique rien
> (dédup par `(source, external_id)`), mais met à jour `last_seen` et
> détecte les changements de prix.

---

## Résultats attendus

Exemple de sortie réelle :

```
[ok] boracay    condos   ->   22 listings (22 total in db)
[ok] boracay    houses   ->    9 listings (31 total in db)
...
=== Summary ===
  new:          1406
  price_change: 0
  total in db:  1406
```

Répartition typique :

| Province | Annonces | Zone cible rattachée  |
|----------|---------:|-----------------------|
| `aklan`  |       39 | Boracay (29)          |
| `palawan`|      226 | El Nido (8)           |
| `batangas`|    1141 | Batangas cible (263)  |

> ⚠️ Note métier : sur DotProperty il y a **très peu de biens réellement à
> El Nido** (la majorité des annonces Palawan sont à Puerto Princesa). Les
> biens « rush sale » de Boracay/El Nido circulent surtout sur Facebook et
> via des agents locaux, sources non couvertes par ce scraper.

---

## Limites connues

- **Lamudi** renvoie `401 Access Denied` (protection anti-bot) ; **Carousell**
  renvoie `403` (Cloudflare). Non couverts pour l'instant.
- Le filtre `location` de DotProperty est **au niveau province uniquement** ;
  la granularité ville est obtenue par mots-clés (`zone_id`).
- Les données GPS nécessitent `--enrich` (une requête supplémentaire par
  annonce).
- Pas de données de revenus Airbnb (ADR / occupation) dans cette couche :
  elles arriveront dans la couche d'analyse/scoring.

---

## Prochaines étapes

1. **Export** CSV/JSON pour consulter les annonces collectées.
2. **Couche d'analyse** : calcul du rendement net estimé (ADR × occupation
   − charges) et score d'opportunité par annonce.
3. **Détection de bonnes affaires** : prix sous le marché, baisses de prix
   (via `price_history`), nouvelles annonces.
4. **Nouvelles sources** : implémenter `BaseSource` pour Lamudi (via API
   tierce type Apify) et les annonces Facebook.
5. **Planification** : exécution périodique pour suivre le marché.
