# TorqScan Dz

Application de diagnostic automobile OBD2. Le dépôt conserve les archives de sources Flutter restaurées ; le code applicatif est extrait par le workflow Android avant compilation.

## Sources conservées

- `DzTorqscan_v1.4.0_complete.zip` : archive source principale utilisée en priorité par le workflow.
- `DzTorqscan_source_recovery_v1.3.10.zip` : archive de récupération de secours.

Ne remplacez pas ces archives par un nouveau projet : elles constituent les sources versionnées du projet existant.

## Construire et récupérer l'APK

Le workflow GitHub Actions **Android APK Build** utilise Java 17 et Flutter 3.35.7. Il extrait l'archive, applique les réparations automatisées contrôlées, installe les dépendances Flutter, exécute l'analyse Dart et les tests, construit `app-release.apk`, vérifie l'APK et publie l'artefact :

1. Ouvrir l'onglet **Actions** du dépôt.
2. Sélectionner **Android APK Build** et ouvrir une exécution terminée avec succès.
3. Télécharger l'artefact **torqscan-dz-android-apk**.
4. Extraire le ZIP de l'artefact pour récupérer `app-release.apk`, puis transférer l'APK sur le téléphone Android.

Les artefacts du workflow sont conservés pendant 14 jours. Une exécution ancienne peut donc ne plus proposer son téléchargement.

## Important — signature de test

Le workflow crée une clé de signature temporaire sur son runner pour chaque exécution. L'APK est ainsi signé et vérifié pour les essais directs, mais cette clé n'est pas une clé de publication durable. Deux APK provenant de deux exécutions différentes peuvent avoir des signatures différentes : Android peut alors refuser la mise à jour par-dessus l'installation précédente. Sauvegardez les données utiles avant de désinstaller l'ancienne version puis d'installer un APK signé par une autre exécution.

Cette APK de test n'est pas une livraison Google Play et ne remplace pas une signature de publication conservée de façon sécurisée.

## Limites de validation

La CI vérifie les sources extraites, l'analyse et les tests automatisés, la compilation, la signature et l'intégrité de l'APK. Elle ne peut pas prouver la connexion à un adaptateur OBD2 physique, la compatibilité de chaque véhicule, ni la lecture réelle des calculateurs. Ces vérifications nécessitent un téléphone Android et un adaptateur compatible connectés à un véhicule.

Aucun service API payant n'est nécessaire pour compiler le projet. Les fonctionnalités qui dépendraient d'un service externe doivent être vérifiées séparément avant toute mise en production.
