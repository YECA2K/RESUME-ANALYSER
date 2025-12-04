import json
from .openrouter_client import call_openrouter

MODEL = "qwen/qwen-2.5-7b-instruct"


def extract_cv_data(text: str) -> dict:
    """
    Extract a structured CV from raw text using OpenRouter.
    Deterministic + robust JSON parsing.
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
        temperature=0.0,
        top_p=1.0,
        extra={
            # helps keep output consistent
            "frequency_penalty": 0,
            "presence_penalty": 0,
        },
    )

    def _empty():
        return {
            "full_name": "",
            "summary": "",
            "skills": [],
            "languages": [],
            "experiences": [],
            "education": [],
        }

    # Direct JSON parse
    try:
        data = json.loads(raw)
    except Exception:
        # Rescue: extract first {...} block
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return _empty()
        try:
            data = json.loads(raw[start:end])
        except Exception:
            return _empty()

    if not isinstance(data, dict):
        return _empty()

    base = _empty()
    for k in base.keys():
        if k in data:
            base[k] = data[k]

    # type safety
    if not isinstance(base["skills"], list):
        base["skills"] = []
    if not isinstance(base["languages"], list):
        base["languages"] = []
    if not isinstance(base["experiences"], list):
        base["experiences"] = []
    if not isinstance(base["education"], list):
        base["education"] = []

    # ensure strings
    base["full_name"] = base["full_name"] if isinstance(base["full_name"], str) else ""
    base["summary"] = base["summary"] if isinstance(base["summary"], str) else ""

    return base
