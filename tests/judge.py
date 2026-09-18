"""LLM-as-judge: nilai kualitas jawaban eval (skor 1-5 + alasan).

Dipakai opt-in via: python tests/run_eval.py --judge
Skor masuk last_eval.json per kasus: {"judge": {"score": 4, "reason": "..."}}.
"""

import json
import re

RUBRIC = """Nilailah kualitas jawaban asisten (skor 1-5) atas pertanyaan user.
Kriteria: ketepatan (benar & relevan), kelengkapan (menjawab semua yang diminta),
kejelasan (bahasa Indonesia rapi), kejujuran (tak mengarang).

Jawab HANYA JSON: {"score": <1-5>, "reason": "<1 kalimat>"}
"""


def parse_judge_output(text: str) -> dict:
    """Parse output judge → {score|None, reason}. Pure, testable."""
    if not text:
        return {"score": None, "reason": "empty"}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"score": None, "reason": text[:200]}
    try:
        data = json.loads(m.group())
        score = int(data.get("score", 0))
        if score < 1 or score > 5:
            return {"score": None, "reason": str(data)[:200]}
        return {"score": score, "reason": str(data.get("reason", ""))[:300]}
    except (ValueError, TypeError, json.JSONDecodeError):
        return {"score": None, "reason": text[:200]}


def judge_answer(question: str, answer: str) -> dict:
    """Panggil LLM sebagai juri. Butuh infra+LLM (opt-in)."""
    from agents.llm_config import get_llm
    llm = get_llm()
    prompt = f"{RUBRIC}\nPertanyaan: {question[:800]}\nJawaban: {answer[:3000]}"
    try:
        response = llm.invoke(prompt)
        from core.text import extract_text
        text = extract_text(response.content if hasattr(response, "content") else str(response))
        return parse_judge_output(text)
    except Exception as e:
        return {"score": None, "reason": f"judge error: {str(e)[:150]}"}
