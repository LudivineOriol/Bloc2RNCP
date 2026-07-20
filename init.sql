
USE patissons;

CREATE TABLE Utilisateur(
   id_utilisateur INT AUTO_INCREMENT,
   nom VARCHAR(50)  NOT NULL,
   email VARCHAR(150)  NOT NULL,
   mot_passe VARCHAR(255)  NOT NULL,
   role VARCHAR(50)  NOT NULL,
   PRIMARY KEY(id_utilisateur),
   UNIQUE(email)
);

CREATE TABLE Categorie(
   id_categorie INT AUTO_INCREMENT,
   slug VARCHAR(50)  NOT NULL,
   label VARCHAR(50)  NOT NULL,
   PRIMARY KEY(id_categorie),
   UNIQUE(slug)
);

CREATE TABLE Recette(
   id_recette INT AUTO_INCREMENT,
   slug VARCHAR(100)  NOT NULL,
   titre VARCHAR(150)  NOT NULL,
   description TEXT,
   temps_preparation SMALLINT UNSIGNED NOT NULL,
   temps_cuisson SMALLINT UNSIGNED,
   temps_repos SMALLINT UNSIGNED,
   portions TINYINT NOT NULL,
   difficulte VARCHAR(50)  NOT NULL,
   image VARCHAR(250) ,
   conseils TEXT,
   statut VARCHAR(50) ,
   id_utilisateur INT NOT NULL,
   id_categorie INT NOT NULL,
   PRIMARY KEY(id_recette),
   UNIQUE(slug),
   FOREIGN KEY(id_utilisateur) REFERENCES Utilisateur(id_utilisateur),
   FOREIGN KEY(id_categorie) REFERENCES Categorie(id_categorie)
);

CREATE TABLE IngredientGroupe(
   id_ingredient_groupe INT AUTO_INCREMENT,
   nom_groupe VARCHAR(100) ,
   ordre TINYINT NOT NULL,
   id_recette INT NOT NULL,
   PRIMARY KEY(id_ingredient_groupe),
   FOREIGN KEY(id_recette) REFERENCES Recette(id_recette)
);

CREATE TABLE Etape(
   id_etape INT AUTO_INCREMENT,
   ordre INT NOT NULL,
   titre VARCHAR(150)  NOT NULL,
   description TEXT  NOT NULL,
   id_recette INT NOT NULL,
   PRIMARY KEY(id_etape),
   FOREIGN KEY(id_recette) REFERENCES Recette(id_recette)
);

CREATE TABLE Commentaire(
   id_commentaire INT AUTO_INCREMENT,
   contenu TEXT  NOT NULL,
   date_publication DATE NOT NULL,
   id_recette INT NOT NULL,
   id_utilisateur INT NOT NULL,
   PRIMARY KEY(id_commentaire),
   FOREIGN KEY(id_recette) REFERENCES Recette(id_recette),
   FOREIGN KEY(id_utilisateur) REFERENCES Utilisateur(id_utilisateur)
);

CREATE TABLE Favoris(
   id_favori INT AUTO_INCREMENT,
   date_ajout DATE NOT NULL,
   id_recette INT NOT NULL,
   id_utilisateur INT NOT NULL,
   PRIMARY KEY(id_favori),
   FOREIGN KEY(id_recette) REFERENCES Recette(id_recette),
   FOREIGN KEY(id_utilisateur) REFERENCES Utilisateur(id_utilisateur)
);

CREATE TABLE Ingredient(
   id_ingredient INT AUTO_INCREMENT,
   nom VARCHAR(150)  NOT NULL,
   quantite FLOAT NOT NULL,
   unite VARCHAR(50) ,
   ordre TINYINT NOT NULL,
   id_ingredient_groupe INT NOT NULL,
   PRIMARY KEY(id_ingredient),
   FOREIGN KEY(id_ingredient_groupe) REFERENCES IngredientGroupe(id_ingredient_groupe)
);
