import os
import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from pymongo import MongoClient
import fitz  # PyMuPDF

# Optional: autorefresh helper
try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None


# -------------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------------
st.set_page_config(
    page_title="Intelligent Job Finder",
    page_icon="🧠",
    layout="wide",
)

API_URL = os.getenv("API_URL", "http://localhost:8000")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB = os.getenv("MONGO_DB", "matcher")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "jobs")

AIRFLOW_API_URL = os.getenv("AIRFLOW_API_URL", "http://localhost:8080/api/v1").rstrip("/")
AIRFLOW_USER = os.getenv("AIRFLOW_USER", "admin")
AIRFLOW_PASSWORD = os.getenv("AIRFLOW_PASSWORD", "admin")

# DAG ID (change if your DAG name differs)
DAG_ID = os.getenv("AIRFLOW_DAG_ID", "jobs_jobspy_daily")


# -------------------------------------------------------
# GLOBAL CSS + DARK MODE
# -------------------------------------------------------
st.markdown(
    """
<style>
.main { background-color: #f7f9fc; color: #1b1b1b; }
.sidebar .sidebar-content { background-color: #eef2f7; }

.stButton>button {
    border-radius: 10px;
    font-weight: bold;
    background-color: #4B77BE;
    color: white;
    padding: 0.55em 1.1em;
}

.metric {
    font-size: 24px !important;
    font-weight: bold !important;
}

.small-muted { font-size: 12px; opacity: 0.7; }
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
    border-radius: 10px;
    font-weight: bold;
    background-color: {btn_bg};
    color: {btn_color};
    padding: 0.55em 1.1em;
}}
</style>
""",
    unsafe_allow_html=True,
)

