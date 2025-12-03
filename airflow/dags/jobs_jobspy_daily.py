from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime

PYTHON = "python"

with DAG(
    dag_id="jobs_jobspy_daily",
    start_date=datetime(2025, 10, 1),
    schedule_interval="@daily",  # exécution automatique chaque 24h
    catchup=False,
    description="Scraping → Normalize → Embeddings → Cleanup (jobs IT)",
) as dag:

    # Environnement commun pour tous les scripts
    common_env = {
        "PYTHONPATH": "/app",                # pour pouvoir importer app.*
        "DATA_LAKE_ROOT": "/workspace/datalake",
        "MONGO_URL": "mongodb://mongo:27017",
        "DB_NAME": "matcher",
        "API_URL": "http://api:8000",
    }

    # 1) SCRAPING IT (24h dernières offres)
    collect = BashOperator(
        task_id="collect_jobspy",
        env={
            **common_env,
            "DATA_LAKE_ROOT": "/workspace/datalake",
        },
        bash_command=(
            f"{PYTHON} /workspace/scripts/jobspy_collect.py "
            "--days 1 "                # ↩ 24h = 1 jour
            "--max_per_call 400 "      # ↩ max par (term, location)
            "--max_total 2500 "        # ↩ limite globale par run
            "--keep_days 10 "          # ↩ garde les fichiers JSONL 10 jours
            "--min_it_jobs 500"        # ↩ warning si < 500 jobs IT collectés
        ),
    )

    # 2) NORMALISATION + FILTRE IT FINAL + ENVOI API → Mongo
    normalize = BashOperator(
        task_id="normalize_jobspy",
        env={
            **common_env,
            "API_URL": "http://api:8000",
        },
        bash_command=f"{PYTHON} /workspace/scripts/jobspy_normalize_jobs.py",
    )

    # 3) EMBEDDINGS (pour les jobs sans embedding, au cas où)
    embed = BashOperator(
        task_id="embed_jobs",
        env={
            **common_env,
        },
        bash_command=f"{PYTHON} /workspace/scripts/embed_jobs.py",
    )

    # 4) CLEANUP (Mongo + datalake) sur 10 jours
    cleanup = BashOperator(
        task_id="cleanup_old_data",
        env={
            **common_env,
            "KEEP_DAYS": "10",   # ↩ suppression jobs + fichiers > 10 jours
        },
        bash_command=f"{PYTHON} /workspace/scripts/cleanup.py",
    )

    # Ordre du pipeline
    collect >> normalize >> embed >> cleanup
