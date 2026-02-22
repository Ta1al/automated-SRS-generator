import argparse
import json
import sys
from pathlib import Path

# include repo root so we can import the cli package
sys.path.append(str(Path(__file__).resolve().parents[1]))

from cli.clarification_loop import build_question_prompt


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the clarification loop demo.")
    parser.add_argument("--input", required=True, help="Initial user idea text.")
    parser.add_argument("--answers", help="JSON map of previous answers.")
    parser.add_argument("--context", help="JSON list of retrieved context strings.")
    parser.add_argument("--max", type=int, default=6, help="Max questions to return.")
    args = parser.parse_args()

    answers = json.loads(args.answers) if args.answers else {}
    context = json.loads(args.context) if args.context else []

    prompts = build_question_prompt(args.input, answers, context, max_questions=args.max)
    payload = {"llm_prompt": prompts}

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
