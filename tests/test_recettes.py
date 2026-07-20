"""
tests/test_recettes.py
Tests pytest de base sur l'API Pâtissons.

Prérequis : MySQL doit être installé et en cours d'exécution localement,
puisque app.py se connecte à une vraie base au moment de son import.

Lancer avec : pytest
Lancer avec plus de détails : pytest -v
"""

import pytest
from app import app


@pytest.fixture
def client():
    """Crée un client de test Flask : simule des requêtes HTTP sans avoir
    besoin de lancer réellement le serveur avec `python app.py`."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_get_recettes_renvoie_200(client):
    """La liste des recettes doit toujours répondre avec succès (200),
    même si la base est vide."""
    response = client.get('/recettes')
    assert response.status_code == 200


def test_get_recettes_renvoie_une_liste_json(client):
    """La réponse doit être une liste JSON (même vide), pas un objet
    ou une erreur."""
    response = client.get('/recettes')
    data = response.get_json()
    assert isinstance(data, list)


def test_post_recette_sans_champ_obligatoire_renvoie_400(client):
    """Si un champ obligatoire manque (ici 'titre'), l'API doit refuser
    la création avec un code 400, pas planter avec une erreur 500."""
    recette_incomplete = {
        "slug": "recette-test",
        # "titre" volontairement absent
        "temps_preparation": 20,
        "portions": 4,
        "difficulte": "Facile",
        "id_utilisateur": 1,
        "id_categorie": 1
    }
    response = client.post('/recettes', json=recette_incomplete)
    assert response.status_code == 400


def test_get_recette_inexistante_renvoie_404(client):
    """Demander une recette avec un id qui n'existe sûrement pas doit
    renvoyer 404, pas planter."""
    response = client.get('/recettes/999999')
    assert response.status_code == 404