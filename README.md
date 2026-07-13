# Pâtissons API — Bloc 2 (RNCP37273)

API REST développée avec Flask et MySQL, dans le cadre du Bloc 2 de la
certification RNCP Développeur Web Full Stack.

## Architecture

- **Base de données** : MySQL 8.0, conteneurisé avec Docker (port 3307)
- **API** : Flask, exécuté en local (port 5000)
- **ORM** : aucun — requêtes SQL paramétrées via `flask-mysqldb`, pour une
  maîtrise complète des requêtes et des jointures

Ce choix d'architecture (base conteneurisée, API en local) privilégie la
reproductibilité de la base de données tout en gardant un cycle de
développement rapide (rechargement à chaud, débogage simplifié).

## Installation

### 1. Cloner le dépôt

```bash
git clone <url-du-repo>
cd bloc2-rncp
```

### 2. Lancer la base de données

```bash
docker-compose up -d
```

Cette commande télécharge l'image MySQL 8.0, crée le conteneur, et exécute
automatiquement `init.sql` pour créer toutes les tables (au tout premier
démarrage uniquement).

Vérifier que le conteneur tourne :
```bash
docker ps
```

### 3. Créer l'environnement virtuel Python

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows (Git Bash)
# ou : source .venv/bin/activate   # Mac / Linux
```

### 4. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 5. Configurer les variables d'environnement

Copier le fichier d'exemple et compléter les valeurs manquantes
(mot de passe MySQL défini dans `docker-compose.yml`, et une clé secrète
de ton choix) :

```bash
cp .env.example .env
```

### 6. Lancer l'API

```bash
python app.py
```

L'API est accessible sur `http://127.0.0.1:5000`.

### 7. (Optionnel) Peupler la base avec des recettes de test

```bash
python importer_recettes.py
```

Nécessite un fichier `data/recettes.json` (non fourni dans ce dépôt, voir
avec l'auteure du projet).

## Routes disponibles

| Méthode | Route | Description |
|---|---|---|
| GET | `/recettes` | Liste toutes les recettes |
| GET | `/recettes/<id>` | Détail d'une recette (ingrédients + étapes) |
| POST | `/recettes` | Crée une recette (ingrédients/étapes optionnels) |
| PUT | `/recettes/<id>` | Modifie une recette |
| DELETE | `/recettes/<id>` | Supprime une recette |
| GET | `/categories` | Liste les catégories |
| POST | `/categories` | Crée une catégorie |
| POST | `/inscription` | Crée un compte utilisateur |
| POST | `/connexion` | Connexion (vérification du mot de passe hashé) |

## Sécurité

- Mots de passe hashés avec `werkzeug.security` (algorithme scrypt), jamais
  stockés en clair
- Requêtes SQL systématiquement paramétrées (`%s`), pour éviter toute
  injection SQL
- Configuration sensible (identifiants MySQL, clé secrète) externalisée dans
  `.env`, exclu du dépôt Git via `.gitignore`
