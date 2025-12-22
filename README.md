# RESUME-ANALYSER
## Intelligent Job Search Powered by AI

---

## Overview

**RESUME-ANALYSER** is an intelligent job recommendation system designed to analyze resumes (CVs) in PDF format and automatically match candidates with the most relevant job offers.

The application leverages **Large Language Models (LLMs)**, **vector embeddings**, and a **data-driven matching pipeline** to provide accurate and contextual job recommendations.

The project follows a **Data / AI / Cloud** approach with a modular, scalable architecture deployed on **AWS**.

---

## Project Objectives

- Automate resume analysis using semantic extraction
- Recommend relevant job offers using vector embeddings
- Build an automated ETL pipeline for job data collection
- Deploy a full cloud-based architecture
- Apply DevOps, security, and MLOps best practices

---

## Global Architecture

The system is composed of the following components:

### Frontend
- **Streamlit**
- User interface for CV upload and results visualization

### Backend API
- **FastAPI**
- Handles CV processing, embeddings generation, job matching, and REST endpoints

### Database
- **MongoDB**
- Stores analyzed CVs, job offers, and their vector representations

### ETL Pipeline
- **Apache Airflow**
- Orchestrates scraping, normalization, vectorization, and data cleanup

### Scraping
- **JobSpy**
- Collects job offers from public sources (Indeed, Glassdoor, LinkedIn)

### Deployment
- **Docker & Docker Compose**
- Deployed on **AWS EC2**

### Version Control
- **GitHub**

---

## System Workflow

1. The user uploads a CV in PDF format.
2. The PDF is converted into raw text.
3. A Large Language Model extracts structured information:
   - Name
   - Skills
   - Work experience
   - Languages
4. The candidate profile is transformed into a vector embedding.
5. CV embeddings are compared with job offer embeddings.
6. Cosine similarity is computed.
7. A final matching score is calculated using:
   - Vector similarity (60%)
   - Skill overlap (10%)
   - Domain relevance (30%)
8. The top 20 most relevant job offers are returned to the user.

---

## ETL Pipeline with Airflow

A scheduled Airflow DAG ensures that job data remains fresh and relevant:

- Scraping job offers via JobSpy
- Cleaning and normalizing data
- Generating embeddings for job descriptions
- Removing outdated job offers

This pipeline runs automatically and can also be triggered manually via the Airflow UI.

---

## Deployment and Security

- Deployed on an **AWS EC2 (Ubuntu)** instance
- All services are containerized using Docker
- Orchestrated with Docker Compose
- EC2 access secured via AWS Security Groups
- Only required ports are exposed
- Internal services communicate over a private Docker network
- CV data is used strictly for academic purposes
- Scraping is limited to public, open-source job listings

---

## Technologies Used

- Python
- FastAPI
- Streamlit
- MongoDB
- Apache Airflow
- JobSpy
- Docker / Docker Compose
- AWS EC2
- OpenRouter (LLM access)
- GitHub

---

## Quick Start

```bash
docker compose up -d --build
