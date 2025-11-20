import os
import requests
import json

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL = "qwen/qwen-2.5-14b-instruct"  # FREE + strong reasoning


def call_llm(system_prompt: str, user_prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERRER", "http://resume-analyser"),
        "X-Title": os.getenv("OPENROUTER_X_TITLE", "resume-analyser"),
        "Content-Type": "application/json",
    }

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 700,
    }

    response = requests.post(
        f"{BASE_URL}/chat/completions",
        headers=headers,
        json=body,
        timeout=60,
    )

    data = response.json()

    # OpenRouter unified parsing
    if "choices" in data:
        msg = data["choices"][0]["message"]["content"]
        return msg

    if "response" in data:
        return data["response"]

    return str(data)


def match_candidate_to_jobs(candidate, jobs):
    """Rank jobs by LLM according to the candidate profile."""

    if not jobs:
        return []

    # ---- NORMALISATION (important !!) ----
    skills = getattr(candidate, "skills_detected", None)
    if skills is None:
        skills = getattr(candidate, "skills", [])
    summary = getattr(candidate, "summary", "")
    experiences = getattr(candidate, "experiences", [])

    # ---- CONSTRUCT LLM INPUT ----
    jobs_text = "\n\n".join(
        [
            f"JOB {i+1}:\nTitle: {j['title']}\nCompany: {j.get('company')}\nDescription: {j.get('description_text')}"
            for i, j in enumerate(jobs)
        ]
    )

    user_prompt = f"""
Candidate:
Name: {candidate.full_name}
Skills: {skills}
Summary: {summary}
Experiences: {experiences}

Jobs to evaluate:
{jobs_text}

Return ONLY a JSON list of max 5 objects:
[
  {{"job_index": 1, "score": 0.87}},
  ...
]
"""

    system_prompt = "You are a ranking engine. Compare candidate skills with job descriptions and rank jobs by fit."

    raw_output = call_llm(system_prompt, user_prompt)

    # ---- SAFE JSON PARSING ----
    try:
        parsed = json.loads(raw_output)
        if isinstance(parsed, list):
            return parsed[:5]
        return []
    except:
        # attempt to extract JSON part
        try:
            start = raw_output.find("[")
            end = raw_output.rfind("]") + 1
            cleaned = raw_output[start:end]
            parsed = json.loads(cleaned)
            return parsed[:5] if isinstance(parsed, list) else []
        except:
            return []
