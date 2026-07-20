"""
importer_recettes.py
Script d'import de recettes.json vers la base MySQL de Pâtissons.
Placer ce fichier à la racine du projet (même dossier que app.py).
Lancer avec : python importer_recettes.py
"""

import json
import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

# --- Connexion ---
conn = mysql.connector.connect(
    host=os.getenv("MYSQL_HOST"),
    port=int(os.getenv("MYSQL_PORT")),
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    database=os.getenv("MYSQL_DB"),
)
print("Connecté sur :", os.getenv("MYSQL_HOST"), os.getenv("MYSQL_PORT"))
cur = conn.cursor()

# --- Chargement du JSON ---
with open("data/recettes.json", encoding="utf-8") as f:
    data = json.load(f)

recettes = data["recettes"]

for r in recettes:

    # 1. Catégorie — insert si elle n'existe pas encore
    cur.execute(
        "INSERT IGNORE INTO Categorie (slug, label) VALUES (%s, %s)",
        (r["categorie"], r["categorie_label"]),
    )
    conn.commit()

    cur.execute("SELECT id_categorie FROM Categorie WHERE slug = %s", (r["categorie"],))
    id_categorie = cur.fetchone()[0]

    # 2. Utilisateur par défaut — créé une seule fois si la table est vide
    cur.execute(
        "INSERT IGNORE INTO Utilisateur (nom, email, mot_passe, role) VALUES (%s, %s, %s, %s)",
        ("Ludivine", "ludivine@patissons.fr", "motdepasse_temporaire", "admin"),
    )
    conn.commit()
    cur.execute("SELECT id_utilisateur FROM Utilisateur LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("❌ Aucun utilisateur en base.")
        break
    id_utilisateur = row[0]

    # 3. Recette principale
    temps = r.get("temps", {})
    image = r.get("images", [None])[0]
    conseils_texte = json.dumps(r.get("conseils", []), ensure_ascii=False)

    cur.execute(
        """
        INSERT IGNORE INTO Recette
            (slug, titre, description, temps_preparation, temps_cuisson,
             temps_repos, portions, difficulte, image, conseils, statut,
             id_utilisateur, id_categorie)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """,
        (
            r["slug"],
            r["titre"],
            r.get("description"),
            temps.get("preparation_min", 0),
            temps.get("cuisson_min"),
            temps.get("repos_min"),
            r.get("portions", 1),
            r.get("difficulte", "Facile"),
            image,
            conseils_texte,
            "publiee",
            id_utilisateur,
            id_categorie,
        ),
    )
    conn.commit()

    cur.execute("SELECT id_recette FROM Recette WHERE slug = %s", (r["slug"],))
    id_recette = cur.fetchone()[0]

    # 4. Groupes d'ingrédients + ingrédients
    for ordre_groupe, groupe in enumerate(r.get("ingredients", []), start=1):
        cur.execute(
            """
            INSERT INTO IngredientGroupe (nom_groupe, ordre, id_recette)
            VALUES (%s, %s, %s)
        """,
            (groupe["groupe"], ordre_groupe, id_recette),
        )
        conn.commit()
        id_groupe = cur.lastrowid

        for ordre_item, item in enumerate(groupe.get("items", []), start=1):
            quantite = item.get("quantite") or 0
            cur.execute(
                """
                INSERT INTO Ingredient (nom, quantite, unite, ordre, id_ingredient_groupe)
                VALUES (%s, %s, %s, %s, %s)
            """,
                (item["nom"], quantite, item.get("unite"), ordre_item, id_groupe),
            )
        conn.commit()

    # 5. Étapes
    for etape in r.get("etapes", []):
        cur.execute(
            """
            INSERT INTO Etape (ordre, titre, description, id_recette)
            VALUES (%s, %s, %s, %s)
        """,
            (etape["numero"], etape["titre"], etape["description"], id_recette),
        )
    conn.commit()

    print(f"✅ Importé : {r['titre']}")

cur.close()
conn.close()
print("\n🎉 Import terminé !")
