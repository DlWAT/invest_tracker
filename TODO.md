# Roadmap — Philippine Airbnb Investment Scanner

Idées d'amélioration, classées par priorité. À cocher au fur et à mesure.

## 🔴 Priorité haute

### Sources de données
- [x] **Scraper filipinohomes.com** — 2e source déjà identifiée (particuliers + sous-types "beach-house/resort"). Même interface `BaseSource`, intégrer au runner + à l'app.
- [ ] **Lamudi** — 100 % derrière Akamai (401 partout, même `robots.txt`). Actors Apify dispo : `shahidirfan/lamudi-ph-property-scraper`, `memo23/lamudi-scraper`. À intégrer via token `APIFY_TOKEN`.
- [x] **Facebook Marketplace / groupes "rush sale"** — pas d'API officielle. Formulaire de saisie manuelle fait (`POST /api/listings` + modal « ＋ Ajouter » + géocodage auto).
- [ ] **Auto-remplissage du formulaire Facebook** : coller le texte brut d'une annonce → parser prix/localisation/chambres (regex).
- [ ] **Déduplication inter-sources** — un même bien listé sur DotProperty + filipinohomes. Fusion par titre/localisation/prix proche.

### Scoring Airbnb (le "process" qu'on a reporté)
- [ ] **Estimation revenus Airbnb** : ADR × occupation estimés par zone (à saisir ou via AirDNA/AirROI).
- [ ] **Calcul rendement net** : revenus − commissions − gestion − ménage − copro − taxes.
- [ ] **Score d'opportunité** (/100) par annonce, avec comparables du marché.
- [ ] **Détection "sous le marché"** : prix < valeur comparable (via prix/m² médian du quartier).
- [ ] **Alerte baisse de prix** — la donnée + l'affichage (badge ↓/↑, tri, filtre) sont faits ; il manque la notification proactive (email/Telegram).

### Collection automatisée
- [ ] **Planification** : exécution périodique (tâche planifiée Windows / cron) pour faire vivre l'historique des prix.
- [ ] **Reprise sur interruption** : mémoriser le dernier (province, type, page) traité pour reprendre sans tout refaire.
- [ ] **Retry + backoff** sur erreurs réseau (429/5xx), avec journalisation.

### Enrichissement
- [ ] **GPS exact des annonces** : activer/utiliser `--enrich` (coordonnées réelles de la page détail, pas le centre-ville du géocodage).
- [ ] **Re-géocodage auto** des nouvelles annonces après chaque collecte (chaîner `geocode.py`).

## 🟡 Priorité moyenne

### Interface
- [ ] **Fiche détail d'une annonce** (modal) : toutes les photos, description complète, carte, historique des prix.
- [ ] **Mini-graphique d'évolution** du prix (sparkline) sur chaque carte.
- [ ] **Favoris / sauvegardés** (table dédiée + bouton ⭐).
- [ ] **Export CSV/JSON** des résultats filtrés.
- [ ] **Sauvegarde des filtres dans l'URL** (partageable) ou "recherches enregistrées".
- [ ] **Comparaison de 2-3 annonces** côte à côte.

### Qualité des données
- [ ] **Validation / filtrage des valeurs aberrantes** (prix/m² absurdes, surfaces énormes).
- [ ] **Normalisation des équipements** (pool, AC, wifi…) en booléens pour filtrer.
- [ ] **Distinction surface sol vs plancher** (le prix/m² peut être trompeur sur les maisons).

### Robustesse
- [ ] **Tests** (pytest) sur le parsing, le scoring, l'API.
- [ ] **Logging** (fichier + niveau réglable) au lieu de `print`.
- [ ] **Config externe** (YAML/JSON) pour zones, budget, réglages — éviter les constantes en dur.

## 🟢 Priorité basse

- [ ] **Docker** (conteneur pour le serveur + le collector).
- [ ] **Auth simple** pour exposer l'app (si accès hors machine locale).
- [ ] **Responsive mobile** (l'app est pensée desktop).
- [ ] **Comparaison multi-marchés** (benchmark Boracay vs El Nido vs Batangas sur rendement).
- [ ] **Notifications** (email/Telegram) sur baisse de prix ou nouvelle opportunité ≥ seuil.
- [ ] **Résumés CSV périodiques** (top opportunités du jour).

---

### Ordre suggéré
1. ~~Scraper filipinohomes~~ ✅
2. ~~Formulaire saisie manuelle (Facebook)~~ ✅
3. Planification de collecte → faire vivre l'historique des prix.
4. Couche scoring/rendement → transformer les données en décisions.
5. Déduplication inter-sources.
6. Fiche détail + sparkline → exploiter les données déjà présentes.
