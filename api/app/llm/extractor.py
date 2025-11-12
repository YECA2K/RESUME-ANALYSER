import requests
import json
import os
import re
from textwrap import wrap

# ==============================
#  CONFIGURATION
# ==============================

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "ollama")
OLLAMA_URL = f"http://{OLLAMA_HOST}:11434/api/generate"


# ==============================
#  TEXT PREPROCESSING
# ==============================

def clean_cv_text(raw_text: str) -> str:
    """
    Clean raw PDF text before sending to the LLM.
    Removes layout noise, multiple spaces, and non-alphanumeric characters.
    """
    text = re.sub(r'\s+', ' ', raw_text)
    text = re.sub(r'[^A-Za-zÀ-ÖØ-öø-ÿ0-9.,;:!?@()\-+/&%\'" ]', '', text)
    text = re.sub(r'(Curriculum Vitae|Resume|CV)', '', text, flags=re.IGNORECASE)
    return text.strip()


def chunk_text(text: str, max_chars: int = 4000):
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
    """
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False
    }

    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=180)
        r.raise_for_status()
        raw_response = r.json().get("response", "").strip()
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
    Extract structured data from CV text using Llama3.2:3b, with fallback to Phi3.
    Performs chunking, cleaning, and skill recovery.
    """
    text = clean_cv_text(text)
    chunks = chunk_text(text)

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
Analyse le CV ci-dessous et renvoie UNIQUEMENT un JSON structuré selon ce schéma :

{{
  "skills": ["Python", "SQL", "AWS", ...],
  "languages": [{{"name": "English", "level": "Fluent"}}, ...],
  "experiences": [
    {{"title": "Data Engineer", "company": "Capgemini", "years": "2021–2024"}},
    ...
  ],
  "education": [
    {{"degree": "Master en Data Science", "school": "ESI", "year": "2021"}},
    ...
  ],
  "summary": "Bref résumé professionnel"
}}

⚠️ Ne renvoie rien d'autre que ce JSON.
CV :
{chunk}
        """

        # Try main model
        data = query_model("llama3.2:3b", prompt)

        # Fallback
        if not data:
            print("⚠️ Fallback vers Phi3:latest ...")
            data = query_model("phi3:latest", prompt)

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
