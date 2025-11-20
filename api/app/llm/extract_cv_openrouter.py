import os
import requests
import json

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL = "qwen/qwen-2.5-7b-instruct"

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERRER", "http://resume-analyser"),
    "X-Title": os.getenv("OPENROUTER_X_TITLE", "resume-analyser")
}

def extract_cv_data(text: str):
    prompt = f"""
Extract ONLY valid JSON with this structure:

{{
  "full_name": "",
  "skills": [],
  "languages": [{{"name": "", "level": ""}}],
  "experiences": [{{"title": "", "company": "", "years": ""}}],
  "education": [{{"degree": "", "school": "", "year": ""}}],
  "summary": ""
}}

Do NOT add explanations. Do NOT add comments.
Return JUST the JSON.

CV TEXT:
{text}
"""

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500
    }

    response = requests.post(f"{BASE_URL}/chat/completions", headers=HEADERS, json=payload)
    data = response.json()

    # ---------------- DEBUG -----------------
    print("\n\n================== RAW LLM OUTPUT ==================\n")
    print(json.dumps(data, indent=2))
    print("\n===================================================\n")
    # -------------------------------------------

    # extract raw text from LLM
    raw = data["choices"][0]["message"]["content"]

    # Try parsing normally
    try:
        return json.loads(raw)
    except:
        # Attempt to extract JSON only
        start = raw.find("{")
        end = raw.rfind("}") + 1
        cleaned = raw[start:end]
        return json.loads(cleaned)
