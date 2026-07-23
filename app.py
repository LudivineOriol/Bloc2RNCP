from flask import Flask, jsonify, request, g
import pymysql
import pymysql.cursors
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import jwt
import datetime
import os

load_dotenv()

app = Flask(__name__)

# --- Configuration MySQL ---
app.config["MYSQL_HOST"] = os.getenv("MYSQL_HOST")
app.config["MYSQL_PORT"] = int(os.getenv("MYSQL_PORT"))
app.config["MYSQL_USER"] = os.getenv("MYSQL_USER")
app.config["MYSQL_PASSWORD"] = os.getenv("MYSQL_PASSWORD")
app.config["MYSQL_DB"] = os.getenv("MYSQL_DB")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")


def get_db():
    """Renvoie la connexion MySQL de la requête en cours. La connexion est
    ouverte une seule fois par requête et stockée sur `g` (un objet fourni
    par Flask qui ne vit que le temps d'une requête), puis réutilisée si
    plusieurs routes/fonctions en ont besoin dans la même requête."""
    if "db" not in g:
        g.db = pymysql.connect(
            host=app.config["MYSQL_HOST"],
            port=app.config["MYSQL_PORT"],
            user=app.config["MYSQL_USER"],
            password=app.config["MYSQL_PASSWORD"],
            database=app.config["MYSQL_DB"],
            autocommit=False,
        )
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    """Ferme la connexion à la fin de la requête, MAIS seulement si une
    connexion a réellement été ouverte (g.pop renvoie None sinon). C'est
    exactement la vérification qui manquait dans flask-mysqldb et qui
    provoquait l'erreur (2006, '') : on ne referme jamais une connexion
    qui n'existe pas ou qui a déjà été fermée."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def token_required(f):
    """Décorateur à poser sur une route pour exiger un jeton JWT valide.

    Le jeton doit être envoyé dans le header HTTP :
        Authorization: Bearer <token>

    S'il est valide, on stocke les infos de l'utilisateur connecté dans
    `g.utilisateur_courant` (accessible ensuite dans la route, un peu
    comme `g.db`). S'il est absent, expiré, ou invalide, on bloque la
    requête avant même qu'elle n'atteigne la route protégée."""

    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get("Authorization")

        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"erreur": "Jeton d'authentification manquant"}), 401

        try:
            payload = jwt.decode(
                token, app.config["SECRET_KEY"], algorithms=["HS256"]
            )
            g.utilisateur_courant = {
                "id_utilisateur": payload["id_utilisateur"],
                "role": payload["role"],
            }
        except jwt.ExpiredSignatureError:
            return jsonify({"erreur": "Jeton expiré, reconnectez-vous"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"erreur": "Jeton invalide"}), 401

        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    """Comme `token_required`, mais exige en plus que l'utilisateur ait le
    rôle 'administrateur'. On réutilise token_required pour ne pas dupliquer
    la logique de vérification du jeton."""

    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        if g.utilisateur_courant["role"] != "administrateur":
            return jsonify({"erreur": "Réservé aux administrateurs"}), 403
        return f(*args, **kwargs)

    return decorated


# =========================================================
# ROUTE DE TEST
# =========================================================


@app.route("/")
def index():
    return jsonify({"message": "API Pâtissons opérationnelle"})


# =========================================================
# RECETTES
# =========================================================


@app.route("/recettes", methods=["GET"])
def liste_recettes():
    """Renvoie la liste de toutes les recettes (vue simplifiée, sans le détail
    des ingrédients/étapes, pour rester léger)."""
    cur = get_db().cursor(pymysql.cursors.DictCursor)
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


@app.route("/recettes/<int:id_recette>", methods=["GET"])
def detail_recette(id_recette):
    """Renvoie une recette complète : infos principales + ingrédients (groupés) + étapes."""
    cur = get_db().cursor(pymysql.cursors.DictCursor)

    cur.execute(
        """
        SELECT r.*, c.label AS categorie
        FROM Recette r
        JOIN Categorie c ON r.id_categorie = c.id_categorie
        WHERE r.id_recette = %s
    """,
        (id_recette,),
    )
    recette = cur.fetchone()

    if not recette:
        cur.close()
        return jsonify({"erreur": "Recette introuvable"}), 404

    # Groupes d'ingrédients + leurs ingrédients
    cur.execute(
        """
        SELECT id_ingredient_groupe, nom_groupe, ordre
        FROM IngredientGroupe
        WHERE id_recette = %s
        ORDER BY ordre
    """,
        (id_recette,),
    )
    groupes = cur.fetchall()

    for groupe in groupes:
        cur.execute(
            """
            SELECT nom, quantite, unite, ordre
            FROM Ingredient
            WHERE id_ingredient_groupe = %s
            ORDER BY ordre
        """,
            (groupe["id_ingredient_groupe"],),
        )
        groupe["ingredients"] = cur.fetchall()

    recette["ingredients"] = groupes

    # Étapes
    cur.execute(
        """
        SELECT ordre, titre, description
        FROM Etape
        WHERE id_recette = %s
        ORDER BY ordre
    """,
        (id_recette,),
    )
    recette["etapes"] = cur.fetchall()

    cur.close()
    return jsonify(recette), 200


@app.route("/recettes", methods=["POST"])
@token_required
def creer_recette():
    """Crée une recette complète en une seule requête : infos principales,
    et éventuellement ses groupes d'ingrédients + ingrédients, et ses étapes.

    Format JSON attendu (les clés "ingredients" et "etapes" sont optionnelles) :
    {
        "slug": "...", "titre": "...", "temps_preparation": 30, "portions": 6,
        "difficulte": "Facile", "id_categorie": 1,
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

    champs_requis = [
        "slug",
        "titre",
        "temps_preparation",
        "portions",
        "difficulte",
        "id_categorie",
    ]
    for champ in champs_requis:
        if champ not in data:
            return jsonify({"erreur": f"Le champ '{champ}' est obligatoire"}), 400

    # L'auteur de la recette est l'utilisateur connecté (token), jamais une
    # valeur envoyée dans le body.
    id_utilisateur = g.utilisateur_courant["id_utilisateur"]

    cur = get_db().cursor()

    # 1. La recette principale
    cur.execute(
        """
        INSERT INTO Recette
            (slug, titre, description, temps_preparation, temps_cuisson,
             temps_repos, portions, difficulte, image, conseils, statut,
             id_utilisateur, id_categorie)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """,
        (
            data["slug"],
            data["titre"],
            data.get("description"),
            data["temps_preparation"],
            data.get("temps_cuisson"),
            data.get("temps_repos"),
            data["portions"],
            data["difficulte"],
            data.get("image"),
            data.get("conseils"),
            data.get("statut", "brouillon"),
            id_utilisateur,
            data["id_categorie"],
        ),
    )
    id_recette = cur.lastrowid

    # 2. Groupes d'ingrédients + ingrédients (optionnel)
    for ordre_groupe, groupe in enumerate(data.get("ingredients", []), start=1):
        cur.execute(
            """
            INSERT INTO IngredientGroupe (nom_groupe, ordre, id_recette)
            VALUES (%s, %s, %s)
        """,
            (groupe["groupe"], ordre_groupe, id_recette),
        )
        id_groupe = cur.lastrowid

        for ordre_item, item in enumerate(groupe.get("items", []), start=1):
            cur.execute(
                """
                INSERT INTO Ingredient (nom, quantite, unite, ordre, id_ingredient_groupe)
                VALUES (%s, %s, %s, %s, %s)
            """,
                (
                    item["nom"],
                    item.get("quantite") or 0,
                    item.get("unite"),
                    ordre_item,
                    id_groupe,
                ),
            )

    # 3. Étapes (optionnel)
    for etape in data.get("etapes", []):
        cur.execute(
            """
            INSERT INTO Etape (ordre, titre, description, id_recette)
            VALUES (%s, %s, %s, %s)
        """,
            (etape["numero"], etape["titre"], etape["description"], id_recette),
        )

    get_db().commit()
    cur.close()

    return jsonify({"message": "Recette créée", "id_recette": id_recette}), 201


@app.route("/recettes/<int:id_recette>", methods=["PUT"])
@token_required
def modifier_recette(id_recette):
    data = request.get_json()

    cur = get_db().cursor(pymysql.cursors.DictCursor)

    # On vérifie d'abord que la recette existe
    cur.execute("SELECT id_utilisateur FROM Recette WHERE id_recette = %s", (id_recette,))
    recette = cur.fetchone()
    if not recette:
        cur.close()
        return jsonify({"erreur": "Recette introuvable"}), 404

    utilisateur_courant = g.utilisateur_courant
    est_auteur = recette["id_utilisateur"] == utilisateur_courant["id_utilisateur"]
    est_admin = utilisateur_courant["role"] == "administrateur"

    if not est_auteur and not est_admin:
        cur.close()
        return (
            jsonify({"erreur": "Vous ne pouvez modifier que vos propres recettes"}),
            403,
        )

    champs_requis = [
        "slug",
        "titre",
        "temps_preparation",
        "portions",
        "difficulte",
        "id_categorie",
    ]
    for champ in champs_requis:
        if champ not in data:
            cur.close()
            return jsonify({"erreur": f"Le champ '{champ}' est obligatoire"}), 400

    cur.execute(
        """
        UPDATE Recette
        SET slug = %s, titre = %s, description = %s, temps_preparation = %s,
            temps_cuisson = %s, temps_repos = %s, portions = %s, difficulte = %s,
            image = %s, conseils = %s, statut = %s, id_categorie = %s
        WHERE id_recette = %s
    """,
        (
            data["slug"],
            data["titre"],
            data.get("description"),
            data["temps_preparation"],
            data.get("temps_cuisson"),
            data.get("temps_repos"),
            data["portions"],
            data["difficulte"],
            data.get("image"),
            data.get("conseils"),
            data.get("statut", "brouillon"),
            data["id_categorie"],
            id_recette,
        ),
    )
    get_db().commit()
    cur.close()

    return jsonify({"message": "Recette mise à jour"}), 200


@app.route("/recettes/<int:id_recette>", methods=["DELETE"])
@token_required
def supprimer_recette(id_recette):
    cur = get_db().cursor(pymysql.cursors.DictCursor)

    cur.execute("SELECT id_utilisateur FROM Recette WHERE id_recette = %s", (id_recette,))
    recette = cur.fetchone()
    if not recette:
        cur.close()
        return jsonify({"erreur": "Recette introuvable"}), 404

    utilisateur_courant = g.utilisateur_courant
    est_auteur = recette["id_utilisateur"] == utilisateur_courant["id_utilisateur"]
    est_admin = utilisateur_courant["role"] == "administrateur"

    if not est_auteur and not est_admin:
        cur.close()
        return (
            jsonify({"erreur": "Vous ne pouvez supprimer que vos propres recettes"}),
            403,
        )

    # Il n'y a pas de suppression en cascade automatique en base,
    # donc on supprime nous-mêmes les données liées, dans le bon ordre :
    # d'abord les "enfants", puis le "parent".

    # 1. Ingrédients (via les groupes de cette recette)
    cur.execute(
        """
        DELETE i FROM Ingredient i
        JOIN IngredientGroupe ig ON i.id_ingredient_groupe = ig.id_ingredient_groupe
        WHERE ig.id_recette = %s
    """,
        (id_recette,),
    )

    # 2. Groupes d'ingrédients
    cur.execute("DELETE FROM IngredientGroupe WHERE id_recette = %s", (id_recette,))

    # 3. Étapes
    cur.execute("DELETE FROM Etape WHERE id_recette = %s", (id_recette,))

    # 4. Commentaires et favoris liés à cette recette
    cur.execute("DELETE FROM Commentaire WHERE id_recette = %s", (id_recette,))
    cur.execute("DELETE FROM Favoris WHERE id_recette = %s", (id_recette,))

    # 5. La recette elle-même
    cur.execute("DELETE FROM Recette WHERE id_recette = %s", (id_recette,))

    get_db().commit()
    cur.close()

    return jsonify({"message": "Recette supprimée"}), 200


# =========================================================
# CATEGORIES
# =========================================================


@app.route("/categories", methods=["GET"])
def liste_categories():
    cur = get_db().cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT id_categorie, slug, label FROM Categorie")
    categories = cur.fetchall()
    cur.close()
    return jsonify(categories), 200


@app.route("/categories", methods=["POST"])
@admin_required
def creer_categorie():
    data = request.get_json()

    champs_requis = ["slug", "label"]
    for champ in champs_requis:
        if champ not in data:
            return jsonify({"erreur": f"Le champ '{champ}' est obligatoire"}), 400

    cur = get_db().cursor()

    # On vérifie que le slug n'existe pas déjà (contrainte UNIQUE en base)
    cur.execute("SELECT id_categorie FROM Categorie WHERE slug = %s", (data["slug"],))
    if cur.fetchone():
        cur.close()
        return jsonify({"erreur": "Cette catégorie existe déjà"}), 400

    cur.execute(
        """
        INSERT INTO Categorie (slug, label)
        VALUES (%s, %s)
    """,
        (data["slug"], data["label"]),
    )
    get_db().commit()

    nouvel_id = cur.lastrowid
    cur.close()

    return jsonify({"message": "Catégorie créée", "id_categorie": nouvel_id}), 201


# =========================================================
# UTILISATEURS : inscription / connexion
# =========================================================


@app.route("/inscription", methods=["POST"])
def inscription():
    data = request.get_json()

    champs_requis = ["nom", "email", "mot_passe"]
    for champ in champs_requis:
        if champ not in data:
            return jsonify({"erreur": f"Le champ '{champ}' est obligatoire"}), 400

    cur = get_db().cursor()

    # On vérifie que l'email n'est pas déjà utilisé
    cur.execute(
        "SELECT id_utilisateur FROM Utilisateur WHERE email = %s", (data["email"],)
    )
    if cur.fetchone():
        cur.close()
        return jsonify({"erreur": "Cet email est déjà utilisé"}), 400

    # IMPORTANT : on ne stocke jamais un mot de passe en clair.
    # generate_password_hash le transforme en une empreinte irréversible.
    mot_passe_hash = generate_password_hash(data["mot_passe"])

    cur.execute(
        """
        INSERT INTO Utilisateur (nom, email, mot_passe, role)
        VALUES (%s, %s, %s, %s)
    """,
        (data["nom"], data["email"], mot_passe_hash, "membre"),
    )
    get_db().commit()

    nouvel_id = cur.lastrowid
    cur.close()

    return jsonify({"message": "Compte créé", "id_utilisateur": nouvel_id}), 201


@app.route("/connexion", methods=["POST"])
def connexion():
    data = request.get_json()

    if "email" not in data or "mot_passe" not in data:
        return jsonify({"erreur": "Email et mot de passe requis"}), 400

    cur = get_db().cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM Utilisateur WHERE email = %s", (data["email"],))
    utilisateur = cur.fetchone()
    cur.close()

    # On vérifie l'empreinte du mot de passe, jamais le mot de passe en clair
    if not utilisateur or not check_password_hash(
        utilisateur["mot_passe"], data["mot_passe"]
    ):
        return jsonify({"erreur": "Email ou mot de passe incorrect"}), 401

    # Génération du jeton JWT : il contient l'identité de l'utilisateur,
    # signée avec la clé secrète du serveur, et expire après 24h.
    token = jwt.encode(
        {
            "id_utilisateur": utilisateur["id_utilisateur"],
            "role": utilisateur["role"],
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=24),
        },
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )

    return (
        jsonify(
            {
                "message": "Connexion réussie",
                "token": token,
                "id_utilisateur": utilisateur["id_utilisateur"],
                "nom": utilisateur["nom"],
                "role": utilisateur["role"],
            }
        ),
        200,
    )


