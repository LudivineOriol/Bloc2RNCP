from flask import Flask, jsonify, request
from flask_mysqldb import MySQL
import MySQLdb.cursors
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
import os

load_dotenv()

app = Flask(__name__)

# --- Configuration MySQL ---
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_PORT'] = int(os.getenv('MYSQL_PORT'))
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

mysql = MySQL(app)


# =========================================================
# ROUTE DE TEST
# =========================================================

@app.route('/')
def index():
    return jsonify({"message": "API Pâtissons opérationnelle"})


# =========================================================
# RECETTES
# =========================================================

@app.route('/recettes', methods=['GET'])
def liste_recettes():
    """Renvoie la liste de toutes les recettes (vue simplifiée, sans le détail
    des ingrédients/étapes, pour rester léger)."""
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT r.id_recette, r.slug, r.titre, r.description, r.temps_preparation,
               r.temps_cuisson, r.temps_repos, r.portions, r.difficulte,
               r.image, r.statut, c.label AS categorie
        FROM Recette r
        JOIN Categorie c ON r.id_categorie = c.id_categorie
    """)
    recettes = cur.fetchall()
    cur.close()
    return jsonify(recettes), 200


@app.route('/recettes/<int:id_recette>', methods=['GET'])
def detail_recette(id_recette):
    """Renvoie une recette complète : infos principales + ingrédients (groupés) + étapes."""
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    cur.execute("""
        SELECT r.*, c.label AS categorie
        FROM Recette r
        JOIN Categorie c ON r.id_categorie = c.id_categorie
        WHERE r.id_recette = %s
    """, (id_recette,))
    recette = cur.fetchone()

    if not recette:
        cur.close()
        return jsonify({"erreur": "Recette introuvable"}), 404

    # Groupes d'ingrédients + leurs ingrédients
    cur.execute("""
        SELECT id_ingredient_groupe, nom_groupe, ordre
        FROM IngredientGroupe
        WHERE id_recette = %s
        ORDER BY ordre
    """, (id_recette,))
    groupes = cur.fetchall()

    for groupe in groupes:
        cur.execute("""
            SELECT nom, quantite, unite, ordre
            FROM Ingredient
            WHERE id_ingredient_groupe = %s
            ORDER BY ordre
        """, (groupe['id_ingredient_groupe'],))
        groupe['ingredients'] = cur.fetchall()

    recette['ingredients'] = groupes

    # Étapes
    cur.execute("""
        SELECT ordre, titre, description
        FROM Etape
        WHERE id_recette = %s
        ORDER BY ordre
    """, (id_recette,))
    recette['etapes'] = cur.fetchall()

    cur.close()
    return jsonify(recette), 200


@app.route('/recettes', methods=['POST'])
def creer_recette():
    """Crée une recette complète en une seule requête : infos principales,
    et éventuellement ses groupes d'ingrédients + ingrédients, et ses étapes.

    Format JSON attendu (les clés "ingredients" et "etapes" sont optionnelles) :
    {
        "slug": "...", "titre": "...", "temps_preparation": 30, "portions": 6,
        "difficulte": "Facile", "id_utilisateur": 1, "id_categorie": 1,
        "ingredients": [
            {"groupe": "Pâte", "items": [
                {"nom": "farine", "quantite": 250, "unite": "g"},
                {"nom": "beurre", "quantite": 125, "unite": "g"}
            ]}
        ],
        "etapes": [
            {"numero": 1, "titre": "Mélanger", "description": "..."}
        ]
    }
    """
    data = request.get_json()

    champs_requis = ['slug', 'titre', 'temps_preparation', 'portions',
                      'difficulte', 'id_utilisateur', 'id_categorie']
    for champ in champs_requis:
        if champ not in data:
            return jsonify({"erreur": f"Le champ '{champ}' est obligatoire"}), 400

    cur = mysql.connection.cursor()

    # 1. La recette principale
    cur.execute("""
        INSERT INTO Recette
            (slug, titre, description, temps_preparation, temps_cuisson,
             temps_repos, portions, difficulte, image, conseils, statut,
             id_utilisateur, id_categorie)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        data['slug'],
        data['titre'],
        data.get('description'),
        data['temps_preparation'],
        data.get('temps_cuisson'),
        data.get('temps_repos'),
        data['portions'],
        data['difficulte'],
        data.get('image'),
        data.get('conseils'),
        data.get('statut', 'brouillon'),
        data['id_utilisateur'],
        data['id_categorie']
    ))
    id_recette = cur.lastrowid

    # 2. Groupes d'ingrédients + ingrédients (optionnel)
    for ordre_groupe, groupe in enumerate(data.get('ingredients', []), start=1):
        cur.execute("""
            INSERT INTO IngredientGroupe (nom_groupe, ordre, id_recette)
            VALUES (%s, %s, %s)
        """, (groupe['groupe'], ordre_groupe, id_recette))
        id_groupe = cur.lastrowid

        for ordre_item, item in enumerate(groupe.get('items', []), start=1):
            cur.execute("""
                INSERT INTO Ingredient (nom, quantite, unite, ordre, id_ingredient_groupe)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                item['nom'],
                item.get('quantite') or 0,
                item.get('unite'),
                ordre_item,
                id_groupe
            ))

    # 3. Étapes (optionnel)
    for etape in data.get('etapes', []):
        cur.execute("""
            INSERT INTO Etape (ordre, titre, description, id_recette)
            VALUES (%s, %s, %s, %s)
        """, (
            etape['numero'],
            etape['titre'],
            etape['description'],
            id_recette
        ))

    mysql.connection.commit()
    cur.close()

    return jsonify({"message": "Recette créée", "id_recette": id_recette}), 201


@app.route('/recettes/<int:id_recette>', methods=['PUT'])
def modifier_recette(id_recette):
    data = request.get_json()

    cur = mysql.connection.cursor()

    # On vérifie d'abord que la recette existe
    cur.execute("SELECT id_recette FROM Recette WHERE id_recette = %s", (id_recette,))
    if not cur.fetchone():
        cur.close()
        return jsonify({"erreur": "Recette introuvable"}), 404

    champs_requis = ['slug', 'titre', 'temps_preparation', 'portions',
                      'difficulte', 'id_utilisateur', 'id_categorie']
    for champ in champs_requis:
        if champ not in data:
            cur.close()
            return jsonify({"erreur": f"Le champ '{champ}' est obligatoire"}), 400

    cur.execute("""
        UPDATE Recette
        SET slug = %s, titre = %s, description = %s, temps_preparation = %s,
            temps_cuisson = %s, temps_repos = %s, portions = %s, difficulte = %s,
            image = %s, conseils = %s, statut = %s, id_utilisateur = %s,
            id_categorie = %s
        WHERE id_recette = %s
    """, (
        data['slug'],
        data['titre'],
        data.get('description'),
        data['temps_preparation'],
        data.get('temps_cuisson'),
        data.get('temps_repos'),
        data['portions'],
        data['difficulte'],
        data.get('image'),
        data.get('conseils'),
        data.get('statut', 'brouillon'),
        data['id_utilisateur'],
        data['id_categorie'],
        id_recette
    ))
    mysql.connection.commit()
    cur.close()

    return jsonify({"message": "Recette mise à jour"}), 200


@app.route('/recettes/<int:id_recette>', methods=['DELETE'])
def supprimer_recette(id_recette):
    cur = mysql.connection.cursor()

    cur.execute("SELECT id_recette FROM Recette WHERE id_recette = %s", (id_recette,))
    if not cur.fetchone():
        cur.close()
        return jsonify({"erreur": "Recette introuvable"}), 404

    # Il n'y a pas de suppression en cascade automatique en base,
    # donc on supprime nous-mêmes les données liées, dans le bon ordre :
    # d'abord les "enfants", puis le "parent".

    # 1. Ingrédients (via les groupes de cette recette)
    cur.execute("""
        DELETE i FROM Ingredient i
        JOIN IngredientGroupe ig ON i.id_ingredient_groupe = ig.id_ingredient_groupe
        WHERE ig.id_recette = %s
    """, (id_recette,))

    # 2. Groupes d'ingrédients
    cur.execute("DELETE FROM IngredientGroupe WHERE id_recette = %s", (id_recette,))

    # 3. Étapes
    cur.execute("DELETE FROM Etape WHERE id_recette = %s", (id_recette,))

    # 4. Commentaires et favoris liés à cette recette
    cur.execute("DELETE FROM Commentaire WHERE id_recette = %s", (id_recette,))
    cur.execute("DELETE FROM Favoris WHERE id_recette = %s", (id_recette,))

    # 5. La recette elle-même
    cur.execute("DELETE FROM Recette WHERE id_recette = %s", (id_recette,))

    mysql.connection.commit()
    cur.close()

    return jsonify({"message": "Recette supprimée"}), 200


# =========================================================
# CATEGORIES
# =========================================================

@app.route('/categories', methods=['GET'])
def liste_categories():
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT id_categorie, slug, label FROM Categorie")
    categories = cur.fetchall()
    cur.close()
    return jsonify(categories), 200


@app.route('/categories', methods=['POST'])
def creer_categorie():
    data = request.get_json()

    champs_requis = ['slug', 'label']
    for champ in champs_requis:
        if champ not in data:
            return jsonify({"erreur": f"Le champ '{champ}' est obligatoire"}), 400

    cur = mysql.connection.cursor()

    # On vérifie que le slug n'existe pas déjà (contrainte UNIQUE en base)
    cur.execute("SELECT id_categorie FROM Categorie WHERE slug = %s", (data['slug'],))
    if cur.fetchone():
        cur.close()
        return jsonify({"erreur": "Cette catégorie existe déjà"}), 400

    cur.execute("""
        INSERT INTO Categorie (slug, label)
        VALUES (%s, %s)
    """, (data['slug'], data['label']))
    mysql.connection.commit()

    nouvel_id = cur.lastrowid
    cur.close()

    return jsonify({"message": "Catégorie créée", "id_categorie": nouvel_id}), 201


# =========================================================
# UTILISATEURS : inscription / connexion
# =========================================================

@app.route('/inscription', methods=['POST'])
def inscription():
    data = request.get_json()

    champs_requis = ['nom', 'email', 'mot_passe']
    for champ in champs_requis:
        if champ not in data:
            return jsonify({"erreur": f"Le champ '{champ}' est obligatoire"}), 400

    cur = mysql.connection.cursor()

    # On vérifie que l'email n'est pas déjà utilisé
    cur.execute("SELECT id_utilisateur FROM Utilisateur WHERE email = %s", (data['email'],))
    if cur.fetchone():
        cur.close()
        return jsonify({"erreur": "Cet email est déjà utilisé"}), 400

    # IMPORTANT : on ne stocke jamais un mot de passe en clair.
    # generate_password_hash le transforme en une empreinte irréversible.
    mot_passe_hash = generate_password_hash(data['mot_passe'])

    cur.execute("""
        INSERT INTO Utilisateur (nom, email, mot_passe, role)
        VALUES (%s, %s, %s, %s)
    """, (
        data['nom'],
        data['email'],
        mot_passe_hash,
        data.get('role', 'membre')
    ))
    mysql.connection.commit()

    nouvel_id = cur.lastrowid
    cur.close()

    return jsonify({"message": "Compte créé", "id_utilisateur": nouvel_id}), 201


@app.route('/connexion', methods=['POST'])
def connexion():
    data = request.get_json()

    if 'email' not in data or 'mot_passe' not in data:
        return jsonify({"erreur": "Email et mot de passe requis"}), 400

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT * FROM Utilisateur WHERE email = %s", (data['email'],))
    utilisateur = cur.fetchone()
    cur.close()

    # On vérifie l'empreinte du mot de passe, jamais le mot de passe en clair
    if not utilisateur or not check_password_hash(utilisateur['mot_passe'], data['mot_passe']):
        return jsonify({"erreur": "Email ou mot de passe incorrect"}), 401

    return jsonify({
        "message": "Connexion réussie",
        "id_utilisateur": utilisateur['id_utilisateur'],
        "nom": utilisateur['nom'],
        "role": utilisateur['role']
    }), 200


# =========================================================
# FAVORIS
# =========================================================

@app.route('/utilisateurs/<int:id_utilisateur>/favoris', methods=['GET'])
def liste_favoris(id_utilisateur):
    """Renvoie la liste des recettes mises en favori par un utilisateur."""
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT f.id_favori, f.date_ajout, r.id_recette, r.slug, r.titre, r.image
        FROM Favoris f
        JOIN Recette r ON f.id_recette = r.id_recette
        WHERE f.id_utilisateur = %s
        ORDER BY f.date_ajout DESC
    """, (id_utilisateur,))
    favoris = cur.fetchall()
    cur.close()
    return jsonify(favoris), 200


