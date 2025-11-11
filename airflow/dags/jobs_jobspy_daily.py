from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="jobs_jobspy_daily",
    start_date=datetime(2025, 10, 1),
    schedule_interval="@daily",
    catchup=False,
    description="Collect with JobSpy (Indeed 24h) → normalize → match",
) as dag:

    collect = BashOperator(
        task_id="collect_jobspy",
        env={
            "PYTHONUNBUFFERED": "1",
            "DATA_LAKE_ROOT": "/workspace/datalake",
        },
        bash_command=(
            "python -u /workspace/scripts/jobspy_collect.py "
            "--queries ' ,ingénieur,développeur,technicien,consultant,chef de projet,manager,responsable,architecte,cloud,devops,data,analyste,commercial,marketing,rh,comptable,finance,logistique,qualité,sécurité,full stack,frontend,backend,IA,réseau,support,stage,alternance,junior,senior' "
            "--locations 'France,Remote,Paris,Lyon,Marseille,Toulouse,Lille,Bordeaux,Nantes,Strasbourg,Montpellier,Rennes,Nice,Grenoble,Reims,Le Havre,Saint-Étienne,Toulon,Dijon,Angers,Nîmes,Clermont-Ferrand,Aix-en-Provence,Brest,Tours,Orléans,Metz,Besançon,Rouen,Perpignan' "
            "--countries 'france' "
            "--sites indeed "
            "--pages 7 --days 1 "
            "--append 1 "
            "--outfile jobspy_all.jsonl"
        ),
    )

    normalize = BashOperator(
        task_id="normalize_jobspy",
        env={"API_URL": "http://resume-analyser-api-1:8000"},
        bash_command="python /workspace/scripts/jobspy_normalize_jobs.py"
    )

    match_demo = BashOperator(
        task_id="match_demo",
        bash_command="curl -X POST 'http://api:8000/match/run?job_title=Data%20Engineer'"
    )

    collect >> normalize >> match_demo
