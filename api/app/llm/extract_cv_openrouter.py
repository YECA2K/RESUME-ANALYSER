import json
from .openrouter_client import call_openrouter

MODEL = "qwen/qwen-2.5-7b-instruct"


def extract_cv_data(text: str) -> dict:
    """
    Utilise OpenRouter pour extraire un CV structuré depuis du texte brut.
    On force un schéma JSON très précis.
    """

    prompt = f"""
Tu es un extracteur de CV très strict.

À partir du texte suivant, retourne UNIQUEMENT un JSON valide avec ce schéma EXACT :

{{
  "full_name": "string",
  "summary": "string",
  "skills": ["string", "..."],
  "languages": ["string", "..."],
  "experiences": [
    {{
      "title": "string",
      "company": "string",
      "period": "string",
      "summary": "string"
    }}
  ],
  "education": [
    {{
      "title": "string",
      "institution": "string",
      "period": "string"
    }}
  ]
}}

Règles IMPORTANTES :
- Retourne UNIQUEMENT le JSON, sans texte avant ou après.
- Si une info est inconnue, mets une chaîne vide "" ou une liste vide [].
- "summary" doit être un paragraphe court (2–4 phrases) résumant le profil.
- "skills" doit contenir des compétences techniques (langages, outils, cloud, etc.).
- "languages" contient les langues parlées avec niveau.
- "experiences" : max 6 expériences, les plus récentes, avec un petit résumé.
- "education" : diplômes principaux.

TEXTE DU CV :
{text}
"""

    raw = call_openrouter(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1800,
    )

    # Parsing JSON robuste
    def _empty():
        return {
            "full_name": "",
            "summary": "",
            "skills": [],
            "languages": [],
            "experiences": [],
            "education": [],
        }

    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return _empty()
        # s'assurer des clés
        base = _empty()
        base.update({k: v for k, v in data.items() if k in base})
        return base
    except Exception:
        # tentative de rescue quand le modèle met du texte autour
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(raw[start:end])
                base = _empty()
                base.update({k: v for k, v in data.items() if k in base})
                return base
        except Exception:
            return _empty()
