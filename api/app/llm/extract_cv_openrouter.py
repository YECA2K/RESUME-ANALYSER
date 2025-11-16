import os
import requests

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL = "google/gemini-flash-1.5"  # fast + free

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERRER", "http://resume-analyser"),
    "X-Title": os.getenv("OPENROUTER_X_TITLE", "resume-analyser")
}


def extract_cv_data(text: str):
    prompt = f"""
You are an ATS resume parser. Extract the CV into this EXACT JSON schema:

{{
  "full_name": "",
  "skills": [],
  "languages": [{{"name": "", "level": ""}}],
  "experiences": [{{"title": "", "company": "", "years": ""}}],
  "education": [{{"degree": "", "school": "", "year": ""}}],
  "summary": ""
}}

Return ONLY JSON.
CV TEXT:
{text}
"""

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    r = requests.post(f"{BASE_URL}/chat/completions",
                      headers=HEADERS, json=payload, timeout=40)

    out = r.json()
    raw = out["choices"][0]["message"]["content"]

    # Try to parse JSON
    import json
    try:
        return json.loads(raw)
    except:
        # cleanup
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
