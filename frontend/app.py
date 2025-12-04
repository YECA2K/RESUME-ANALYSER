import os
import time
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st
from pymongo import MongoClient
import fitz  # PyMuPDF


# ======================================================
# CONFIG
# ======================================================
st.set_page_config(
    page_title="Intelligent Job Finder",
    page_icon="🧠",
    layout="wide",
)

API_URL = os.getenv("API_URL", "http://localhost:8000")

AIRFLOW_API_URL = os.getenv("AIRFLOW_API_URL", "http://airflow-webserver:8080/api/v1")
AIRFLOW_USER = os.getenv("AIRFLOW_USER", "admin")
AIRFLOW_PASSWORD = os.getenv("AIRFLOW_PASSWORD", "admin")

DAG_ID = os.getenv("AIRFLOW_DAG_ID", "jobs_jobspy_daily")

AUTO_REFRESH_SECONDS = 5  # ✅ fixed refresh interval (no user setting)

# Mongo
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB = os.getenv("MONGO_DB", "matcher")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "jobs")


# ======================================================
# CSS + DARK MODE
# ======================================================
st.markdown(
    """
<style>
.main { background-color: #f7f9fc; color: #1b1b1b; }
.sidebar .sidebar-content { background-color: #eef2f7; }

.stButton>button {
    border-radius: 10px;
    font-weight: 700;
    background-color: #4B77BE;
    color: white;
    padding: 0.5em 1em;
}

.metric { font-size: 24px !important; font-weight: bold !important; }

.small-muted { opacity: 0.7; font-size: 0.9rem; }
.badge {
    display: inline-block;
    padding: 0.2rem 0.55rem;
    border-radius: 14px;
    font-size: 0.85rem;
    font-weight: 700;
}
.badge-running { background: #FFF3CD; color: #856404; }
.badge-success { background: #D4EDDA; color: #155724; }
.badge-failed  { background: #F8D7DA; color: #721C24; }
.badge-queued  { background: #D1ECF1; color: #0C5460; }
.badge-other   { background: #E2E3E5; color: #383D41; }
</style>
""",
    unsafe_allow_html=True,
)

dark_mode = st.sidebar.checkbox("🌙 Mode sombre", value=False)

if dark_mode:
    bg_color = "#121212"
    text_color = "#e0e0e0"
    sidebar_bg = "#1e1e1e"
    btn_bg = "#333333"
    btn_color = "#ffffff"
else:
    bg_color = "#f7f9fc"
    text_color = "#1b1b1b"
    sidebar_bg = "#eef2f7"
    btn_bg = "#4B77BE"
    btn_color = "#ffffff"

st.markdown(
    f"""
<style>
[data-testid="stAppViewContainer"], body {{
    background-color: {bg_color};
    color: {text_color};
}}
[data-testid="stSidebar"] {{
    background-color: {sidebar_bg};
    color: {text_color};
}}
.stButton>button {{
    background-color: {btn_bg};
    color: {btn_color};
}}
</style>
""",
    unsafe_allow_html=True,
)


