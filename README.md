# Pâtissons API

API REST Flask + MySQL pour gérer des recettes.

## Prérequis
- Python 3.10+
- MySQL local (port 3306)

## Installation
1. Créer l'environnement virtuel :
   ```bash
   python -m venv .venv
   source .venv/Scripts/activate  # Windows
   pip install -r requirements.txt
   ```

2. Configurer la base :
   ```bash
   mysql -u root -p patissons < init.sql
   ```

3. Copier et compléter `.env` :
   ```bash
   cp .env.example .env
   ```

## Lancement
```bash
python app.py
```
→ API accessible sur `http://127.0.0.1:5000`