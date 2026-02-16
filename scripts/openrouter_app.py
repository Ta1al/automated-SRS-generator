import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable
from dotenv import load_dotenv

import requests
from rank_bm25 import BM25Okapi

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
sys.path.append(str(Path(__file__).resolve().parent))

from clarification_loop import generate_questions, build_llm_prompt

BASE_DIR = Path(__file__).resolve().parents[1]
NORMALIZED_PATH = BASE_DIR / "data" / "normalized" / "combined.jsonl"


def load_corpus(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(
            f"Normalized data not found: {path}. Run scripts/normalize_data.py first."
        )
    texts = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            text = record.get("text", "").strip()
            if text:
                texts.append(text)
    return texts


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in text.split() if t.strip()]


def retrieve_context(corpus: list[str], query: str, k: int = 5) -> list[str]:
    tokenized = [tokenize(doc) for doc in corpus]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return [corpus[i] for i in ranked[:k]]


def ask_questions(questions: Iterable) -> dict[str, str]:
    answers: dict[str, str] = {}
    for question in questions:
        print(f"\n[{question.section}] {question.prompt}")
        for idx, option in enumerate(question.options, start=1):
            print(f"  {idx}. {option}")
        choice = input("Select an option or type your own answer: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(question.options):
            answers[question.question_id] = question.options[int(choice) - 1]
        else:
            answers[question.question_id] = choice
    return answers


def call_openrouter(system_prompt: str, user_prompt: str, dry_run: bool = False) -> str:
    if dry_run:
        return "[DRY RUN] OpenRouter call skipped."

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENROUTER_API_KEY is not set.")

    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    referer = os.getenv("OPENROUTER_HTTP_REFERER")
    title = os.getenv("OPENROUTER_APP_TITLE")
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=60,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        details = response.text.strip() if response.text else "No response body."
        hint = (
            "Check OPENROUTER_API_KEY, model access, and optional HTTP-Referer/X-Title."
            if response.status_code == 403
            else ""
        )
        raise RuntimeError(
            f"OpenRouter error {response.status_code}: {details}\n{hint}"
        ) from exc

    data = response.json()
    return data["choices"][0]["message"]["content"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Clarification loop + RAG demo using OpenRouter.")
    parser.add_argument("--idea", help="Initial user idea text.")
    parser.add_argument("--k", type=int, default=5, help="Number of context items to retrieve.")
    parser.add_argument("--max-questions", type=int, default=6, help="Max clarification questions.")
    parser.add_argument("--dry-run", action="store_true", help="Skip OpenRouter call.")
    args = parser.parse_args()

    idea = args.idea or input("Describe your product idea: ").strip()
    corpus = load_corpus(NORMALIZED_PATH)

    questions = generate_questions(idea, max_questions=args.max_questions)
    answers = ask_questions(questions)
    context = retrieve_context(corpus, idea, k=args.k)

    prompts = build_llm_prompt(idea, answers, context)
    reply = call_openrouter(prompts["system"], prompts["user"], dry_run=args.dry_run)

    print("\n--- OpenRouter Response ---")
    print(reply)


if __name__ == "__main__":
    main()