# -------------------------------------------------------
# LOGIN
# -------------------------------------------------------
def login():
    st.sidebar.title("🔐 Connexion")
    user = st.sidebar.text_input("Utilisateur")
    password = st.sidebar.text_input("Mot de passe", type="password")

    st.markdown(
        """
        <div style="margin-top:60px;text-align:center;opacity:0.95">
            <img src="https://cdn-icons-png.flaticon.com/512/3135/3135670.png" width="120">
            <h2 style="margin:10px 0 0 0;">Intelligent Job Finder</h2>
            <div class="small-muted">By Idriss EL GAZRI & Yassine CHETOUANI</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.sidebar.button("Se connecter"):
        if user == "admin" and password == "1234":
            st.session_state["logged"] = True
            st.sidebar.success("Connexion réussie")
            time.sleep(0.3)
            st.rerun()
        else:
            st.sidebar.error("Identifiants incorrects")


if "logged" not in st.session_state:
    st.session_state["logged"] = False

if not st.session_state["logged"]:
    login()
    st.stop()


# -------------------------------------------------------
# DB CONNECTION
# -------------------------------------------------------
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


# -------------------------------------------------------
# AIRFLOW HELPERS
# -------------------------------------------------------
def airflow_request(method: str, path: str, **kwargs):
    url = f"{AIRFLOW_API_URL}{path}"
    auth = (AIRFLOW_USER, AIRFLOW_PASSWORD)
    headers = kwargs.pop("headers", {})
    headers.setdefault("Accept", "application/json")
    return requests.request(method, url, auth=auth, headers=headers, timeout=15, **kwargs)


def airflow_health() -> bool:
    try:
        r = airflow_request("GET", "/health")
        return r.status_code == 200
    except Exception:
        return False


def trigger_dag(dag_id: str) -> dict:
    payload = {"conf": {}}
    r = airflow_request("POST", f"/dags/{dag_id}/dagRuns", json=payload)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Airflow trigger error {r.status_code}: {r.text}")
    return r.json()


def list_dag_runs(dag_id: str, limit: int = 5) -> list[dict]:
    r = airflow_request("GET", f"/dags/{dag_id}/dagRuns", params={"order_by": "-execution_date", "limit": limit})
    if r.status_code != 200:
        raise RuntimeError(f"Airflow list dagRuns error {r.status_code}: {r.text}")
    data = r.json() or {}
    return data.get("dag_runs", []) or []


def get_task_instances(dag_id: str, dag_run_id: str) -> list[dict]:
    r = airflow_request("GET", f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances")
    if r.status_code != 200:
        raise RuntimeError(f"Airflow taskInstances error {r.status_code}: {r.text}")
    data = r.json() or {}
    return data.get("task_instances", []) or []


# -------------------------------------------------------
# SIDEBAR NAV
# -------------------------------------------------------
st.sidebar.title("⚙️ Navigation")
page = st.sidebar.radio("Aller à :", ["🏠 Dashboard", "📂 Analyse CV", "📄 Offres"])
st.sidebar.markdown("---")
st.sidebar.info("Intelligent Job Finder – Yassine & Idriss")


# -------------------------------------------------------
# PAGES
# -------------------------------------------------------
if page == "🏠 Dashboard":
    st.title("📊 Dashboard – Système ETL d'offres d'emploi")

    df = load_data()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Offres", len(df))
    col2.metric("Sources", df["source"].nunique() if len(df) and "source" in df.columns else 0)
    col3.metric(
        "Villes",
        df["location"].apply(lambda x: x.get("city") if isinstance(x, dict) else None).nunique()
        if len(df) and "location" in df.columns
        else 0,
    )
    col4.metric("Dernière Maj", datetime.now().strftime("%d/%m/%Y %H:%M"))

    st.markdown("### 🔌 Statut des services")

    col_status_api, col_status_db, col_status_airflow = st.columns(3)

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

    with col_status_airflow:
        if airflow_health():
            st.success("Airflow : ✅ OK")
        else:
            st.error("Airflow : ❌ Injoignable (API)")

    st.markdown("---")
    st.subheader("⚡ Lancer le pipeline Airflow (1 bouton) + suivi live")

    st.caption(f"DAG: `{DAG_ID}`  |  Airflow API: `{AIRFLOW_API_URL}`")

    colA, colB = st.columns([1, 2])
    with colA:
        if st.button("🚀 Lancer le pipeline (Airflow DAG)"):

            try:
                run = trigger_dag(DAG_ID)
                st.session_state["last_dag_run_id"] = run.get("dag_run_id")
                st.success(f"DAG déclenché ✅ (run_id={st.session_state['last_dag_run_id']})")
            except Exception as e:
                st.error(f"Erreur Airflow: {e}")

    with colB:
        st.markdown(
            "<div class='small-muted'>Le suivi se rafraîchit automatiquement toutes les 5 secondes (pas d’option utilisateur).</div>",
            unsafe_allow_html=True,
        )

    if st_autorefresh is not None:
        st_autorefresh(interval=5000, key="airflow_refresh")

    st.markdown("### 📡 Suivi du DAG (live)")

    try:
        runs = list_dag_runs(DAG_ID, limit=5)
        if not runs:
            st.info("Aucun dagRun trouvé pour ce DAG.")
        else:
            wanted = st.session_state.get("last_dag_run_id")
            selected = None
            if wanted:
                for r in runs:
                    if r.get("dag_run_id") == wanted:
                        selected = r
                        break
            if selected is None:
                selected = runs[0]

            run_id = selected.get("dag_run_id")
            st.write(f"**Run:** `{run_id}`  |  **state:** `{selected.get('state')}`")
            st.write(f"start: `{selected.get('start_date')}`  |  end: `{selected.get('end_date')}`")

            tis = get_task_instances(DAG_ID, run_id)
            if tis:
                rows = []
                for t in tis:
                    rows.append(
                        {
                            "task_id": t.get("task_id"),
                            "state": t.get("state"),
                            "try_number": t.get("try_number"),
                            "start_date": t.get("start_date"),
                            "end_date": t.get("end_date"),
                        }
                    )
                df_ti = pd.DataFrame(rows).sort_values(by=["state", "task_id"], ascending=[True, True])
                st.dataframe(df_ti, use_container_width=True)
            else:
                st.info("Aucune task instance pour ce run (pas encore démarré ?).")

    except Exception as e:
        st.error(f"Impossible de lire Airflow (API): {e}")

    st.markdown("---")
    st.markdown("### 📈 Statistiques générales")

    if len(df):
        colL, colR = st.columns(2)
        with colL:
            st.subheader("📍 Top 10 villes")
            if "location" in df.columns:
                cities = df["location"].apply(lambda x: x.get("city") if isinstance(x, dict) else None)
                st.bar_chart(cities.value_counts().head(10))
            else:
                st.info("Pas de colonne 'location' exploitable.")
        with colR:
            st.subheader("🧷 Répartition par source")
            if "source" in df.columns:
                st.bar_chart(df["source"].value_counts())
            else:
                st.info("Pas de colonne 'source' exploitable.")
    else:
        st.info("Aucune data dans MongoDB.")


elif page == "📂 Analyse CV":
    st.title("📂 Analyse de CV")

    uploaded_file = st.file_uploader("Upload votre CV (PDF)", type=["pdf"])

    if uploaded_file is None:
        st.info("Upload un PDF pour démarrer.")
        st.stop()

    pdf_bytes = uploaded_file.read()
    pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    for page_pdf in pdf:
        text += page_pdf.get_text()

    st.subheader("📝 Texte brut extrait du PDF")
    st.text_area("Contenu", text, height=220)

    if "full_name" not in st.session_state:
        st.session_state["full_name"] = ""

    st.subheader("👤 Nom complet")

    colN1, colN2 = st.columns([1, 2])

    with colN1:
        if st.button("🧠 Détecter le nom depuis le CV"):
            try:
                with st.spinner("Extraction du nom via l'API..."):
                    files = {"file": ("cv.pdf", pdf_bytes, "application/pdf")}
                    r = requests.post(f"{API_URL}/test_extract", files=files, timeout=120)

                if r.status_code != 200:
                    st.error(f"Erreur extraction ({r.status_code}) : {r.text}")
                else:
                    data = r.json() or {}
                    candidate = data.get("candidate") or data
                    st.session_state["full_name"] = candidate.get("full_name", "") or ""
                    if st.session_state["full_name"]:
                        st.success(f"Nom détecté: {st.session_state['full_name']}")
                    else:
                        st.warning("Nom non détecté.")
            except Exception as e:
                st.error(f"Erreur appel API extraction: {e}")

    with colN2:
        st.session_state["full_name"] = st.text_input(
            "Nom complet",
            value=st.session_state["full_name"],
            placeholder="Auto via bouton ou saisie manuelle",
        )

    st.markdown("---")
    st.subheader("🤖 Analyse complète via l'API Resume Analyzer")

    if st.button("🚀 Lancer l'analyse IA"):
        try:
            with st.spinner("Analyse du CV en cours..."):
                files = {"file": ("cv.pdf", pdf_bytes, "application/pdf")}
                data = {"full_name": st.session_state["full_name"]}

                response = requests.post(
                    f"{API_URL}/upload_cv",
                    files=files,
                    data=data,
                    timeout=180,
                )

            if response.status_code != 200:
                st.error(f"Erreur API ({response.status_code}) : {response.text}")
                st.stop()

            result = response.json() or {}
            status = result.get("status")
            candidate = result.get("candidate") or {}
            matches = result.get("matches") or []

            # ---------- handle backend statuses ----------
            if status == "ERROR":
                st.error(f"Backend ERROR: {result.get('detail')}")
                st.stop()

            st.markdown("### 👤 Profil candidat (normalisé)")
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

            if status == "NON_IT":
                threshold = result.get("threshold", 0.6)
                max_score = result.get("max_score", 0.0)
                pct_thresh = threshold * 100.0
                pct_max = max_score * 100.0

                st.markdown("### 🎯 Offres recommandées")
                st.info(
                    f"Votre CV a été détecté comme **profil non-IT / non-Data** par rapport à la base d'offres actuelle.\n\n"
                    f"- Score de matching maximum trouvé : **{pct_max:.1f} %**\n"
                    f"- Seuil minimum pour afficher des offres : **{pct_thresh:.1f} %**\n\n"
                    "Aucune offre n'est donc affichée. "
                    "Ajoutez des offres dans des domaines proches de votre profil (ex: restauration, service, retail) "
                    "pour obtenir des recommandations pertinentes."
                )
                st.stop()
            # ---------------------------------------------

            st.caption(f"{len(matches)} offres reçues de l'API")

            st.markdown("### 🎯 Offres recommandées")

            if not matches:
                st.info("Aucune offre recommandée retournée par l'API (ou toutes filtrées).")
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
                        if location.get("remote") is not None:
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
                            st.write(desc[:900] + ("..." if len(desc) > 900 else ""))

                        if url:
                            st.markdown(f"[🔗 Voir l'offre]({url})")

        except Exception as e:
            st.error(f"Erreur lors de l'appel à l'API : {e}")


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

        source_values = sorted(df["source"].dropna().unique()) if "source" in df.columns else []
        source = col1.selectbox("Source", ["Toutes"] + source_values)

        city_values = sorted(df["city"].dropna().unique()) if "city" in df.columns else []
        city = col2.selectbox("Ville", ["Toutes"] + city_values)

        keyword = col3.text_input("Mot-clé (titre / description)")

        if source != "Toutes" and "source" in df.columns:
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