# =========================================================
# COMMENTAIRES
# =========================================================


@app.route("/recettes/<int:id_recette>/commentaires", methods=["GET"])
def liste_commentaires(id_recette):
    """Renvoie les commentaires d'une recette, du plus récent au plus ancien,
    avec le nom de l'auteur (jointure sur Utilisateur)."""
    cur = get_db().cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        SELECT c.id_commentaire, c.contenu, c.date_publication,
               c.id_utilisateur, u.nom AS auteur
        FROM Commentaire c
        JOIN Utilisateur u ON c.id_utilisateur = u.id_utilisateur
        WHERE c.id_recette = %s
        ORDER BY c.date_publication DESC
    """,
        (id_recette,),
    )
    commentaires = cur.fetchall()
    cur.close()
    return jsonify(commentaires), 200


@app.route("/commentaires", methods=["POST"])
@token_required
def ajouter_commentaire():
    data = request.get_json()

    if "contenu" not in data or "id_recette" not in data:
        return jsonify({"erreur": "Le champ 'contenu' et 'id_recette' sont obligatoires"}), 400

    # On ne fait plus confiance à un éventuel "id_utilisateur" envoyé dans le
    # body : on prend l'identité authentifiée par le jeton JWT, pour qu'on
    # ne puisse pas poster un commentaire "au nom" de quelqu'un d'autre.
    id_utilisateur = g.utilisateur_courant["id_utilisateur"]

    cur = get_db().cursor()

    # On vérifie que la recette existe avant d'y attacher un commentaire
    cur.execute(
        "SELECT id_recette FROM Recette WHERE id_recette = %s", (data["id_recette"],)
    )
    if not cur.fetchone():
        cur.close()
        return jsonify({"erreur": "Recette introuvable"}), 404

    cur.execute(
        """
        INSERT INTO Commentaire (contenu, date_publication, id_recette, id_utilisateur)
        VALUES (%s, CURDATE(), %s, %s)
    """,
        (data["contenu"], data["id_recette"], id_utilisateur),
    )
    get_db().commit()

    nouvel_id = cur.lastrowid
    cur.close()

    return (
        jsonify({"message": "Commentaire ajouté", "id_commentaire": nouvel_id}),
        201,
    )


@app.route("/commentaires/<int:id_commentaire>", methods=["DELETE"])
@token_required
def supprimer_commentaire(id_commentaire):
    """Suppression d'un commentaire : autorisée pour son auteur, ou pour un
    administrateur (modération)."""
    cur = get_db().cursor(pymysql.cursors.DictCursor)

    cur.execute(
        "SELECT id_utilisateur FROM Commentaire WHERE id_commentaire = %s",
        (id_commentaire,),
    )
    commentaire = cur.fetchone()

    if not commentaire:
        cur.close()
        return jsonify({"erreur": "Commentaire introuvable"}), 404

    utilisateur_courant = g.utilisateur_courant
    est_auteur = commentaire["id_utilisateur"] == utilisateur_courant["id_utilisateur"]
    est_admin = utilisateur_courant["role"] == "administrateur"

    if not est_auteur and not est_admin:
        cur.close()
        return (
            jsonify({"erreur": "Vous ne pouvez supprimer que vos propres commentaires"}),
            403,
        )

    cur.execute("DELETE FROM Commentaire WHERE id_commentaire = %s", (id_commentaire,))
    get_db().commit()
    cur.close()

    return jsonify({"message": "Commentaire supprimé"}), 200


# =========================================================
# FAVORIS
# =========================================================


@app.route("/utilisateurs/<int:id_utilisateur>/favoris", methods=["GET"])
@token_required
def liste_favoris(id_utilisateur):
    """Renvoie la liste des recettes mises en favori par un utilisateur."""
    utilisateur_courant = g.utilisateur_courant
    est_lui_meme = utilisateur_courant["id_utilisateur"] == id_utilisateur
    est_admin = utilisateur_courant["role"] == "administrateur"

    if not est_lui_meme and not est_admin:
        return (
            jsonify({"erreur": "Vous ne pouvez consulter que vos propres favoris"}),
            403,
        )

    cur = get_db().cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        SELECT f.id_favori, f.date_ajout, r.id_recette, r.slug, r.titre, r.image
        FROM Favoris f
        JOIN Recette r ON f.id_recette = r.id_recette
        WHERE f.id_utilisateur = %s
        ORDER BY f.date_ajout DESC
    """,
        (id_utilisateur,),
    )
    favoris = cur.fetchall()
    cur.close()
    return jsonify(favoris), 200


