"""
Backend formatting utilities for SRS documents.

Shared helpers for text transformation, heading numbering, requirement parsing,
and document assembly.
"""

import re


def number_headings(text: str) -> str:
    """
    Number markdown headings hierarchically across levels 1-6.
    
    Strips existing numbering and applies consistent formatting like:
    # 1 Introduction
    ## 1.1 Overview
    ### 1.1.1 Details
    
    Args:
        text: Markdown text with headings.
    
    Returns:
        Markdown text with numbered headings.
    """
    counters = [0, 0, 0, 0, 0, 0]
    out_lines: list[str] = []
    
    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s*(.+)$", line)
        if not m:
            out_lines.append(line)
            continue

        level = min(6, len(m.group(1)))
        # Strip existing numbering patterns from the title
        title = re.sub(r"^[0-9]+(?:\.[0-9]+)*[\)\.:\-\s]+", "", m.group(2)).strip()

        # Increment counter at this level and reset deeper levels
        counters[level - 1] += 1
        for i in range(level, 6):
            counters[i] = 0

        parts = [str(n) for n in counters[:level] if n > 0]
        number = ".".join(parts)
        out_lines.append(f"{m.group(1)} {number} {title}".rstrip())

    return "\n".join(out_lines)


def split_functional_requirements(text: str) -> str:
    """
    Restructure functional requirements into proper list format.
    
    Converts inline requirement markers like " - [F-1]" into separate list items,
    and ensures requirement blocks are properly split for parsing.
    
    Args:
        text: Markdown text with inline requirements.
    
    Returns:
        Markdown text with requirements restructured as proper lists.
    """
    out = text
    # Insert newline before inline requirement markers like " - [F-1]"
    out = re.sub(r"\s-\s*(\[F[-_A-Za-z0-9]*\])", r"\n- \1", out)
    # Split sequences like "] - [" between requirements
    out = re.sub(r"\]\s*-\s*\[", r"]\n- [", out)
    # Move inline lists after headings like "Functional Requirements - [F-1]..." to actual list
    out = re.sub(
        r"(Functional Requirements[:\-–\s]*)(\[F[-_A-Za-z0-9]*\])",
        lambda m: f"{m.group(1).strip()}\n- {m.group(2)}",
        out,
        flags=re.IGNORECASE,
    )
    return out


def format_srs_body(text: str) -> str:
    """
    Apply backend formatting to SRS body text.
    
    Applies splitting and numbering in the correct order so that
    numbering reflects the final list structure.
    
    Args:
        text: Raw SRS body markdown.
    
    Returns:
        Formatted SRS body markdown.
    """
    # Apply splitting first so numbering reflects list structure
    body = split_functional_requirements(text)
    body = number_headings(body)
    return body


def assemble_document_from_sections(sections: dict[str, str] | None) -> str:
    """Assemble ordered SRS Markdown from stored section drafts."""
    ordered_keys = ["s1", "s2", "s3_functional", "s3_external", "s3_nfr", "s4"]
    parts = [str((sections or {}).get(key, "")).strip() for key in ordered_keys if str((sections or {}).get(key, "")).strip()]
    return "\n\n".join(parts).strip()
