import os
import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from pymongo import MongoClient
import fitz  # PyMuPDF


# -------------------------------------------------------
# SETTINGS
# -------------------------------------------------------
st.set_page_config(
    page_title="JobScraper ETL",
    page_icon="🧠",
    layout="wide",
)

API_URL = os.getenv("API_URL", "http://localhost:8000")

# -------------------------------------------------------
# CSS & DARK MODE
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
    padding: 0.5em 1em;
}
.metric { font-size: 24px !important; font-weight: bold !important; }
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
    padding: 0.5em 1em;
}}
.metric {{ font-size: 24px !important; font-weight: bold !important; }}
.stDataFrame div.row_widget {{ color: {text_color}; }}
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

    if st.sidebar.button("Se connecter"):
        if user == "admin" and password == "1234":
            st.session_state["logged"] = True
            st.sidebar.success("Connexion réussie")
            time.sleep(0.5)
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
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB = os.getenv("MONGO_DB", "matcher")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "jobs")

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


def run_scraping():
    time.sleep(1)
    return "Scraping lancé avec succès ✔️"


def run_etl():
    time.sleep(1)
    return "Pipeline ETL exécuté ✔️"


# -------------------------------------------------------
# SIDEBAR NAV
# -------------------------------------------------------
st.sidebar.title("⚙️ Navigation")
page = st.sidebar.radio(
    "Aller à :",
    ["🏠 Dashboard", "📂 Analyse CV", "📜 Logs Pipeline", "📄 Offres"],
)
st.sidebar.markdown("---")
st.sidebar.info("Projet JobScraper ETL – Yassine & Idriss")

# -------------------------------------------------------
# PAGES
# -------------------------------------------------------

# ---------------------- DASHBOARD ----------------------
if page == "🏠 Dashboard":
    st.title("📊 Dashboard – Système ETL d'offres d'emploi")

    df = load_data()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Offres", len(df))
    col2.metric("Sources", df["source"].nunique() if len(df) else 0)
    col3.metric(
        "Villes",
        df["location"]
        .apply(lambda x: x.get("city") if isinstance(x, dict) else None)
        .nunique()
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
                cities = df["location"].apply(
                    lambda x: x.get("city") if isinstance(x, dict) else None
                )
                st.bar_chart(cities.value_counts().head(10))
            else:
                st.info("Pas de colonne 'location' exploitable.")

        with colB:
            st.subheader("🧷 Répartition par source")
            st.bar_chart(df["source"].value_counts())
    else:
        st.info("Aucune data dans MongoDB.")

    st.markdown("---")
    st.markdown("### ⚡ Actions rapides")

    colX, colY = st.columns(2)
    if colX.button("🚀 Lancer Scraping"):
        st.success(run_scraping())

    if colY.button("🔁 Exécuter Pipeline ETL"):
        st.success(run_etl())

# ---------------------- ANALYSE CV ----------------------
elif page == "📂 Analyse CV":
    st.title("📂 Analyse de CV")

    full_name = st.text_input("Nom complet", value="Yassine Chetouani")
    uploaded_file = st.file_uploader("Upload votre CV (PDF)", type=["pdf"])

    if uploaded_file is not None:
        pdf_bytes = uploaded_file.read()
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page_pdf in pdf:
            text += page_pdf.get_text()

        st.subheader("📝 Texte brut extrait du CV")
        st.text_area("Contenu du CV", text, height=250)

        st.markdown("---")
        st.subheader("🤖 Analyse complète via l'API Resume Analyzer")

        if st.button("🚀 Lancer l'analyse IA"):
            try:
                with st.spinner("Analyse du CV en cours..."):

                    files = {
                        "file": ("cv.pdf", pdf_bytes, "application/pdf"),
                    }
                    data = {"full_name": full_name}

                    response = requests.post(
                        f"{API_URL}/upload_cv",
                        files=files,
                        data=data,
                        timeout=180,
                    )

                if response.status_code != 200:
                    st.error(
                        f"Erreur API ({response.status_code}) : {response.text}"
                    )
                else:
                    result = response.json()

                    candidate = result.get("candidate") or {}
                    matches = result.get("matches") or []

                    # DEBUG (optionnel) : afficher combien de matches
                    st.caption(f"{len(matches)} offres reçues de l'API")

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

                    st.markdown("### 🎯 Offres recommandées")

                    if not matches:
                        st.info(
                            "Aucune offre recommandée retournée par l'API (ou toutes filtrées)."
                        )
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
                                        pct = (
                                            float(score) * 100
                                            if float(score) <= 1
                                            else float(score)
                                        )
                                        st.write(
                                            f"⭐ Score de matching : {pct:.1f} %"
                                        )
                                    except Exception:
                                        st.write(
                                            f"⭐ Score de matching : {score}"
                                        )

                                desc = (
                                    job.get("description_text")
                                    or job.get("description")
                                    or ""
                                )
                                if desc:
                                    st.write(
                                        desc[:800]
                                        + ("..." if len(desc) > 800 else "")
                                    )

                                if url:
                                    st.markdown(f"[🔗 Voir l'offre]({url})")

            except Exception as e:
                st.error(f"Erreur lors de l'appel à l'API : {e}")

# ---------------------- LOGS ----------------------
elif page == "📜 Logs Pipeline":
    st.title("📜 Logs & Suivi du Pipeline ETL")
    st.subheader("Dernières exécutions")
    st.info("Fonctionnement Airflow à connecter ici.")
    st.text_area(
        "Logs (exemple)",
        "Scraping Indeed → OK\nTransformation → OK\nLoad MongoDB → OK",
    )

# ---------------------- OFFRES ----------------------
elif page == "📄 Offres":
    st.title("📄 Offres d'emploi – Base MongoDB")
    df = load_data()

    if not len(df):
        st.warning("Aucune donnée trouvée.")
        st.stop()

    if "location" in df.columns:
        df["city"] = df["location"].apply(
            lambda x: x.get("city") if isinstance(x, dict) else None
        )

    with st.expander("🎛️ Filtres avancés"):
        col1, col2, col3 = st.columns(3)
        source = col1.selectbox("Source", ["Toutes"] + sorted(df["source"].unique()))
        city_values = (
            sorted(df["city"].dropna().unique()) if "city" in df.columns else []
        )
        city = col2.selectbox("Ville", ["Toutes"] + city_values)
        keyword = col3.text_input("Mot-clé (titre / description)")

        if source != "Toutes":
            df = df[df["source"] == source]
        if city != "Toutes" and "city" in df.columns:
            df = df[df["city"] == city]
        if keyword:
            df = df[
                df.apply(
                    lambda r: keyword.lower() in str(r).lower(),
                    axis=1,
                )
            ]

    st.dataframe(df, use_container_width=True)

    st.download_button(
        label="📥 Télécharger en CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="offres.csv",
        mime="text/csv",
    )
