import os
import requests
import json

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

MODEL = os.getenv("MATCH_LLM_MODEL", "qwen/qwen-2.5-14b-instruct")

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERRER", "http://resume-analyser"),
    "X-Title": os.getenv("OPENROUTER_X_TITLE", "resume-analyser")
}


def score_candidate_against_job(cv, job):
    """
    LLM #2 → Score CV vs JOB using structured output
    """

    prompt = f"""
Evaluate how well this CV matches this JOB.
Return JSON ONLY:

{{
  "score": 0-100,
  "reason": ""
}}

CV:
{json.dumps(cv, indent=2)}

JOB:
{json.dumps(job, indent=2)}
"""

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}]
    }

    r = requests.post(
        f"{BASE_URL}/chat/completions",
        headers=HEADERS,
        json=payload,
        timeout=40
    )

    out = r.json()["choices"][0]["message"]["content"]

    try:
        return json.loads(out)
    except:
        start = out.find("{")
        end = out.rfind("}") + 1
        return json.loads(out[start:end])
