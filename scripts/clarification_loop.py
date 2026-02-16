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


QUESTION_BANK: dict[str, ClarificationQuestion] = {
    "product_name": ClarificationQuestion(
        question_id="product_name",
        section="Introduction",
        prompt="What should we call this product in the SRS?",
        options=[
            "Use a working name",
            "Use a final brand name",
            "No name yet (use placeholder)",
        ],
        tags=["srs", "naming"],
    ),
    "target_users": ClarificationQuestion(
        question_id="target_users",
        section="Product Overview",
        prompt="Who are the primary users?",
        options=[
            "General public",
            "Business users",
            "Internal staff",
            "Admins only",
            "Mixed roles",
        ],
        tags=["users", "stakeholders"],
    ),
    "primary_goals": ClarificationQuestion(
        question_id="primary_goals",
        section="Product Overview",
        prompt="What are the top 2-3 goals the product must achieve?",
        options=[
            "Collect user input and generate documents",
            "Automate a manual workflow",
            "Provide analytics/reporting",
            "Enable collaboration",
            "Other",
        ],
        tags=["scope", "goals"],
    ),
    "platforms": ClarificationQuestion(
        question_id="platforms",
        section="Product Constraints",
        prompt="Which platforms must the product support?",
        options=["Web", "Mobile", "Desktop", "API-only", "Other"],
        tags=["constraints", "platform"],
    ),
    "data_types": ClarificationQuestion(
        question_id="data_types",
        section="Requirements",
        prompt="What data types will users input or generate?",
        options=[
            "Text-only",
            "Files (PDF/DOCX)",
            "Images/diagrams",
            "Sensitive data (PII)",
            "Other",
        ],
        tags=["data", "privacy"],
    ),
    "integrations": ClarificationQuestion(
        question_id="integrations",
        section="External Interfaces",
        prompt="Are any external systems or APIs required?",
        options=[
            "None",
            "OAuth/SSO",
            "Storage (S3/Drive)",
            "Issue trackers (Jira/GitHub)",
            "Other",
        ],
        tags=["integration", "interfaces"],
    ),
    "auth": ClarificationQuestion(
        question_id="auth",
        section="Security",
        prompt="How should users authenticate?",
        options=["Email/password", "SSO/OAuth", "Magic links", "No auth"],
        tags=["security", "auth"],
    ),
    "compliance": ClarificationQuestion(
        question_id="compliance",
        section="Compliance",
        prompt="Any compliance requirements?",
        options=["None", "GDPR", "HIPAA", "PCI-DSS", "Other"],
        tags=["legal", "compliance"],
    ),
    "performance": ClarificationQuestion(
        question_id="performance",
        section="Quality of Service",
        prompt="Any performance targets?",
        options=[
            "Under 2s for most actions",
            "Under 5s for document generation",
            "No strict targets",
            "Other",
        ],
        tags=["performance", "latency"],
    ),
    "availability": ClarificationQuestion(
        question_id="availability",
        section="Quality of Service",
        prompt="What availability/uptime is expected?",
        options=["99%", "99.9%", "99.99%", "Best effort"],
        tags=["availability", "sla"],
    ),
    "security": ClarificationQuestion(
        question_id="security",
        section="Quality of Service",
        prompt="Any security expectations?",
        options=[
            "Role-based access",
            "Audit logs",
            "Encryption at rest",
            "No special requirements",
        ],
        tags=["security", "controls"],
    ),
    "scalability": ClarificationQuestion(
        question_id="scalability",
        section="Quality of Service",
        prompt="Expected scale at launch?",
        options=[
            "<100 daily users",
            "100-1,000 daily users",
            "1,000-10,000 daily users",
            ">10,000 daily users",
        ],
        tags=["scale", "capacity"],
    ),
}


def _has_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pat, text, re.IGNORECASE) for pat in patterns)


def analyze_gaps(user_text: str) -> list[str]:
    text = user_text.strip()
    missing = []

    if not _has_any(text, [r"\bname\b", r"\bcalled\b", r"\bnamed\b", r"\bproduct\b"]):
        missing.append("product_name")
    if not _has_any(text, [r"\buser\b", r"\bcustomer\b", r"\badmin\b", r"\bclient\b", r"\bstaff\b"]):
        missing.append("target_users")
    if not _has_any(text, [r"\bgoal\b", r"\bmust\b", r"\bneed\b", r"\bwant\b", r"\bshould\b"]):
        missing.append("primary_goals")
    if not _has_any(text, [r"\bweb\b", r"\bmobile\b", r"\bdesktop\b", r"\bapi\b"]):
        missing.append("platforms")
    if not _has_any(text, [r"\bdata\b", r"\bdocument\b", r"\bfile\b", r"\bpdf\b", r"\bdiagram\b"]):
        missing.append("data_types")
    if not _has_any(text, [r"\bintegrat\b", r"\bapi\b", r"\bthird\b", r"\bexternal\b"]):
        missing.append("integrations")
    if not _has_any(text, [r"\blogin\b", r"\bauth\b", r"\bsso\b", r"\bsign\s?up\b"]):
        missing.append("auth")
    if not _has_any(text, [r"\bgdpr\b", r"\bhipaa\b", r"\bpci\b", r"\bcompliance\b"]):
        missing.append("compliance")
    if not _has_any(text, [r"\bms\b", r"\bseconds\b", r"\blatency\b", r"\bperformance\b"]):
        missing.append("performance")
    if not _has_any(text, [r"\buptime\b", r"\bavailability\b", r"\b24/7\b"]):
        missing.append("availability")
    if not _has_any(text, [r"\bsecurity\b", r"\bencrypt\b", r"\brole\b", r"\baudit\b"]):
        missing.append("security")
    if not _has_any(text, [r"\busers\b", r"\bconcurrent\b", r"\bscale\b", r"\bload\b"]):
        missing.append("scalability")

    return missing


def generate_questions(user_text: str, max_questions: int = 6) -> list[ClarificationQuestion]:
    missing = analyze_gaps(user_text)
    questions = [QUESTION_BANK[key] for key in missing if key in QUESTION_BANK]
    return questions[:max_questions]


def build_llm_prompt(
    user_text: str,
    answers: dict[str, str],
    retrieved_context: list[str],
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
        "Return the next 1-3 clarification questions with multiple-choice options when possible."
    )

    return {"system": system, "user": user}
