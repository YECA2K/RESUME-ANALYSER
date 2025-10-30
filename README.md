<<<<<<< HEAD
# All-in-One: API + Mongo + Airflow + JobSpy (no front)

## 1) Démarrer toute la stack
```bash
docker compose up -d --build
```

- API: http://localhost:8000/docs
- Airflow UI: http://localhost:8080 (admin / admin)

## 2) Initialiser Airflow (si premier run)
```bash
docker compose up airflow-init
# une fois terminé (exits), lance :
docker compose up -d airflow-scheduler airflow-webserver
```

## 3) Exécuter le pipeline (Airflow UI)
- Ouvre http://localhost:8080, connecte-toi (admin/admin)
- Active le DAG **jobs_jobspy_daily**
- Tu peux aussi cliquer **Trigger DAG** pour lancer immédiatement

## 4) Exécuter manuellement (sans Airflow)
```bash
# collecte
docker compose exec api python scripts/jobspy_collect.py --query "Data Engineer" --location "France" --sites indeed,glassdoor,linkedin --pages 2 --days 7
# normalisation + ingestion
docker compose exec api python scripts/jobspy_normalize_jobs.py
# matching (stub)
curl -X POST "http://localhost:8000/match/run?job_title=Data%20Engineer"
curl "http://localhost:8000/match?job_title=Data%20Engineer&k=10"
```

## 5) Data Lake local
- Tous les bruts sont sous `./ops/datalake/` (monté dans API & Airflow).
- CV uploadés: `raw/cv/`, texte CV: `raw/cv_text/`, offres jobspy: `raw/jobs/`.

## 6) Remarques
- JobSpy est inclus côté API (requirements).
- Airflow exécute les scripts montés via `/workspace/scripts`.
- Si tu changes l'URL de l'API, adapte `API_URL` dans le DAG.
=======
# RESUME-ANALYSER
RESUME-ANALYSER
>>>>>>> 4abcca27d994b246294688ffed085d743c77aa5f
