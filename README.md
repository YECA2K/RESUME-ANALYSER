RESUME-ANALYSER

Recherche d’emploi intelligent basée sur l’IA

Présentation

RESUME-ANALYSER est une application intelligente de recommandation d’offres d’emploi.
Elle permet d’analyser automatiquement un CV au format PDF, d’en extraire les informations clés à l’aide de modèles de langage (LLM), puis de proposer les offres d’emploi les plus pertinentes à partir d’une base de données d’offres réelles.

Le projet s’inscrit dans une approche Data / IA / Cloud, avec une architecture modulaire, scalable et déployée sur AWS.

Objectifs du projet

Automatiser l’analyse des CV (extraction sémantique)

Recommander des offres pertinentes à l’aide d’embeddings vectoriels

Mettre en place un pipeline ETL automatisé pour la collecte des offres

Déployer une architecture complète en environnement cloud

Appliquer de bonnes pratiques DevOps, sécurité et MLOps

Architecture globale

Le projet repose sur les composants suivants :

Frontend : Streamlit
Interface utilisateur pour l’upload du CV et la visualisation des résultats.

Backend API : FastAPI
Gestion de l’extraction, du matching, des embeddings et des endpoints REST.

Base de données : MongoDB
Stockage des CV analysés, des offres d’emploi et de leurs vecteurs.

Pipeline ETL : Apache Airflow
Orchestration du scraping, nettoyage, vectorisation et maintenance des données.

Scraping : JobSpy
Collecte des offres depuis des sources publiques (Indeed, Glassdoor, LinkedIn).

Déploiement : Docker & Docker Compose sur AWS EC2.

Versioning : GitHub.

Fonctionnement du système

L’utilisateur téléverse un CV au format PDF.

Le PDF est converti en texte brut.

Un LLM extrait les informations structurées (nom, compétences, expériences, langues).

Le profil candidat est transformé en embedding vectoriel.

Les embeddings du CV sont comparés à ceux des offres stockées.

La similarité cosinus est calculée.

Un score final est généré à partir de :

similarité vectorielle (60 %),

recouvrement des compétences (10 %),

correspondance du domaine métier (30 %).

Les 20 offres les plus pertinentes sont affichées.

Pipeline ETL (Airflow)

Un DAG Airflow s’exécute automatiquement (ou manuellement) pour :

Scraper les offres d’emploi via JobSpy

Normaliser et nettoyer les données

Générer les embeddings des offres

Supprimer les anciennes données obsolètes

Ce pipeline garantit une base d’offres à jour et exploitable pour le matching.

Déploiement et sécurité

Déploiement sur AWS EC2 (Ubuntu).

Services conteneurisés avec Docker.

Orchestration via Docker Compose.

Accès EC2 sécurisé par groupes de sécurité AWS.

Exposition minimale des ports nécessaires.

Réseau Docker privé entre les services.

Données utilisées à des fins académiques uniquement.

Scraping limité à des sources publiques et open source.

Technologies utilisées

Python

FastAPI

Streamlit

MongoDB

Apache Airflow

JobSpy

Docker & Docker Compose

AWS EC2

OpenRouter (LLM)

GitHub

Lancer le projet (résumé)
docker compose up -d --build


API : http://localhost:8000/docs

Airflow : http://localhost:8080
 (admin / admin)
