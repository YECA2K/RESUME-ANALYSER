import json
from typing import List, Dict, Any

from .openrouter_client import call_openrouter

# Modèle rapide pour le ranking
MODEL = "qwen/qwen3-coder-flash"


def _build_candidate_text(candidate) -> str:
    skills = getattr(candidate, "skills", []) or []
    summary = getattr(candidate, "summary", "") or ""
    experiences = getattr(candidate, "experiences", []) or []

    exp_lines = []
    for e in experiences[:4]:
        if isinstance(e, dict):
            line = " | ".join(
                [
                    e.get("title") or e.get("position", ""),
                    e.get("company", ""),
                    e.get("period", "") or e.get("years", ""),
                ]
            )
        else:
            line = str(e)
        if line.strip():
            exp_lines.append(line)

    parts = []
    if summary:
        parts.append(f"Summary: {summary}")
    if skills:
        parts.append("Skills: " + ", ".join(skills))
    if exp_lines:
        parts.append("Experiences:\n" + "\n".join(exp_lines))

    return "\n".join(parts)


def _build_jobs_block(jobs: List[Dict[str, Any]]) -> str:
    """
    Construit un bloc Jobs limité pour ne pas exploser le contexte du LLM.
    """
    lines = []
    max_jobs = min(len(jobs), 40)

    for i in range(max_jobs):
        job = jobs[i]
        title = job.get("title") or "Unknown title"
        company = job.get("company") or "Unknown company"
        desc = job.get("description_text") or ""
        if len(desc) > 400:
            desc = desc[:400] + "..."

        lines.append(
            f"JOB {i+1}:\n"
            f"Title: {title}\n"
            f"Company: {company}\n"
            f"Description: {desc}\n"
        )

    return "\n".join(lines)


def match_candidate_to_jobs(candidate, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Retourne une liste de dicts:
    [
      {"job_index": 1, "score": 0.95},
      ...
    ]
    job_index est 1-based (JOB 1, JOB 2, etc.)
    """
    if not jobs:
        return []

    candidate_text = _build_candidate_text(candidate)
    jobs_block = _build_jobs_block(jobs)

    system_prompt = (
        "You are an expert job matching system. "
        "You only rank the jobs by relevance to the candidate. "
        "Return ONLY valid JSON, no comments."
    )

    user_prompt = f"""
Candidate:
{candidate_text}

Jobs:
{jobs_block}

Return ONLY a JSON array like:
[
  {{"job_index": 1, "score": 0.95}},
  {{"job_index": 4, "score": 0.88}}
]

Rules:
- job_index must match the JOB number (1-based).
- score is between 0 and 1 (float).
- Do not include any explanation text, only JSON.
"""

    raw = call_openrouter(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=400,
    )

    # Parsing JSON robuste
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            # petit nettoyage
            out = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                idx = item.get("job_index")
                score = item.get("score")
                if idx is None or score is None:
                    continue
                try:
                    out.append(
                        {
                            "job_index": int(idx),
                            "score": float(score),
                        }
                    )
                except Exception:
                    continue
            return out
        return []
    except Exception:
        # tentative de rescue simple
        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                parsed = json.loads(raw[start:end])
                if isinstance(parsed, list):
                    return parsed
        except Exception:
            pass
        return []
