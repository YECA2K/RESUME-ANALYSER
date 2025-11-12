import requests
import json
import os
import re
from textwrap import wrap
from datetime import datetime

# ==============================
#  CONFIGURATION
# ==============================

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "ollama")
OLLAMA_URL = f"http://{OLLAMA_HOST}:11434/api/generate"

DATA_LAKE = os.getenv("DATA_LAKE_ROOT", "/app/ops/datalake")
LOG_DIR = os.path.join(DATA_LAKE, "raw", "llm_outputs")
os.makedirs(LOG_DIR, exist_ok=True)


# ==============================
#  TEXT PREPROCESSING
# ==============================

def clean_cv_text(raw_text: str) -> str:
    """
    Clean raw PDF text before sending to the LLM.
    Removes layout noise, multiple spaces, bullet points, and common CV headers.
    """
    text = re.sub(r'\s+', ' ', raw_text)
    text = re.sub(r'•', '-', text)
    text = re.sub(r'(\n|\r)+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'(Curriculum Vitae|Resume|CV)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[^A-Za-zÀ-ÖØ-öø-ÿ0-9.,;:!?@()\-+/&%\'" ]', '', text)
    return text.strip()


def chunk_text(text: str, max_chars: int = 2500):
    """
    Split long CVs into smaller chunks to prevent context overflow.
    """
    return wrap(text, max_chars)


# ==============================
#  FALLBACK LOGIC
# ==============================

def fallback_skill_extraction(text: str, llm_skills: list) -> list:
    """
    Lightweight regex-based skill extraction to recover missed ones.
    """
    known_skills = [
        "Python", "SQL", "AWS", "Docker", "Airflow", "MongoDB", "PostgreSQL",
        "FastAPI", "Java", "C++", "Spark", "Hadoop", "Kubernetes", "TensorFlow",
        "PyTorch", "Pandas", "NumPy", "Excel", "Linux", "Git", "ETL"
    ]
    detected = [s for s in known_skills if re.search(rf"\b{s}\b", text, re.I)]
    return sorted(set(llm_skills + detected))


# ==============================
#  LLM CALL FUNCTION
# ==============================

def query_model(model_name: str, prompt: str):
    """
    Send the prompt to the Ollama model and return parsed JSON.
    If JSON parsing fails, save raw output to datalake for inspection.
    """
    payload = {"model": model_name, "prompt": prompt, "stream": False}

    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=180)
        r.raise_for_status()
        raw_response = r.json().get("response", "").strip()

        # Log raw model output for debugging
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        with open(os.path.join(LOG_DIR, f"{ts}_{model_name}.txt"), "w", encoding="utf-8") as f:
            f.write(raw_response)

        data = json.loads(raw_response)
        assert isinstance(data, dict)
        return data
    except Exception as e:
        print(f"❌ Erreur modèle {model_name}: {e}")
        return None


# ==============================
#  MAIN EXTRACTION FUNCTION
# ==============================

def extract_profile_from_text(text: str) -> dict:
    """
    Extract structured data from CV text using Llama3.2:3b (or Phi3 fallback).
    Performs chunking, cleaning, JSON validation, and skill recovery.
    """
    text = clean_cv_text(text)
    chunks = chunk_text(text, max_chars=2500)

    combined = {
        "skills": [],
        "languages": [],
        "experiences": [],
        "education": [],
        "summary": ""
    }

    for i, chunk in enumerate(chunks):
        print(f"🧩 Traitement du chunk {i+1}/{len(chunks)}...")

        prompt = f"""
Tu es un assistant expert en recrutement.
Analyse le texte suivant d’un CV et renvoie UNIQUEMENT un JSON structuré au format suivant :

{{
  "skills": ["Python", "SQL", "AWS", ...],
  "languages": [
    {{"name": "English", "level": "Fluent"}},
    {{"name": "French", "level": "Intermediate"}}
  ],
  "experiences": [
    {{"title": "Data Engineer", "company": "Capgemini", "years": "2021–2024"}},
    {{"title": "Data Analyst", "company": "BNP Paribas", "years": "2019–2021"}}
  ],
  "education": [
    {{"degree": "Master en Data Science", "school": "ESI Alger", "year": "2021"}}
  ],
  "summary": "Court résumé professionnel résumant le parcours du candidat."
}}

⚠️ IMPORTANT :
- Renseigne toujours un champ, même vide (par exemple [] ou "").
- N’ajoute aucun texte explicatif hors du JSON.
- Si certaines informations ne sont pas présentes, laisse des listes vides.

CV :
{chunk}
        """

        # Try Phi3 first (better JSON structuring)
        data = query_model("phi3:latest", prompt)

        # Fallback to Llama3.2 if Phi3 fails
        if not data:
            print("⚠️ Fallback vers llama3.2:3b ...")
            data = query_model("llama3.2:3b", prompt)

        if not data:
            continue

        # Merge chunk results
        for key in combined:
            if isinstance(data.get(key), list):
                combined[key].extend(data[key])
            elif isinstance(data.get(key), str):
                combined[key] += " " + data[key]

    # Deduplicate and cleanup
    combined["skills"] = fallback_skill_extraction(text, combined.get("skills", []))
    combined["skills"] = sorted(set(combined["skills"]))

    # Clean up lists (avoid empty strings)
    for key in ["languages", "experiences", "education"]:
        combined[key] = [x for x in combined[key] if x]

    combined["summary"] = combined["summary"].strip()

    return combined