@app.route("/favoris", methods=["POST"])
@token_required
def ajouter_favori():
    data = request.get_json()

    if "id_recette" not in data:
        return jsonify({"erreur": "Le champ 'id_recette' est obligatoire"}), 400

    # Comme pour les commentaires : l'utilisateur concerné est celui du
    # jeton, jamais celui envoyé dans le body.
    id_utilisateur = g.utilisateur_courant["id_utilisateur"]

    cur = get_db().cursor()

    # On évite les doublons : cette recette est-elle déjà en favori pour cet utilisateur ?
    cur.execute(
        """
        SELECT id_favori FROM Favoris
        WHERE id_utilisateur = %s AND id_recette = %s
    """,
        (id_utilisateur, data["id_recette"]),
    )
    if cur.fetchone():
        cur.close()
        return jsonify({"erreur": "Cette recette est déjà dans les favoris"}), 400

    cur.execute(
        """
        INSERT INTO Favoris (date_ajout, id_recette, id_utilisateur)
        VALUES (CURDATE(), %s, %s)
    """,
        (data["id_recette"], id_utilisateur),
    )
    get_db().commit()

    nouvel_id = cur.lastrowid
    cur.close()

    return (
        jsonify({"message": "Recette ajoutée aux favoris", "id_favori": nouvel_id}),
        201,
    )


@app.route("/favoris/<int:id_favori>", methods=["DELETE"])
@token_required
def supprimer_favori(id_favori):
    cur = get_db().cursor(pymysql.cursors.DictCursor)

    cur.execute("SELECT id_utilisateur FROM Favoris WHERE id_favori = %s", (id_favori,))
    favori = cur.fetchone()

    if not favori:
        cur.close()
        return jsonify({"erreur": "Favori introuvable"}), 404

    utilisateur_courant = g.utilisateur_courant
    est_proprietaire = favori["id_utilisateur"] == utilisateur_courant["id_utilisateur"]

    if not est_proprietaire:
        cur.close()
        return (
            jsonify({"erreur": "Vous ne pouvez retirer que vos propres favoris"}),
            403,
        )

    cur.execute("DELETE FROM Favoris WHERE id_favori = %s", (id_favori,))
    get_db().commit()
    cur.close()

    return jsonify({"message": "Retiré des favoris"}), 200


# =========================================================
# LANCEMENT DU SERVEUR
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)