# Invest Tracker — app Android (lecteur hors-ligne)

Lecteur Android de la base `listings.db`, embarquée dans l'APK.
**Aucune collecte** : l'app lit la base telle quelle (annonces, favoris,
historique des prix). La collecte reste sur le PC / serveur.

## Prérequis

- [Flutter SDK](https://docs.flutter.dev/get-started/install/windows) (stable)
- Android Studio (SDK Android) pour compiler / tester

## Générer la base embarquée

Depuis la racine du repo, la base doit exister (`data/listings.db`, générée par
`python main.py`). Copiez-la dans les assets de l'app :

```powershell
.\android_app\scripts\prepare_db.ps1
```

Cela copie `data/listings.db` → `android_app/assets/listings.db`.

## Construire / lancer

```powershell
cd android_app
flutter create --platforms android --org com.investtracker --project-name invest_tracker .   # 1ere fois uniquement
flutter pub get
flutter run                # sur un émulateur / téléphone branché
flutter build apk --release
```

L'APK de release sort dans :
`android_app/build/app/outputs/flutter-apk/app-release.apk`.

## Build automatique (GitHub Actions)

Le workflow `.github/workflows/build_android.yml` construit l'APK sur un runner
Ubuntu. Comme la base est gitignorée (`*.db`), il faut la rendre disponible :

- soit committer `android_app/assets/listings.db` avec `git add -f`,
- soit pousser `data/listings.db` dans le repo.

Puis : **Actions → Build Android APK → Run workflow**, et télécharger
l'artefact `invest-tracker-apk`.

## Fonctionnalités

- Onglets **Accueil / Recherches / Favoris**
- Recherche + tri + filtres (type, zone cible)
- Favoris (étoile) persistés dans la base locale
- Fiche détail avec **graphique d'évolution du prix**
- Bilingue **FR / EN** (bouton en haut à droite)

## Note

La base est chargée en mémoire puis copiée vers le stockage de l'app au premier
lancement (~118 Mo). Pour la mettre à jour, régénérez la base (collecte) puis
reconstruisez l'APK.
