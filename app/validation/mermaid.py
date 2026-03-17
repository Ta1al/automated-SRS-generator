"""
Mermaid diagram syntax validator.

Primary strategy  : Run the official @mermaid-js/mermaid-cli (mmdc) as an
                    async subprocess.  mmdc must be installed globally:

    npm install -g @mermaid-js/mermaid-cli

Fallback strategy : Regex-based heuristic check when mmdc is not available in
                    PATH (e.g. CI environments without Node.js).

Returns:
    (valid: bool, error_message: str)
    On success error_message is an empty string.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Supported diagram types for the fallback heuristic ────────────────────────
_VALID_TYPES = re.compile(
    r"^\s*(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram"
    r"|stateDiagram-v2|erDiagram|gantt|pie|gitGraph|mindmap|timeline"
    r"|C4Context|C4Container|quadrantChart|xychart-beta)\b",
    re.IGNORECASE | re.MULTILINE,
)


# ER diagram relationship connectors that contain { or } but are NOT brackets
_ER_EDGE_PATTERN = re.compile(r"\|[o|]{0,2}[{|]|[{|][o|]{0,2}\|")


def _heuristic_validate(code: str) -> tuple[bool, str]:
    """
    Lightweight regex-based Mermaid syntax check.  Not exhaustive but catches
    the most common generation errors when mmdc is unavailable.
    """
    stripped = code.strip()
    if not stripped:
        return False, "Empty diagram body."

    # Must start with a recognised diagram type
    if not _VALID_TYPES.search(stripped):
        return False, (
            "Diagram does not begin with a recognised Mermaid diagram type "
            "(flowchart, sequenceDiagram, classDiagram, erDiagram, \u2026)."
        )

    # Skip bracket balance check for erDiagram — relationship connectors like
    # ||--o{ and ||--|{ use { } as cardinality markers, not bracket pairs.
    first_line = stripped.split("\n")[0].strip().lower()
    if first_line.startswith("erdiagram"):
        return True, ""

    # Balanced parentheses / brackets / braces
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack: list[str] = []
    for ch in stripped:
        if ch in pairs:
            stack.append(ch)
        elif ch in pairs.values():
            if not stack or pairs[stack[-1]] != ch:
                return False, f"Unbalanced brackets \u2014 unexpected '{ch}'."
            stack.pop()
    if stack:
        return False, f"Unclosed bracket(s): {''.join(stack)}"

    return True, ""


async def validate_mermaid_syntax(code: str) -> tuple[bool, str]:
    """
    Validate Mermaid syntax.

    1. Tries mmdc (mermaid-cli) via subprocess — authoritative AST parse.
    2. Falls back to _heuristic_validate when mmdc is not on PATH.

    Args:
        code: Raw Mermaid diagram text (without the triple-backtick fence).

    Returns:
        (valid, error_message)
    """
    mmdc_path = shutil.which("mmdc")
    if mmdc_path is None:
        logger.warning(
            "mmdc not found in PATH — using heuristic Mermaid validator. "
            "Install with: npm install -g @mermaid-js/mermaid-cli"
        )
        return _heuristic_validate(code)

    # Write to a temp file so mmdc can read it
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".mmd", delete=False, encoding="utf-8"
    ) as tmp_in:
        tmp_in.write(code)
        tmp_in_path = tmp_in.name

    # Output to /dev/null (or NUL on Windows) — we only care about exit code
    null_out = "NUL" if Path("/dev/null").exists() is False else "/dev/null"

    try:
        proc = await asyncio.create_subprocess_exec(
            mmdc_path,
            "-i", tmp_in_path,
            "-o", null_out,
            "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=20)
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        if proc.returncode == 0:
            return True, ""
        return False, stderr or "mmdc exited with a non-zero return code."
    except asyncio.TimeoutError:
        return False, "mmdc validation timed out (>20 s)."
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected error running mmdc: %s", exc)
        return _heuristic_validate(code)
    finally:
        Path(tmp_in_path).unlink(missing_ok=True)