# ======================================================
# LOGIN
# ======================================================
def login():
    st.sidebar.title("🔐 Connexion")
    user = st.sidebar.text_input("Utilisateur")
    password = st.sidebar.text_input("Mot de passe", type="password")

    st.markdown(
        """
        <div style="margin-top: 60px; text-align:center;">
            <img src="https://cdn-icons-png.flaticon.com/512/3135/3135670.png" style="width:120px;">
            <h2 style="margin: 8px 0 0 0;">Intelligent Job Finder</h2>
            <div class="small-muted">By Idriss EL GAZRI & Yassine CHETOUANI</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.sidebar.button("Se connecter"):
        if user == "admin" and password == "1234":
            st.session_state["logged"] = True
            st.sidebar.success("Connexion réussie")
            time.sleep(0.4)
            st.rerun()
        else:
            st.sidebar.error("Identifiants incorrects")


if "logged" not in st.session_state:
    st.session_state["logged"] = False

if not st.session_state["logged"]:
    login()
    st.stop()


# ======================================================
# DB
# ======================================================
client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
collection = db[MONGO_COLLECTION]


def load_data() -> pd.DataFrame:
    try:
        data = list(collection.find({}, {"_id": 0}))
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Erreur lors de la lecture MongoDB : {e}")
        return pd.DataFrame()


# ======================================================
# AIRFLOW HELPERS
# ======================================================
def airflow_headers():
    return {"Content-Type": "application/json"}


def airflow_auth():
    return (AIRFLOW_USER, AIRFLOW_PASSWORD)


def airflow_get(path: str, params=None, timeout=10):
    url = f"{AIRFLOW_API_URL.rstrip('/')}/{path.lstrip('/')}"
    r = requests.get(url, params=params, auth=airflow_auth(), headers=airflow_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json()


def airflow_post(path: str, payload=None, timeout=10):
    url = f"{AIRFLOW_API_URL.rstrip('/')}/{path.lstrip('/')}"
    r = requests.post(url, json=payload or {}, auth=airflow_auth(), headers=airflow_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json()


def trigger_dag(dag_id: str):
    # Airflow 2 REST: POST /dags/{dag_id}/dagRuns
    # payload may include conf and dag_run_id
    payload = {}  # keep simple
    return airflow_post(f"/dags/{dag_id}/dagRuns", payload=payload, timeout=15)


def list_recent_dagruns(dag_id: str, limit: int = 5):
    # GET /dags/{dag_id}/dagRuns?order_by=-execution_date&limit=5
    return airflow_get(f"/dags/{dag_id}/dagRuns", params={"order_by": "-execution_date", "limit": limit}, timeout=10)


def get_task_instances(dag_id: str, dag_run_id: str):
    # GET /dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances
    return airflow_get(f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances", timeout=10)


def badge_html(state: str) -> str:
    s = (state or "").lower()
    if s == "running":
        cls = "badge-running"
    elif s in ("success", "completed"):
        cls = "badge-success"
    elif s in ("failed",):
        cls = "badge-failed"
    elif s in ("queued", "scheduled"):
        cls = "badge-queued"
    else:
        cls = "badge-other"
    label = state or "unknown"
    return f'<span class="badge {cls}">{label}</span>'


# ======================================================
# NAV
# ======================================================
st.sidebar.title("⚙️ Navigation")
page = st.sidebar.radio(
    "Aller à :",
    ["🏠 Dashboard", "📂 Analyse CV", "⚡ Pipeline Airflow", "📄 Offres"],
)
st.sidebar.markdown("---")
st.sidebar.info("Intelligent Job Finder – Yassine & Idriss")


# ======================================================
# PAGES
# ======================================================
if page == "🏠 Dashboard":
    st.title("📊 Dashboard – Système ETL d'offres d'emploi")

    df = load_data()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Offres", len(df))
    col2.metric("Sources", df["source"].nunique() if len(df) else 0)
    col3.metric(
        "Villes",
        df["location"].apply(lambda x: x.get("city") if isinstance(x, dict) else None).nunique()
        if len(df) and "location" in df.columns
        else 0,
    )
    col4.metric("Dernière Maj", datetime.now().strftime("%d/%m/%Y %H:%M"))

    st.markdown("### 🔌 Statut des services")
    col_status_api, col_status_db = st.columns(2)

    with col_status_api:
        try:
            r = requests.get(f"{API_URL}/health", timeout=3)
            if r.status_code == 200:
                st.success("API FastAPI : ✅ OK")
            else:
                st.warning(f"API FastAPI : ⚠️ Code {r.status_code}")
        except Exception as e:
            st.error(f"API FastAPI : ❌ Injoignable ({e})")

    with col_status_db:
        try:
            _ = collection.find_one()
            st.success("MongoDB : ✅ OK")
        except Exception as e:
            st.error(f"MongoDB : ❌ Erreur ({e})")

    st.markdown("### 📈 Statistiques générales")
    if len(df):
        colA, colB = st.columns(2)
        with colA:
            st.subheader("📍 Top 10 villes")
            if "location" in df.columns:
                cities = df["location"].apply(lambda x: x.get("city") if isinstance(x, dict) else None)
                st.bar_chart(cities.value_counts().head(10))
            else:
                st.info("Pas de colonne 'location' exploitable.")
        with colB:
            st.subheader("🧷 Répartition par source")
            st.bar_chart(df["source"].value_counts())
    else:
        st.info("Aucune data dans MongoDB.")


elif page == "📂 Analyse CV":
    st.title("📂 Analyse de CV")

    # ✅ name state (default empty, not "Enter Your Name")
    if "full_name" not in st.session_state:
        st.session_state["full_name"] = ""

    full_name_input = st.text_input(
        "Nom complet",
        value=st.session_state["full_name"],
        placeholder="(Auto) Rempli depuis le CV après analyse — ou tape ton nom ici",
    )

    uploaded_file = st.file_uploader("Upload votre CV (PDF)", type=["pdf"])

    if uploaded_file is not None:
        pdf_bytes = uploaded_file.read()
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page_pdf in pdf:
            text += page_pdf.get_text()

        st.subheader("📝 Texte brut extrait")
        st.text_area("Contenu", text, height=250)

        st.markdown("---")
        st.subheader("🤖 Analyse via API Resume Analyzer")

        if st.button("🚀 Lancer l'analyse IA"):
            try:
                with st.spinner("Analyse du CV en cours..."):
                    files = {"file": ("cv.pdf", pdf_bytes, "application/pdf")}

                    # ✅ Only send full_name if user typed something useful
                    data = {}
                    if full_name_input and full_name_input.strip():
                        fn = full_name_input.strip()
                        if fn.lower() not in {"enter your name", "your name", "name"}:
                            data["full_name"] = fn

                    response = requests.post(
                        f"{API_URL}/upload_cv",
                        files=files,
                        data=data,
                        timeout=180,
                    )

                if response.status_code != 200:
                    st.error(f"Erreur API ({response.status_code}) : {response.text}")
                else:
                    result = response.json()
                    candidate = result.get("candidate") or {}
                    matches = result.get("matches") or []

                    extracted_name = (candidate.get("full_name") or "").strip()
                    if (not full_name_input.strip()) and extracted_name:
                        st.session_state["full_name"] = extracted_name

                    st.caption(f"{len(matches)} offres reçues de l'API")

                    st.markdown("### 👤 Profil candidat")
                    colA, colB = st.columns(2)
                    with colA:
                        st.write("**Nom complet :**", candidate.get("full_name", "N/A"))
                        st.write("**Résumé :**", candidate.get("summary", "N/A"))
                    with colB:
                        st.write("**Skills :**")
                        skills = candidate.get("skills") or []
                        st.write(", ".join(skills) if skills else "N/A")

                        st.write("**Langues :**")
                        langs = candidate.get("languages") or []
                        st.write(", ".join(langs) if langs else "N/A")

                    st.markdown("### 🎯 Offres recommandées")
                    if not matches:
                        st.info("Aucune offre recommandée retournée par l'API.")
                    else:
                        for i, job in enumerate(matches, start=1):
                            title = job.get("title", "Titre inconnu")
                            company = job.get("company", "Entreprise inconnue")
                            score = job.get("score") or job.get("match_score")
                            url = job.get("url") or job.get("link")
                            location = job.get("location") or job.get("city")

                            if isinstance(location, dict):
                                loc_parts = []
                                if location.get("city"):
                                    loc_parts.append(location["city"])
                                if location.get("country"):
                                    loc_parts.append(location["country"])
                                if location.get("remote"):
                                    loc_parts.append(f"remote={location['remote']}")
                                location = ", ".join(loc_parts) or None

                            header = f"{i}. {title} – {company}"
                            with st.expander(header):
                                if location:
                                    st.write(f"📍 {location}")

                                if score is not None:
                                    try:
                                        pct = float(score) * 100 if float(score) <= 1 else float(score)
                                        st.write(f"⭐ Score de matching : {pct:.1f} %")
                                    except Exception:
                                        st.write(f"⭐ Score de matching : {score}")

                                desc = job.get("description_text") or job.get("description") or ""
                                if desc:
                                    st.write(desc[:800] + ("..." if len(desc) > 800 else ""))

                                if url:
                                    st.markdown(f"[🔗 Voir l'offre]({url})")

            except Exception as e:
                st.error(f"Erreur lors de l'appel à l'API : {e}")


elif page == "⚡ Pipeline Airflow":
    st.title("⚡ Lancer le pipeline Airflow (1 bouton) + suivi live")
    st.caption(f"DAG: {DAG_ID} | Airflow API: {AIRFLOW_API_URL}")

    # One button only
    if st.button("🚀 Lancer le pipeline (Airflow DAG)"):
        try:
            out = trigger_dag(DAG_ID)
            st.success("DAG déclenché ✅")
            st.json(out)
        except Exception as e:
            st.error(f"Impossible de déclencher le DAG: {e}")

    st.markdown("---")
    st.subheader("📡 Suivi du DAG (live)")
    st.caption(f"Auto-refresh: {AUTO_REFRESH_SECONDS}s")

    placeholder = st.empty()

    # Auto-refresh loop (fixed 5s). This keeps the page “live”.
    # Streamlit reruns the script from top. We emulate live with sleep + rerun.
    # We keep it lightweight: show only latest run.
    try:
        runs = list_recent_dagruns(DAG_ID, limit=1).get("dag_runs", [])
        if not runs:
            placeholder.info("Aucun DAG run trouvé.")
        else:
            run = runs[0]
            dag_run_id = run.get("dag_run_id")
            state = run.get("state")
            start_date = run.get("start_date")
            end_date = run.get("end_date")

            with placeholder.container():
                st.markdown(
                    f"**Dernier run:** `{dag_run_id}`  &nbsp; {badge_html(state)}",
                    unsafe_allow_html=True,
                )
                st.write(f"start: {start_date} | end: {end_date}")

                # Task instances table
                ti = get_task_instances(DAG_ID, dag_run_id).get("task_instances", [])
                if ti:
                    df_ti = pd.DataFrame(
                        [
                            {
                                "task_id": x.get("task_id"),
                                "state": x.get("state"),
                                "try_number": x.get("try_number"),
                                "start_date": x.get("start_date"),
                                "end_date": x.get("end_date"),
                            }
                            for x in ti
                        ]
                    )
                    st.dataframe(df_ti, use_container_width=True)
                else:
                    st.info("Aucune task instance pour ce run.")

    except Exception as e:
        placeholder.error(f"Erreur Airflow API: {e}")

    # Fixed refresh (no slider, no checkbox)
    time.sleep(AUTO_REFRESH_SECONDS)
    st.rerun()


elif page == "📄 Offres":
    st.title("📄 Offres d'emploi – Base MongoDB")
    df = load_data()

    if not len(df):
        st.warning("Aucune donnée trouvée.")
        st.stop()

    if "location" in df.columns:
        df["city"] = df["location"].apply(lambda x: x.get("city") if isinstance(x, dict) else None)

    with st.expander("🎛️ Filtres avancés"):
        col1, col2, col3 = st.columns(3)

        source = col1.selectbox("Source", ["Toutes"] + sorted(df["source"].unique()))
        city_values = sorted(df["city"].dropna().unique()) if "city" in df.columns else []
        city = col2.selectbox("Ville", ["Toutes"] + city_values)
        keyword = col3.text_input("Mot-clé (titre / description)")

        if source != "Toutes":
            df = df[df["source"] == source]
        if city != "Toutes" and "city" in df.columns:
            df = df[df["city"] == city]
        if keyword:
            df = df[df.apply(lambda r: keyword.lower() in str(r).lower(), axis=1)]

    st.dataframe(df, use_container_width=True)

    st.download_button(
        label="📥 Télécharger en CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="offres.csv",
        mime="text/csv",
    )
