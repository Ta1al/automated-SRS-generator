import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable
from dotenv import load_dotenv
from openai import OpenAI
from rank_bm25 import BM25Okapi

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
sys.path.append(str(Path(__file__).resolve().parent))

from clarification_loop import build_question_prompt, parse_questions

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


def _create_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENROUTER_API_KEY is not set.")

    default_headers = {}
    referer = os.getenv("OPENROUTER_HTTP_REFERER")
    title = os.getenv("OPENROUTER_APP_TITLE")
    if referer:
        default_headers["HTTP-Referer"] = referer
    if title:
        default_headers["X-Title"] = title

    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers=default_headers or None,
    )


def call_openrouter(
    system_prompt: str,
    user_prompt: str,
    dry_run: bool = False,
    stream: bool = False,
) -> str:
    if dry_run:
        return "[DRY RUN] OpenRouter call skipped."

    client = _create_client()
    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    try:
        if stream:
            stream_resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                stream=True,
            )
            chunks: list[str] = []
            for event in stream_resp:
                delta = event.choices[0].delta.content
                if delta:
                    print(delta, end="", flush=True)
                    chunks.append(delta)
            print()
            return "".join(chunks)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        status_code = getattr(exc, "status_code", None)
        hint = (
            "Check OPENROUTER_API_KEY, model access, and optional HTTP-Referer/X-Title."
            if status_code == 403
            else ""
        )
        raise RuntimeError(f"OpenRouter request failed. {hint}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Clarification loop + RAG demo using OpenRouter.")
    parser.add_argument("--idea", help="Initial user idea text.")
    parser.add_argument("--k", type=int, default=5, help="Number of context items to retrieve.")
    parser.add_argument("--max-questions", type=int, default=6, help="Max clarification questions.")
    parser.add_argument("--rounds", type=int, default=2, help="Max clarification rounds.")
    parser.add_argument("--dry-run", action="store_true", help="Skip OpenRouter call.")
    parser.add_argument("--stream", action="store_true", help="Stream LLM response to console.")
    args = parser.parse_args()

    idea = args.idea or input("Describe your product idea: ").strip()
    corpus = load_corpus(NORMALIZED_PATH)

    context = retrieve_context(corpus, idea, k=args.k)
    answers: dict[str, str] = {}

    for _ in range(args.rounds):
        prompts = build_question_prompt(
            idea,
            answers,
            context,
            max_questions=args.max_questions,
        )
        reply = call_openrouter(
            prompts["system"],
            prompts["user"],
            dry_run=args.dry_run,
            stream=args.stream,
        )

        if args.dry_run:
            print("\n--- LLM Prompt (dry run) ---")
            print(prompts["user"])
            break

        try:
            questions = parse_questions(reply)
        except ValueError as exc:
            print("\n--- OpenRouter Response (raw) ---")
            print(reply)
            raise SystemExit(str(exc)) from exc

        if not questions:
            print("\nNo further clarification questions.")
            break

        new_answers = ask_questions(questions)
        answers.update(new_answers)

    print("\n--- Collected Answers ---")
    print(json.dumps(answers, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
