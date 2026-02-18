from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Iterable


@dataclass
class ClarificationQuestion:
    question_id: str
    section: str
    prompt: str
    options: list[str]
    required: bool = True
    tags: list[str] = field(default_factory=list)
    rationale: str | None = None


@dataclass
class ClarificationState:
    product_name: str | None = None
    target_users: str | None = None
    primary_goals: str | None = None
    platforms: str | None = None
    data_types: str | None = None
    integrations: str | None = None
    auth: str | None = None
    compliance: str | None = None
    performance: str | None = None
    availability: str | None = None
    security: str | None = None
    scalability: str | None = None

    def apply_answers(self, answers: dict[str, str]) -> None:
        for key, value in answers.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def to_dict(self) -> dict[str, str | None]:
        return {
            "product_name": self.product_name,
            "target_users": self.target_users,
            "primary_goals": self.primary_goals,
            "platforms": self.platforms,
            "data_types": self.data_types,
            "integrations": self.integrations,
            "auth": self.auth,
            "compliance": self.compliance,
            "performance": self.performance,
            "availability": self.availability,
            "security": self.security,
            "scalability": self.scalability,
        }


def build_question_prompt(
    user_text: str,
    answers: dict[str, str],
    retrieved_context: list[str],
    max_questions: int = 3,
) -> dict[str, str]:
    context_block = "\n".join(f"- {item}" for item in retrieved_context)
    answers_block = json.dumps(answers, ensure_ascii=False, indent=2)

    system = (
        "You are a requirements assistant. Ask concise clarification questions when information "
        "is missing. Use the retrieved context as grounding and avoid hallucinations."
    )

    user = (
        "Initial user idea:\n"
        f"{user_text}\n\n"
        "Known answers:\n"
        f"{answers_block}\n\n"
        "Retrieved context:\n"
        f"{context_block}\n\n"
        "Return JSON only with this shape:\n"
        "{\"questions\":[{\"question_id\":string,\"section\":string,\"prompt\":string,"
        "\"options\":array,\"required\":boolean,\"rationale\":string}]}.\n"
        f"Ask up to {max_questions} questions. If no questions needed, return {{\"questions\":[]}}."
    )

    return {"system": system, "user": user}


def _extract_json(text: str) -> str:
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            if "{" in part and "}" in part:
                text = part
                break
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model response.")
    return text[start : end + 1]


def parse_questions(response_text: str) -> list[ClarificationQuestion]:
    payload = json.loads(_extract_json(response_text))
    questions = []
    for item in payload.get("questions", []):
        questions.append(
            ClarificationQuestion(
                question_id=item.get("question_id", ""),
                section=item.get("section", ""),
                prompt=item.get("prompt", ""),
                options=item.get("options", []) or [],
                required=bool(item.get("required", True)),
                tags=item.get("tags", []) or [],
                rationale=item.get("rationale"),
            )
        )
    return questions
