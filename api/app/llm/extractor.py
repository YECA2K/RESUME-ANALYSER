import requests
import json
import os

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "ollama")
OLLAMA_URL = f"http://{OLLAMA_HOST}:11434/api/generate"

def extract_profile_from_text(text: str):
    """
    Envoie le texte brut du CV au modèle Llama3.2:3b pour extraire les informations structurées.
    Si le modèle échoue ou dépasse le délai, un fallback sur Phi3:latest est exécuté.
    """

    def query_model(model_name):
        prompt = f"""
Tu es un assistant expert en recrutement. 
Analyse le CV suivant et renvoie les informations sous format JSON structuré avec les clés suivantes :
- skills_detected : liste de compétences techniques (Python, SQL, AWS, etc.)
- languages : langues parlées et niveau
- experiences : liste d'expériences professionnelles avec "title", "company", "years"
- education : diplômes avec "degree", "school", "year" si possible
- summary : résumé professionnel court

CV :
{text}

Réponds UNIQUEMENT avec un JSON valide.
        """

        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False
        }

        try:
            r = requests.post(OLLAMA_URL, json=payload, timeout=300)
            r.raise_for_status()
            data = r.json().get("response", "").strip()
            return json.loads(data)
        except Exception as e:
            print(f"❌ Erreur avec le modèle {model_name}: {e}")
            return None

    # On essaie d’abord Llama3.2:3b
    data = query_model("llama3.2:3b")
    if not data:
        print("⚠️ Fallback vers Phi3:latest ...")
        data = query_model("phi3:latest")

    # Valeurs par défaut si le modèle ne renvoie rien
    if not data:
        data = {
            "skills_detected": [],
            "languages": [],
            "experiences": [],
            "education": [],
            "summary": ""
        }

    return data