@app.route('/favoris', methods=['POST'])
def ajouter_favori():
    data = request.get_json()

    champs_requis = ['id_utilisateur', 'id_recette']
    for champ in champs_requis:
        if champ not in data:
            return jsonify({"erreur": f"Le champ '{champ}' est obligatoire"}), 400

    cur = mysql.connection.cursor()

    # On évite les doublons : cette recette est-elle déjà en favori pour cet utilisateur ?
    cur.execute("""
        SELECT id_favori FROM Favoris
        WHERE id_utilisateur = %s AND id_recette = %s
    """, (data['id_utilisateur'], data['id_recette']))
    if cur.fetchone():
        cur.close()
        return jsonify({"erreur": "Cette recette est déjà dans les favoris"}), 400

    cur.execute("""
        INSERT INTO Favoris (date_ajout, id_recette, id_utilisateur)
        VALUES (CURDATE(), %s, %s)
    """, (data['id_recette'], data['id_utilisateur']))
    mysql.connection.commit()

    nouvel_id = cur.lastrowid
    cur.close()

    return jsonify({"message": "Recette ajoutée aux favoris", "id_favori": nouvel_id}), 201


@app.route('/favoris/<int:id_favori>', methods=['DELETE'])
def supprimer_favori(id_favori):
    cur = mysql.connection.cursor()

    cur.execute("SELECT id_favori FROM Favoris WHERE id_favori = %s", (id_favori,))
    if not cur.fetchone():
        cur.close()
        return jsonify({"erreur": "Favori introuvable"}), 404

    cur.execute("DELETE FROM Favoris WHERE id_favori = %s", (id_favori,))
    mysql.connection.commit()
    cur.close()

    return jsonify({"message": "Retiré des favoris"}), 200


# =========================================================
# LANCEMENT DU SERVEUR
# =========================================================

if __name__ == '__main__':
    app.run(debug=True)