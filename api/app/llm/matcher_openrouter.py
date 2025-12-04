import json
from typing import List, Dict, Any

from .openrouter_client import call_openrouter

# Fast model for ranking (keep small)
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
                    (e.get("title") or e.get("position") or "").strip(),
                    (e.get("company") or "").strip(),
                    (e.get("period") or e.get("years") or "").strip(),
                ]
            ).strip()
        else:
            line = str(e).strip()
        if line:
            exp_lines.append(line)

    parts = []
    if summary:
        parts.append(f"Summary: {summary}")
    if skills:
        parts.append("Skills: " + ", ".join([str(s) for s in skills if str(s).strip()]))
    if exp_lines:
        parts.append("Experiences:\n" + "\n".join(exp_lines))

    return "\n".join(parts).strip()


def _build_jobs_block(jobs: List[Dict[str, Any]]) -> str:
    lines = []
    max_jobs = min(len(jobs), 40)

    for i in range(max_jobs):
        job = jobs[i]
        title = job.get("title") or "Unknown title"
        company = job.get("company") or "Unknown company"
        desc = job.get("description_text") or ""
        if len(desc) > 450:
            desc = desc[:450] + "..."

        lines.append(
            f"JOB {i+1}:\n"
            f"Title: {title}\n"
            f"Company: {company}\n"
            f"Description: {desc}\n"
        )

    return "\n".join(lines)


def match_candidate_to_jobs(candidate, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Returns:
    [
      {"job_index": 1, "score": 0.95},
      ...
    ]
    job_index is 1-based (JOB 1..N)
    """
    if not jobs:
        return []

    candidate_text = _build_candidate_text(candidate)
    jobs_block = _build_jobs_block(jobs)

    system_prompt = (
        "You are an expert job matching system. "
        "Rank jobs by relevance to the candidate. "
        "Return ONLY valid JSON (no markdown, no comments)."
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
- Return at most 20 items.
- Do not include any text outside JSON.
"""

    raw = call_openrouter(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=350,
        temperature=0.0,
        top_p=1.0,
        extra={
            "frequency_penalty": 0,
            "presence_penalty": 0,
        },
    )

    def _clean_list(lst):
        out = []
        for item in lst:
            if not isinstance(item, dict):
                continue
            idx = item.get("job_index")
            score = item.get("score")
            if idx is None or score is None:
                continue
            try:
                idx = int(idx)
                score = float(score)
            except Exception:
                continue
            if idx < 1:
                continue
            if score < 0:
                score = 0.0
            if score > 1:
                score = 1.0
            out.append({"job_index": idx, "score": score})
        return out[:20]

    # Parse JSON
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return _clean_list(parsed)
        return []
    except Exception:
        # rescue [ ... ]
        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                parsed = json.loads(raw[start:end])
                if isinstance(parsed, list):
                    return _clean_list(parsed)
        except Exception:
            pass
        return []
