"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  type BackendStatusEvent,
  type ClarificationQuestion,
  formatClarificationPrompt,
  normalizeClarificationQuestions,
} from "@/lib/backend";

type ChatListItem = {
  id: string;
  title: string;
  currentDocument: string | null;
  stateJson: Record<string, unknown> | null;
  updatedAt: string;
};

type ChatMessage = {
  id: string;
  role: "USER" | "ASSISTANT";
  content: string;
  createdAt: string;
};

type ChatDetails = {
  chat: {
    id: string;
    title: string;
    currentDocument: string | null;
    stateJson: Record<string, unknown> | null;
    messages: ChatMessage[];
  };
};

type ActiveRunSummary = {
  id: string;
  chatTitle?: string;
  status: "RUNNING" | "COMPLETED" | "FAILED" | "NEEDS_INPUT";
  currentNode: string | null;
  etaSeconds: number | null;
  errorMessage: string | null;
  questionPrompt: string | null;
  questions: ClarificationQuestion[];
  statuses: BackendStatusEvent[];
  liveSections?: Record<string, string>;
};

type SectionStreamPayload = {
  status?: "RUNNING" | "COMPLETED" | "FAILED" | "NEEDS_INPUT";
  currentNode?: string | null;
  etaSeconds?: number | null;
  sections?: Record<string, string>;
};

type QuestionMode = {
  introPrompt: string;
  questions: ClarificationQuestion[];
  answers: string[];
};

type DraftPart = {
  id: string;
  title: string;
  content: string;
  sectionKey: string;
  preview: string;
};

type RevisionTarget = {
  title: string;
  content: string;
  sectionKey: string;
};

const SECTION_TITLES: Record<string, string> = {
  s1: "Section 1 · Introduction",
  s2: "Section 2 · Product Overview",
  s3_iface: "Section 3.1 · External Interfaces",
  s3_fr: "Section 3.2 · Functional Requirements",
  s3_nfr: "Section 3.3 · Quality of Service",
  s4: "Section 4 · Verification",
};

const SECTION_ORDER = ["s1", "s2", "s3_iface", "s3_fr", "s3_nfr", "s4"];
// All five section writers run in parallel after elicit_requirements
const PARALLEL_DRAFT_NODES = new Set([
  "draft_section_1",
  "draft_section_2",
  "draft_section_3_iface",
  "draft_section_3_fr",
  "draft_section_3_nfr",
]);
const DRAFT_NODE_TO_SECTION_KEY: Record<string, string> = {
  draft_section_1: "s1",
  draft_section_2: "s2",
  draft_section_3_iface: "s3_iface",
  draft_section_3_fr: "s3_fr",
  draft_section_3_nfr: "s3_nfr",
  draft_section_4: "s4",
};

const NODE_LABELS: Record<string, string> = {
  retrieve_rag_context: "Retrieved compliance context",
  elicit_requirements: "the initial product outline",
  evaluate_completeness: "Audited brief for missing requirements",
  ask_clarifying_questions: "Prepared follow-up questions",
  classify_requirements: "Classified requirements",
  draft_section_3_fr: "Drafted functional requirements",
  draft_section_3_nfr: "Drafted non-functional requirements",
  draft_section_3_iface: "Drafted interface requirements",
  draft_section_1: "Drafted introduction",
  draft_section_2: "Drafted product overview",
  draft_section_4: "Built verification matrix",
  revise_selected_section: "Revised selected section",
  generate_mermaid: "Generated diagrams",
  validate_mermaid: "Validated diagrams",
  correct_mermaid: "Corrected diagram syntax",
  qa_review: "Ran QA review",
  finalize_document: "Assembled the final document",
};

function formatSectionTitle(key: string) {
  return SECTION_TITLES[key] || key.replaceAll("_", " ");
}

function slugifyText(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "part";
}

function buildDraftDocument(sections: Array<{ key: string; content: string }>) {
  return sections
    .map((section) => normalizeMarkdownForPreview(section.content).trim())
    .filter(Boolean)
    .join("\n\n");
}

function normalizeMarkdownForPreview(content: string) {
  const normalized = content.replace(/\r\n?/g, "\n").trim();
  const wrappedMarkdownFenceMatch = normalized.match(/^```(?:markdown|md)\s*\n([\s\S]*?)\n```\s*$/i);
  const unwrapped = wrappedMarkdownFenceMatch ? wrappedMarkdownFenceMatch[1] : normalized;

  return unwrapped.replace(/\n{3,}/g, "\n\n").trim();
}

function buildDraftPreviewText(content: string) {
  return normalizeMarkdownForPreview(content)
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/[*_~]/g, "")
    .replace(/\|/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 180);
}

function hasDraftPartBodyContent(content: string) {
  const normalized = normalizeMarkdownForPreview(content);
  const withoutHeadings = normalized
    .replace(/^\s{0,3}#{1,6}\s+.*$/gm, "")
    .replace(/^\s{0,3}#{1,6}\s*$/gm, "")
    .replace(/^\s{0,3}[-*_]{3,}\s*$/gm, "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/\s+/g, " ")
    .trim();

  return /[A-Za-z0-9]/.test(withoutHeadings);
}

function extractFirstMermaidChart(content: string) {
  const normalized = normalizeMarkdownForPreview(content);
  const match = normalized.match(/```mermaid\s*\n([\s\S]*?)\n```/i);
  return match?.[1]?.trim() || "";
}

function extractDraftParts(sectionKey: string, content: string): DraftPart[] {
  const trimmedContent = normalizeMarkdownForPreview(content).trim();
  if (!trimmedContent) {
    return [];
  }

  const lines = trimmedContent.split(/\r?\n/);
  const headings = lines
    .map((line) => ({
      match: /^(#{3,4})\s+(.+)$/.exec(line.trim()),
    }))
    .filter((entry): entry is { match: RegExpExecArray } => !!entry.match);

  const headingLevels = new Set(headings.map((entry) => entry.match[1].length));
  const targetLevel = headingLevels.has(4) ? 4 : headingLevels.has(3) ? 3 : null;

  if (!targetLevel) {
    return [
      {
        id: `${sectionKey}-root`,
        title: formatSectionTitle(sectionKey),
        content: trimmedContent,
        sectionKey,
        preview: buildDraftPreviewText(trimmedContent),
      },
    ];
  }

  const parts: DraftPart[] = [];
  let currentTitle = formatSectionTitle(sectionKey);
  let currentLines: string[] = [];

  const flushPart = () => {
    const partContent = currentLines.join("\n").trim();
    if (!partContent) {
      return;
    }

    parts.push({
      id: `${sectionKey}-${slugifyText(currentTitle)}-${parts.length + 1}`,
      title: currentTitle,
      content: partContent,
      sectionKey,
      preview: buildDraftPreviewText(partContent),
    });
  };

  for (const line of lines) {
    const headingMatch = /^(#{3,4})\s+(.+)$/.exec(line.trim());
    if (headingMatch && headingMatch[1].length === targetLevel) {
      flushPart();
      currentTitle = headingMatch[2].trim();
      currentLines = [line];
      continue;
    }

    if (currentLines.length === 0 && !line.trim()) {
      continue;
    }

    currentLines.push(line);
  }

  flushPart();

  return parts.length > 0
    ? parts
    : [
        {
          id: `${sectionKey}-root`,
          title: formatSectionTitle(sectionKey),
          content: trimmedContent,
          sectionKey,
          preview: buildDraftPreviewText(trimmedContent),
        },
      ];
}

function getWaitingOnLabel(statuses: BackendStatusEvent[], activeNode: string | null) {
  if (activeNode) {
    return NODE_LABELS[activeNode] || activeNode.replaceAll("_", " ");
  }

  if (statuses.length === 0) {
    return "Submitting your request";
  }

  const finishedNodes = new Set(
    statuses.filter((item) => item.status === "finished").map((item) => item.node),
  );
  const latest = statuses[statuses.length - 1];

  if (latest.node === "elicit_requirements") {
    return "Drafting the core requirements sections";
  }

  if (PARALLEL_DRAFT_NODES.has(latest.node)) {
    const completedCount = [...PARALLEL_DRAFT_NODES].filter((node) => finishedNodes.has(node)).length;
    return completedCount < PARALLEL_DRAFT_NODES.size
      ? `Drafting sections in parallel (${completedCount}/${PARALLEL_DRAFT_NODES.size})`
      : NODE_LABELS.draft_section_4;
  }

  const nextNodeMap: Record<string, string> = {
    retrieve_rag_context: "elicit_requirements",
    elicit_requirements: "draft_section_1",
    draft_section_4: "generate_mermaid",
    generate_mermaid: "validate_mermaid",
    validate_mermaid: "finalize_document",
  };

  const nextNode = nextNodeMap[latest.node];
  if (nextNode) {
    return NODE_LABELS[nextNode] || nextNode.replaceAll("_", " ");
  }

  return getStatusLabel(latest);
}

function getStatusLabel(event: BackendStatusEvent) {
  const base = NODE_LABELS[event.node] || event.node.replaceAll("_", " ");
  return event.status === "finished" ? base : `${base} (${event.status})`;
}

function formatEtaLabel(seconds: number | null) {
  if (seconds === null || Number.isNaN(seconds)) {
    return "Estimating time remaining...";
  }

  if (seconds <= 30) {
    return "Estimated remaining: under a minute";
  }

  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;

  if (minutes <= 0) {
    return `Estimated remaining: ~${remainder}s`;
  }

  if (remainder === 0) {
    return `Estimated remaining: ~${minutes}m`;
  }

  return `Estimated remaining: ~${minutes}m ${remainder}s`;
}

function MarkdownContent({ content }: { content: string }) {
  const normalizedContent = normalizeMarkdownForPreview(content);

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => <h1 className="mb-2 text-lg font-semibold">{children}</h1>,
        h2: ({ children }) => <h2 className="mb-2 text-base font-semibold">{children}</h2>,
        h3: ({ children }) => <h3 className="mb-1 text-sm font-semibold">{children}</h3>,
        p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
        ul: ({ children }) => <ul className="mb-2 list-disc pl-5">{children}</ul>,
        ol: ({ children }) => <ol className="mb-2 list-decimal pl-5">{children}</ol>,
        li: ({ children }) => <li className="mb-1">{children}</li>,
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        table: ({ children }) => (
          <div className="mb-2 overflow-x-auto">
            <table className="min-w-full border-collapse text-left text-xs">{children}</table>
          </div>
        ),
        thead: ({ children }) => <thead className="bg-black/5">{children}</thead>,
        tbody: ({ children }) => <tbody>{children}</tbody>,
        tr: ({ children }) => <tr className="border-b border-black/10">{children}</tr>,
        th: ({ children }) => <th className="px-2 py-1 font-semibold">{children}</th>,
        td: ({ children }) => <td className="px-2 py-1 align-top">{children}</td>,
        code: ({ className, children, ...props }) => {
          const languageMatch = typeof className === "string" ? /language-([\w-]+)/.exec(className) : null;
          const language = languageMatch?.[1]?.toLowerCase();
          const codeText = String(children ?? "").replace(/\n$/, "");

          if (language === "mermaid") {
            return <MermaidBlock chart={codeText} />;
          }

          if (language) {
            return (
              <pre className="mb-2 overflow-x-auto rounded-md bg-black/90 p-3 text-xs text-white">
                <code className={className} {...props}>
                  {children}
                </code>
              </pre>
            );
          }

          return (
            <code className="rounded bg-black/10 px-1 py-0.5" {...props}>
              {children}
            </code>
          );
        },
      }}
    >
      {normalizedContent}
    </ReactMarkdown>
  );
}

function MermaidBlock({ chart }: { chart: string }) {
  const elementRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let mounted = true;

    async function render() {
      if (!elementRef.current) {
        return;
      }

      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({ startOnLoad: false, securityLevel: "loose" });
        await mermaid.parse(chart);
        const renderId = `mermaid-${Math.random().toString(36).slice(2)}`;
        const { svg } = await mermaid.render(renderId, chart);
        if (mounted && elementRef.current) {
          const lowerSvg = svg.toLowerCase();
          const hasMermaidErrorText =
            lowerSvg.includes("syntax error in text") ||
            lowerSvg.includes("mermaid version") ||
            lowerSvg.includes("parse error");

          if (hasMermaidErrorText) {
            elementRef.current.textContent = "Diagram unavailable.";
          } else {
            elementRef.current.innerHTML = svg;
          }
        }
      } catch {
        if (mounted && elementRef.current) {
          elementRef.current.textContent = "Diagram unavailable.";
        }
      }
    }

    void render();
    return () => {
      mounted = false;
    };
  }, [chart]);

  return <div ref={elementRef} className="mb-2 overflow-x-auto rounded-md bg-[color:var(--surface-lowest)] p-2 ring-1 ring-[color:var(--outline-variant)]/30" />;
}

function parseAssistantClarificationContent(content: string): {
  prompt?: string;
  questions: ClarificationQuestion[];
} | null {
  const trimmed = content.trim();
  if (!trimmed) {
    return null;
  }

  const candidateJson = [
    trimmed,
    trimmed.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim(),
  ];

  const extractJsonSegments = (text: string) => {
    const segments: string[] = [];
    for (let start = 0; start < text.length; start++) {
      const opener = text[start];
      if (opener !== "{" && opener !== "[") {
        continue;
      }

      let depth = 0;
      let inString = false;
      let escaping = false;

      for (let end = start; end < text.length; end++) {
        const char = text[end];

        if (escaping) {
          escaping = false;
          continue;
        }

        if (char === "\\") {
          escaping = true;
          continue;
        }

        if (char === '"') {
          inString = !inString;
          continue;
        }

        if (inString) {
          continue;
        }

        if (char === "{" || char === "[") {
          depth += 1;
        } else if (char === "}" || char === "]") {
          depth -= 1;
          if (depth === 0) {
            segments.push(text.slice(start, end + 1));
            break;
          }
        }
      }
    }
    return segments;
  };

  for (const segment of extractJsonSegments(trimmed)) {
    if (!candidateJson.includes(segment)) {
      candidateJson.push(segment);
    }
  }

  const looksLikeQuestionText = (text: string) => {
    const normalized = text.trim();
    if (!normalized) {
      return false;
    }

    return normalized.endsWith("?") || normalized.split(/\s+/).length >= 5;
  };

  const normalizeRecordQuestions = (record: Record<string, unknown>) => {
    return normalizeClarificationQuestions(record.questions ?? record.missing);
  };

  // Pass 1: strongly prefer object payloads with explicit questions/missing keys.
  for (const candidate of candidateJson) {
    try {
      const parsed = JSON.parse(candidate) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        continue;
      }

      const record = parsed as Record<string, unknown>;
      if (!("questions" in record) && !("missing" in record)) {
        continue;
      }

      const questions = normalizeRecordQuestions(record);
      if (questions.length === 0) {
        continue;
      }

      const prompt =
        typeof record.prompt === "string" && record.prompt.trim()
          ? record.prompt.trim()
          : undefined;

      return { prompt, questions };
    } catch {
      continue;
    }
  }

  // Pass 2: accept top-level array only if it clearly looks like question data.
  for (const candidate of candidateJson) {
    try {
      const parsed = JSON.parse(candidate) as unknown;

      if (Array.isArray(parsed)) {
        const objectsWithQuestion = parsed.filter(
          (item) =>
            !!item &&
            typeof item === "object" &&
            typeof (item as Record<string, unknown>).question === "string",
        );

        if (objectsWithQuestion.length > 0) {
          const questions = normalizeClarificationQuestions(parsed);
          if (questions.length > 0) {
            return { questions };
          }
        }

        const questionLikeStrings = parsed.filter(
          (item) => typeof item === "string" && looksLikeQuestionText(item),
        );

        if (questionLikeStrings.length > 0 && questionLikeStrings.length === parsed.length) {
          const questions = normalizeClarificationQuestions(parsed);
          if (questions.length > 0) {
            return { questions };
          }
        }

        continue;
      }

      if (!parsed || typeof parsed !== "object") {
        continue;
      }

      const record = parsed as Record<string, unknown>;
      const questions = normalizeRecordQuestions(record);
      if (questions.length === 0) {
        continue;
      }

      const prompt =
        typeof record.prompt === "string" && record.prompt.trim()
          ? record.prompt.trim()
          : undefined;

      return { prompt, questions };
    } catch {
      continue;
    }
  }

  return null;
}

function extractJsonSegments(text: string) {
  const segments: string[] = [];

  for (let start = 0; start < text.length; start++) {
    const opener = text[start];
    if (opener !== "{" && opener !== "[") {
      continue;
    }

    let depth = 0;
    let inString = false;
    let escaping = false;

    for (let end = start; end < text.length; end++) {
      const char = text[end];

      if (escaping) {
        escaping = false;
        continue;
      }

      if (char === "\\") {
        escaping = true;
        continue;
      }

      if (char === '"') {
        inString = !inString;
        continue;
      }

      if (inString) {
        continue;
      }

      if (char === "{" || char === "[") {
        depth += 1;
      } else if (char === "}" || char === "]") {
        depth -= 1;
        if (depth === 0) {
          segments.push(text.slice(start, end + 1));
          break;
        }
      }
    }
  }

  return segments;
}

function formatElicitationPayload(record: Record<string, unknown>) {
  const lines: string[] = [];

  const entities = Array.isArray(record.entities)
    ? record.entities.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
  if (entities.length > 0) {
    lines.push(`Entities: ${entities.join(", ")}`);
  }

  const workflows = Array.isArray(record.workflows)
    ? record.workflows.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
  if (workflows.length > 0) {
    lines.push("Workflows:");
    lines.push(...workflows.map((workflow) => `- ${workflow}`));
  }

  const constraints = Array.isArray(record.constraints_mentioned)
    ? record.constraints_mentioned.filter(
        (item): item is string => typeof item === "string" && item.trim().length > 0,
      )
    : [];
  if (constraints.length > 0) {
    lines.push("Constraints mentioned:");
    lines.push(...constraints.map((constraint) => `- ${constraint}`));
  }

  const platformHints = Array.isArray(record.platform_hints)
    ? record.platform_hints.filter(
        (item): item is string => typeof item === "string" && item.trim().length > 0,
      )
    : [];
  if (platformHints.length > 0) {
    lines.push(`Platform hints: ${platformHints.join(", ")}`);
  }

  const preliminary = record.preliminary_sections;
  if (preliminary && typeof preliminary === "object" && !Array.isArray(preliminary)) {
    lines.push("Preliminary sections detected.");
  }

  return lines.join("\n").trim();
}

function formatAssistantContent(content: string) {
  const clarification = parseAssistantClarificationContent(content);
  if (clarification) {
    return formatClarificationPrompt({
      prompt: clarification.prompt,
      questions: clarification.questions,
    });
  }

  const trimmed = content.trim();
  if (!trimmed) {
    return content;
  }

  const candidates = [trimmed, ...extractJsonSegments(trimmed)];
  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        continue;
      }

      const record = parsed as Record<string, unknown>;
      const elicitation = formatElicitationPayload(record);
      if (elicitation) {
        return elicitation;
      }
    } catch {
      continue;
    }
  }

  return content;
}

function ClarificationFormCard({
  questionMode,
  onAnswerChange,
  onOptionSelect,
  onSubmit,
  isSending,
}: {
  questionMode: QuestionMode;
  onAnswerChange: (index: number, value: string) => void;
  onOptionSelect: (index: number, value: string) => void;
  onSubmit: () => void;
  isSending: boolean;
}) {
  return (
    <div className="max-w-[90%] rounded-2xl bg-[color:var(--surface-highest)]/80 px-4 py-4 text-[color:var(--foreground)] ring-1 ring-[color:var(--outline-variant)]/35 backdrop-blur">
      {questionMode.introPrompt ? (
        <p className="mb-4 text-sm leading-relaxed">{questionMode.introPrompt}</p>
      ) : null}

      <div className="space-y-3">
        {questionMode.questions.map((question, index) => (
          <div
            key={`${question.question}-${index}`}
            className="rounded-xl bg-[color:var(--surface-lowest)] px-3 py-3 ring-1 ring-[color:var(--outline-variant)]/35"
          >
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[color:var(--on-surface-variant)]">
              Question {index + 1} of {questionMode.questions.length}
              {question.category ? ` · ${question.category}` : ""}
            </p>
            <p className="mt-1 text-sm font-medium leading-snug">{question.question}</p>

            {question.suggested_options && question.suggested_options.length > 0 ? (
              <div className="mt-2">
                <p className="mb-1 text-xs text-[color:var(--on-surface-variant)]">Suggested answers:</p>
                <div className="flex flex-wrap gap-1.5">
                  {question.suggested_options.map((option, optionIndex) => (
                    <button
                      key={`${option}-${optionIndex}`}
                      type="button"
                      onClick={() => onOptionSelect(index, option)}
                      className="rounded-full bg-[color:var(--surface-low)] px-2.5 py-0.5 text-xs ring-1 ring-[color:var(--outline-variant)]/35 transition-colors hover:bg-[color:var(--surface)]"
                    >
                      {option}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            <textarea
              value={questionMode.answers[index] || ""}
              onChange={(event) => onAnswerChange(index, event.target.value)}
              placeholder="Type your answer..."
              rows={3}
              className="mt-3 w-full rounded-md bg-[color:var(--surface-low)] px-3 py-2 text-sm ring-1 ring-[color:var(--outline-variant)]/40 outline-none focus:ring-2 focus:ring-[color:var(--primary)]"
              disabled={isSending}
            />

            {question.rationale ? (
              <p className="mt-2 text-xs text-[color:var(--on-surface-variant)] italic">{question.rationale}</p>
            ) : null}
          </div>
        ))}
      </div>

      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={onSubmit}
          disabled={isSending}
          className="rounded-md bg-[color:var(--primary)] px-4 py-2 text-sm text-white disabled:opacity-60"
        >
          {isSending ? "Sending..." : "Continue with answers"}
        </button>
      </div>
    </div>
  );
}

function ReceivingBubble({
  waitingOn,
  statuses,
  etaSeconds,
}: {
  waitingOn: string;
  statuses: BackendStatusEvent[];
  etaSeconds: number | null;
}) {
  const recentStatuses = statuses.slice(-3);

  return (
    <div className="max-w-[85%] rounded-2xl bg-[color:var(--surface-highest)]/80 px-4 py-3 text-[color:var(--foreground)] backdrop-blur">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 h-4 w-4 animate-spin rounded-full border-2 border-black/15 border-t-black" />
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[color:var(--on-surface-variant)]">
            Receiving SRS update
          </p>
          <p className="mt-1 text-sm leading-snug">Waiting on {waitingOn.toLowerCase()}.</p>
          <p className="mt-1 text-xs text-[color:var(--on-surface-variant)]">{formatEtaLabel(etaSeconds)}</p>
        </div>
      </div>

      {recentStatuses.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {recentStatuses.map((status) => (
            <span
              key={`${status.node}-${status.status}`}
              className="rounded-full bg-[color:var(--surface-lowest)] px-2.5 py-1 text-[11px] text-[color:var(--on-surface-variant)] ring-1 ring-[color:var(--outline-variant)]/35"
            >
              {getStatusLabel(status)}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function SelectedDraftBubble({
  part,
  onClear,
}: {
  part: DraftPart;
  onClear: () => void;
}) {
  return (
    <div className="max-w-[85%] rounded-2xl bg-[color:var(--surface-low)] px-4 py-3 text-[color:var(--foreground)] ring-1 ring-[color:var(--outline-variant)]/35">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[color:var(--on-surface-variant)]">
            Selected SRS part
          </p>
          <p className="mt-1 text-sm font-medium leading-snug">{part.title}</p>
        </div>
        <button
          type="button"
          onClick={onClear}
          className="rounded-full px-2 py-0.5 text-[11px] text-[color:var(--foreground)] ring-1 ring-[color:var(--outline-variant)]/40 transition-colors hover:bg-[color:var(--surface-lowest)]"
        >
          Clear
        </button>
      </div>
      <div className="mt-3 max-h-52 overflow-y-auto rounded-xl bg-[color:var(--surface-lowest)] px-3 py-2 text-xs leading-relaxed text-[color:var(--on-surface-variant)]">
        <MarkdownContent content={part.content} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChatWorkspace
// ---------------------------------------------------------------------------

export function ChatWorkspace({ userEmail }: { userEmail: string }) {
  const [chats, setChats] = useState<ChatListItem[]>([]);
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [documentText, setDocumentText] = useState<string>("");
  const [stateJson, setStateJson] = useState<Record<string, unknown> | null>(null);
  const [backendStatuses, setBackendStatuses] = useState<BackendStatusEvent[]>([]);
  const [liveSectionDrafts, setLiveSectionDrafts] = useState<Record<string, string>>({});
  const [questionMode, setQuestionMode] = useState<QuestionMode | null>(null);
  const [deletingChatId, setDeletingChatId] = useState<string | null>(null);
  const [activeBackendNode, setActiveBackendNode] = useState<string | null>(null);
  const [selectedDraftPart, setSelectedDraftPart] = useState<DraftPart | null>(null);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [isGeneratingDiagrams, setIsGeneratingDiagrams] = useState(false);
  const [isExportingDocx, setIsExportingDocx] = useState(false);
  const [activeRun, setActiveRun] = useState<ActiveRunSummary | null>(null);
  const [retryPayload, setRetryPayload] = useState<{
    chatId: string;
    message: string;
    revisionTarget?: RevisionTarget;
    options?: { generateDiagrams?: boolean; diagramsOnly?: boolean };
  } | null>(null);
  const runPollTimerRef = useRef<number | null>(null);
  const sectionStreamRef = useRef<EventSource | null>(null);

  // Ref used to hold the latest selectedChatId inside the sendToBackend closure.
  const selectedChatIdRef = useRef(selectedChatId);
  useEffect(() => {
    selectedChatIdRef.current = selectedChatId;
  }, [selectedChatId]);

  const activeBackendNodeRef = useRef(activeBackendNode);
  useEffect(() => {
    activeBackendNodeRef.current = activeBackendNode;
  }, [activeBackendNode]);

  const stopRunPolling = useCallback(() => {
    if (runPollTimerRef.current !== null) {
      window.clearTimeout(runPollTimerRef.current);
      runPollTimerRef.current = null;
    }
  }, []);

  const stopSectionStreaming = useCallback(() => {
    if (sectionStreamRef.current) {
      sectionStreamRef.current.close();
      sectionStreamRef.current = null;
    }
  }, []);

  const startSectionStreaming = useCallback(
    (chatId: string) => {
      stopSectionStreaming();

      const stream = new EventSource(`/api/chats/${chatId}/runs/active/stream`);
      sectionStreamRef.current = stream;

      stream.addEventListener("sections", (event) => {
        let payload: SectionStreamPayload = {};
        try {
          payload = JSON.parse((event as MessageEvent).data) as SectionStreamPayload;
        } catch {
          return;
        }

        if (payload.currentNode !== undefined) {
          setActiveBackendNode(payload.currentNode || null);
        }

        if (payload.etaSeconds !== undefined) {
          setActiveRun((prev) =>
            prev
              ? {
                  ...prev,
                  etaSeconds: payload.etaSeconds ?? null,
                  currentNode:
                    payload.currentNode !== undefined
                      ? (payload.currentNode ?? null)
                      : prev.currentNode,
                }
              : prev,
          );
        }

        if (payload.sections && typeof payload.sections === "object") {
          setLiveSectionDrafts((prev) => ({
            ...prev,
            ...payload.sections,
          }));
        }
      });

      stream.addEventListener("done", () => {
        stopSectionStreaming();
      });

      stream.addEventListener("error", () => {
        stopSectionStreaming();
      });
    },
    [stopSectionStreaming],
  );

  const pollActiveRun = useCallback(
    async (chatId: string) => {
      stopRunPolling();

      try {
        const response = await fetch(`/api/chats/${chatId}/runs/active`, {
          cache: "no-store",
        });

        if (!response.ok) {
          throw new Error("Failed to fetch active generation status.");
        }

        const payload = (await response.json()) as { run: ActiveRunSummary | null };
        const run = payload.run;
        setActiveRun(run);

        if (run?.chatTitle && run.chatTitle.trim()) {
          setChats((prev) =>
            prev.map((chat) =>
              chat.id === chatId ? { ...chat, title: run.chatTitle as string } : chat,
            ),
          );
        }

        if (!run) {
          stopSectionStreaming();
          setIsSending(false);
          setIsGeneratingDiagrams(false);
          setActiveBackendNode(null);
          setBackendStatuses([]);

          if (selectedChatIdRef.current === chatId) {
            const detailsResponse = await fetch(`/api/chats/${chatId}/messages`, {
              cache: "no-store",
            });

            if (detailsResponse.ok && selectedChatIdRef.current === chatId) {
              const detailsPayload = (await detailsResponse.json()) as ChatDetails;
              setMessages(detailsPayload.chat.messages);
              setDocumentText(detailsPayload.chat.currentDocument || "");
              setStateJson(detailsPayload.chat.stateJson || null);
              setLiveSectionDrafts({});
              setQuestionMode(null);
              setSelectedDraftPart(null);
            }
          }

          return;
        }

        setBackendStatuses(run.statuses || []);
        setActiveBackendNode(run.currentNode || null);
        if (run.liveSections && Object.keys(run.liveSections).length > 0) {
          setLiveSectionDrafts((prev) => ({
            ...prev,
            ...run.liveSections,
          }));
        }

        if (run.status === "RUNNING") {
          if (!sectionStreamRef.current) {
            startSectionStreaming(chatId);
          }
          setIsSending(true);
          runPollTimerRef.current = window.setTimeout(() => {
            void pollActiveRun(chatId);
          }, 2000);
          return;
        }

        stopSectionStreaming();
        setIsSending(false);
        setIsGeneratingDiagrams(false);
        setActiveBackendNode(null);

        if (run.status === "FAILED") {
          setError(run.errorMessage || "Failed to send message.");
          setRetryPayload((prev) => prev);
          return;
        }

        if (run.status === "NEEDS_INPUT" && run.questions.length > 0) {
          setQuestionMode({
            introPrompt:
              run.questionPrompt || "I need a few clarifications before drafting the SRS.",
            questions: run.questions,
            answers: run.questions.map(() => ""),
          });
        }

        await loadChatDetails(chatId);
      } catch (caughtError) {
        const message =
          caughtError instanceof Error
            ? caughtError.message
            : "Failed to fetch active generation status.";
        setError(message);
        setIsSending(false);
        setIsGeneratingDiagrams(false);
      }
    },
    [startSectionStreaming, stopRunPolling, stopSectionStreaming],
  );

  // Scroll-to-bottom ref
  const messagesEndRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, questionMode]);

  const selectedChat = useMemo(
    () => chats.find((chat) => chat.id === selectedChatId) ?? null,
    [chats, selectedChatId],
  );

  const loadChats = useCallback(async () => {
    setIsLoading(true);
    setError("");

    try {
      const response = await fetch("/api/chats", { cache: "no-store" });
      if (!response.ok) {
        throw new Error("Failed to load chats.");
      }

      const payload = await response.json();
      const nextChats = payload.chats as ChatListItem[];
      setChats(nextChats);

      if (nextChats.length > 0) {
        const initialId = selectedChatId ?? nextChats[0].id;
        setSelectedChatId(initialId);
        await loadChatDetails(initialId);
      }
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Failed to load chats.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [selectedChatId]);

  useEffect(() => {
    void loadChats();
  }, [loadChats]);

  async function createChat() {
    stopRunPolling();
    stopSectionStreaming();
    setError("");

    try {
      const response = await fetch("/api/chats", { method: "POST" });
      if (!response.ok) {
        throw new Error("Failed to create chat.");
      }

      const payload = await response.json();
      const newChat = payload.chat as ChatListItem;
      setChats((prev) => [newChat, ...prev]);
      setSelectedChatId(newChat.id);
      setMessages([]);
      setDocumentText("");
      setStateJson(null);
      setBackendStatuses([]);
      setLiveSectionDrafts({});
      setQuestionMode(null);
      setActiveBackendNode(null);
      setSelectedDraftPart(null);
      setActiveRun(null);
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Failed to create chat.";
      setError(message);
    }
  }

  async function loadChatDetails(chatId: string) {
    stopRunPolling();
    stopSectionStreaming();
    setError("");

    try {
      const response = await fetch(`/api/chats/${chatId}/messages`, {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error("Failed to load messages.");
      }

      const payload = (await response.json()) as ChatDetails;
      setMessages(payload.chat.messages);
      setDocumentText(payload.chat.currentDocument || "");
      setStateJson(payload.chat.stateJson || null);
      setBackendStatuses([]);
      setLiveSectionDrafts({});
      setQuestionMode(null);
      setActiveBackendNode(null);
      setSelectedDraftPart(null);

      const runResponse = await fetch(`/api/chats/${chatId}/runs/active`, {
        cache: "no-store",
      });

      if (runResponse.ok) {
        const runPayload = (await runResponse.json()) as { run: ActiveRunSummary | null };
        const run = runPayload.run;
        setActiveRun(run);

        if (run?.status === "RUNNING") {
          setIsSending(true);
          setBackendStatuses(run.statuses || []);
          setActiveBackendNode(run.currentNode || null);
          setLiveSectionDrafts(run.liveSections || {});
          startSectionStreaming(chatId);
          void pollActiveRun(chatId);
        } else if (run?.status === "NEEDS_INPUT" && run.questions.length > 0) {
          setQuestionMode({
            introPrompt:
              run.questionPrompt || "I need a few clarifications before drafting the SRS.",
            questions: run.questions,
            answers: run.questions.map(() => ""),
          });
        }
      } else {
        setActiveRun(null);
        setIsGeneratingDiagrams(false);
      }
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Failed to load messages.";
      setError(message);
    }
  }

  async function deleteChat(chatId: string) {
    stopRunPolling();
    if (deletingChatId) {
      return;
    }

    setDeletingChatId(chatId);
    setError("");

    try {
      const response = await fetch(`/api/chats/${chatId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Failed to delete chat.");
      }

      const remainingChats = chats.filter((chat) => chat.id !== chatId);
      setChats(remainingChats);

      if (selectedChatId === chatId) {
        const nextChat = remainingChats[0] ?? null;
        setSelectedChatId(nextChat?.id ?? null);

        if (nextChat) {
          await loadChatDetails(nextChat.id);
        } else {
          setMessages([]);
          setDocumentText("");
          setStateJson(null);
          setBackendStatuses([]);
          setLiveSectionDrafts({});
          setQuestionMode(null);
          setActiveBackendNode(null);
          setSelectedDraftPart(null);
        }
      }
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Failed to delete chat.";
      setError(message);
    } finally {
      setDeletingChatId(null);
    }
  }

  // ---------------------------------------------------------------------------
  // Core send function — shared by initial submission and question-answer send.
  // ---------------------------------------------------------------------------

  async function handleRetry() {
    if (!retryPayload || isSending) return;
    const { chatId, message, revisionTarget, options } = retryPayload;
    setRetryPayload(null);
    setError("");
    await sendToBackend(chatId, message, revisionTarget, options);
  }

  async function sendToBackend(
    chatId: string,
    messageText: string,
    revisionTarget?: RevisionTarget,
    options?: { generateDiagrams?: boolean; diagramsOnly?: boolean },
  ) {
    const initialNode = options?.diagramsOnly
      ? "generate_mermaid"
      : revisionTarget
        ? "revise_selected_section"
        : "retrieve_rag_context";

    setIsSending(true);
    setIsGeneratingDiagrams(Boolean(options?.diagramsOnly));
    setError("");
    setRetryPayload(null);
    setBackendStatuses([{ node: initialNode, status: "started" }]);
    setLiveSectionDrafts({});
    setActiveBackendNode(initialNode);
    setActiveRun(null);

    const optimisticMessage: ChatMessage = {
      id: `optimistic-${Date.now()}`,
      role: "USER",
      content: revisionTarget
        ? `[Selected section: ${revisionTarget.title}]\n${messageText}`
        : messageText,
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticMessage]);

    try {
      const response = await fetch(`/api/chats/${chatId}/interact`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          revisionTarget
            ? {
                message: messageText,
                revisionTarget,
                generateDiagrams: options?.generateDiagrams,
                diagramsOnly: options?.diagramsOnly,
              }
            : {
                message: messageText,
                generateDiagrams: options?.generateDiagrams,
                diagramsOnly: options?.diagramsOnly,
              },
        ),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        const responseError =
          payload && typeof payload === "object" && "error" in payload
            ? String((payload as { error?: unknown }).error || "")
            : "";
        throw new Error(responseError || "Failed to send message.");
      }

      const payload = (await response.json()) as { run?: ActiveRunSummary | null };
      const run = payload.run ?? null;
      setActiveRun(run);

      if (run) {
        setBackendStatuses(run.statuses || []);
        setActiveBackendNode(run.currentNode || null);
        if (run.status === "RUNNING") {
          startSectionStreaming(chatId);
        }
        await pollActiveRun(chatId);
      } else {
        await loadChatDetails(chatId);
      }
    } catch (caughtError) {
      setMessages((prev) => prev.filter((message) => message.id !== optimisticMessage.id));
      setActiveBackendNode(null);
      const message =
        caughtError instanceof Error ? caughtError.message : "Failed to send message.";
      setError(message);
      setRetryPayload({ chatId, message: messageText, revisionTarget, options });
      setIsSending(false);
      setIsGeneratingDiagrams(false);
    }
  }

  async function handleGenerateDiagrams() {
    const chatId = selectedChatIdRef.current;
    if (!chatId || isSending || isGeneratingDiagrams) {
      return;
    }

    if (questionMode !== null) {
      setError("Please answer all clarification questions before generating diagrams.");
      return;
    }

    if (hasGeneratedDiagrams) {
      const confirmed = window.confirm(
        "Diagrams have already been generated for this draft. Generate them again and replace the existing diagrams?",
      );
      if (!confirmed) {
        return;
      }
    }

    await sendToBackend(
      chatId,
      "Generate and append Mermaid diagrams for the current SRS draft.",
      undefined,
      { generateDiagrams: true, diagramsOnly: true },
    );
  }

  // ---------------------------------------------------------------------------
  // Form submit
  // ---------------------------------------------------------------------------

  function handleClarificationAnswerChange(index: number, value: string) {
    setQuestionMode((prev) => {
      if (!prev) {
        return prev;
      }

      const nextAnswers = [...prev.answers];
      nextAnswers[index] = value;
      return { ...prev, answers: nextAnswers };
    });
  }

  async function submitClarificationAnswers() {
    if (!questionMode || isSending) {
      return;
    }

    const sanitizedAnswers = questionMode.answers.map((answer) => answer.trim());
    const firstMissing = sanitizedAnswers.findIndex((answer) => !answer);
    if (firstMissing >= 0) {
      setError(`Please answer question ${firstMissing + 1} before continuing.`);
      return;
    }

    const compiled = questionMode.questions
      .map((question, index) => `Q: ${question.question}\nA: ${sanitizedAnswers[index]}`)
      .join("\n\n");

    const chatId = selectedChatIdRef.current;
    if (!chatId) {
      return;
    }

    setError("");
    setQuestionMode(null);
    await sendToBackend(chatId, compiled);
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (questionMode !== null) {
      setError("Use the clarification form above to answer follow-up questions.");
      return;
    }

    const inputValue = input.trim();
    if (!inputValue) return;

    // Normal submit
    if (!selectedChatId || isSending) return;
    const revisionTarget = selectedDraftPart
      ? {
          title: selectedDraftPart.title,
          content: selectedDraftPart.content,
          sectionKey: selectedDraftPart.sectionKey,
        }
      : undefined;
    setInput("");
    if (revisionTarget) {
      setSelectedDraftPart(null);
    }
    await sendToBackend(selectedChatId, inputValue, revisionTarget);
  }

  async function onLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
  }

  async function handleDownloadDocx() {
    const chatId = selectedChatIdRef.current;
    if (!chatId || isExportingDocx) {
      return;
    }

    setError("");
    setIsExportingDocx(true);

    try {
      const response = await fetch(`/api/chats/${chatId}/export/docx`, {
        method: "GET",
        cache: "no-store",
      });

      const contentType = response.headers.get("content-type") || "";

      if (
        !response.ok ||
        response.status !== 200 ||
        !contentType.includes(
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
      ) {
        const payload = await response.json().catch(() => null);
        const responseError =
          payload && typeof payload === "object" && "error" in payload
            ? String((payload as { error?: unknown }).error || "")
            : "";
        throw new Error(responseError || "Failed to export DOCX.");
      }

      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") || "";
      const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
      const filename = filenameMatch?.[1] || "srs-document.docx";

      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Failed to export DOCX.";
      setError(message);
    } finally {
      setIsExportingDocx(false);
    }
  }

  // When question mode is active, hide the last ASSISTANT message from the DB
  // since it contains the same questions that are already shown as interactive
  // bubbles below.
  const visibleMessages = useMemo(() => {
    if (questionMode === null) return messages;
    const lastAssistantIdx = messages.reduce(
      (acc, msg, i) => (msg.role === "ASSISTANT" ? i : acc),
      -1,
    );
    return lastAssistantIdx >= 0 ? messages.filter((_, i) => i !== lastAssistantIdx) : messages;
  }, [messages, questionMode]);

  const displayMessages = useMemo(
    () =>
      visibleMessages.map((message) => {
        if (message.role !== "ASSISTANT") {
          return message;
        }

        return {
          ...message,
          content: formatAssistantContent(message.content),
        };
      }),
    [visibleMessages],
  );

  const draftedSections = useMemo(() => {
    const sectionMap = new Map<string, string>();

    if (stateJson && typeof stateJson === "object") {
      const sections = (stateJson as Record<string, unknown>).sections;
      if (sections && typeof sections === "object" && !Array.isArray(sections)) {
        for (const [key, value] of Object.entries(sections as Record<string, unknown>)) {
          if (typeof value === "string") {
            const trimmed = value.trim();
            if (trimmed) {
              sectionMap.set(key, trimmed);
            }
            continue;
          }

          try {
            sectionMap.set(key, JSON.stringify(value, null, 2));
          } catch {
            sectionMap.set(key, String(value));
          }
        }
      }
    }

    for (const [key, value] of Object.entries(liveSectionDrafts)) {
      const trimmed = value.trim();
      if (trimmed) {
        sectionMap.set(key, trimmed);
      }
    }

    return Array.from(sectionMap.entries())
      .map(([key, content]) => ({ key, content }))
      .filter((entry) => entry.content.length > 0)
      .sort((first, second) => SECTION_ORDER.indexOf(first.key) - SECTION_ORDER.indexOf(second.key));
  }, [stateJson, liveSectionDrafts]);

  const draftSections = useMemo(
    () =>
      draftedSections.map((section) => {
        const parts = extractDraftParts(section.key, section.content).filter((part) =>
          hasDraftPartBodyContent(part.content),
        );

        return {
          ...section,
          title: formatSectionTitle(section.key),
          parts,
        };
      }),
    [draftedSections],
  );

  const allDraftParts = useMemo(
    () => draftSections.flatMap((section) => section.parts),
    [draftSections],
  );

  const shouldShowDraftingPlaceholders = useMemo(
    () => isSending || activeRun?.status === "RUNNING",
    [isSending, activeRun?.status],
  );

  const visibleDraftSections = useMemo(
    () =>
      draftSections.filter(
        (section) => section.parts.length > 0 || shouldShowDraftingPlaceholders,
      ),
    [draftSections, shouldShowDraftingPlaceholders],
  );

  const hasRenderableDraftParts = useMemo(
    () => draftSections.some((section) => section.parts.length > 0),
    [draftSections],
  );

  useEffect(() => {
    if (!selectedDraftPart) {
      return;
    }

    const nextMatch = allDraftParts.find((part) => part.id === selectedDraftPart.id);
    if (!nextMatch) {
      setSelectedDraftPart(null);
      return;
    }

    if (
      nextMatch.title !== selectedDraftPart.title ||
      nextMatch.content !== selectedDraftPart.content ||
      nextMatch.preview !== selectedDraftPart.preview
    ) {
      setSelectedDraftPart(nextMatch);
    }
  }, [allDraftParts, selectedDraftPart]);

  const resolvedDocumentText = useMemo(
    () => documentText || buildDraftDocument(draftedSections),
    [documentText, draftedSections],
  );

  const hasGeneratedDiagrams = useMemo(() => {
    const stateHasMermaidBlocks =
      !!stateJson &&
      typeof stateJson === "object" &&
      !Array.isArray(stateJson) &&
      Array.isArray((stateJson as Record<string, unknown>).mermaid_blocks) &&
      ((stateJson as Record<string, unknown>).mermaid_blocks as unknown[]).some(
        (item) => typeof item === "string" && item.trim().length > 0,
      );

    if (stateHasMermaidBlocks) {
      return true;
    }

    return /```mermaid\s*\n/i.test(resolvedDocumentText);
  }, [stateJson, resolvedDocumentText]);

  const waitingOnLabel = useMemo(
    () => getWaitingOnLabel(backendStatuses, activeBackendNode),
    [backendStatuses, activeBackendNode],
  );

  useEffect(() => {
    return () => {
      stopRunPolling();
      stopSectionStreaming();
    };
  }, [stopRunPolling, stopSectionStreaming]);

  return (
    <div className="flex h-screen flex-col bg-[color:var(--surface)]">
      <header className="flex items-center justify-between border-b border-[color:var(--outline-variant)]/35 bg-[color:var(--surface-lowest)] px-4 py-3">
        <div>
          <h1 className="font-headline text-lg font-semibold text-[color:var(--primary)]">SRS Chat Workspace</h1>
          <p className="text-xs text-[color:var(--on-surface-variant)]">{userEmail}</p>
        </div>
        <button
          onClick={onLogout}
          className="rounded-md px-3 py-1.5 text-sm ring-1 ring-[color:var(--outline-variant)]/50"
        >
          Logout
        </button>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[260px_1fr_420px]">
        {/* ── Sidebar: chat list ── */}
        <aside className="flex min-h-0 flex-col border-r border-[color:var(--outline-variant)]/35 bg-[color:var(--surface-low)]">
          <div className="flex items-center justify-between p-3">
            <h2 className="text-sm font-semibold text-[color:var(--primary)]">Previous chats</h2>
            <button
              onClick={createChat}
              className="rounded-md bg-[color:var(--primary)] px-2 py-1 text-xs text-white"
            >
              New
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
            {isLoading ? <p className="px-1 text-sm text-[color:var(--on-surface-variant)]">Loading...</p> : null}
            {chats.length === 0 && !isLoading ? (
              <p className="px-1 text-sm text-[color:var(--on-surface-variant)]">No chats yet. Create one.</p>
            ) : null}

            {chats.map((chat) => {
              const isActive = chat.id === selectedChatId;
              return (
                <div
                  key={chat.id}
                  className={`mb-2 flex items-start gap-2 rounded-md px-2 py-2 ring-1 ${
                    isActive
                      ? "bg-[color:var(--primary)] text-white ring-[color:var(--primary)]"
                      : "bg-[color:var(--surface-lowest)] ring-[color:var(--outline-variant)]/35"
                  }`}
                >
                  <button
                    onClick={() => {
                      setSelectedChatId(chat.id);
                      void loadChatDetails(chat.id);
                    }}
                    className={`min-w-0 flex-1 text-left ${isActive ? "text-white" : "text-[color:var(--foreground)]"}`}
                  >
                    <p className="truncate text-sm font-medium">{chat.title || "Untitled"}</p>
                    <p className={`mt-1 text-xs ${isActive ? "text-white/70" : "text-[color:var(--on-surface-variant)]"}`}>
                      {new Date(chat.updatedAt).toLocaleString()}
                    </p>
                  </button>
                  <button
                    type="button"
                    onClick={() => void deleteChat(chat.id)}
                    disabled={deletingChatId === chat.id}
                    className={`rounded px-2 py-1 text-xs ${
                      isActive
                        ? "text-white/80 hover:bg-white/10"
                        : "text-[color:var(--on-surface-variant)] hover:bg-[color:var(--surface-low)]"
                    } disabled:opacity-40`}
                    aria-label={`Delete ${chat.title || "chat"}`}
                    title="Delete chat"
                  >
                    {deletingChatId === chat.id ? "..." : "✕"}
                  </button>
                </div>
              );
            })}
          </div>
        </aside>

        {/* ── Main chat area ── */}
        <main className="flex min-h-0 flex-col border-r border-[color:var(--outline-variant)]/35 bg-[color:var(--surface-lowest)]">
          <div className="border-b border-[color:var(--outline-variant)]/35 px-4 py-3">
            <h2 className="text-sm font-semibold text-[color:var(--primary)]">Interactive Generation</h2>
            <p className="text-xs text-[color:var(--on-surface-variant)]">
              {selectedChat ? selectedChat.title : "Select or create a chat"}
            </p>
          </div>

          {/* Messages */}
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
            {displayMessages.map((message) => (
              <div
                key={message.id}
                className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                  message.role === "USER"
                    ? "ml-auto bg-[color:var(--primary)] text-white"
                    : "bg-[color:var(--surface-highest)]/80 text-[color:var(--foreground)] backdrop-blur"
                }`}
              >
                {message.role === "ASSISTANT" ? (
                  <MarkdownContent content={message.content} />
                ) : (
                  message.content
                )}
              </div>
            ))}

            {/* Clarification form mode */}
            {questionMode !== null ? (
              <ClarificationFormCard
                questionMode={questionMode}
                onAnswerChange={handleClarificationAnswerChange}
                onOptionSelect={handleClarificationAnswerChange}
                onSubmit={() => {
                  void submitClarificationAnswers();
                }}
                isSending={isSending}
              />
            ) : null}

            {selectedDraftPart !== null && questionMode === null ? (
              <SelectedDraftBubble
                part={selectedDraftPart}
                onClear={() => setSelectedDraftPart(null)}
              />
            ) : null}

            {isSending ? (
              <ReceivingBubble
                waitingOn={waitingOnLabel}
                statuses={backendStatuses}
                etaSeconds={activeRun?.etaSeconds ?? null}
              />
            ) : null}

            {visibleMessages.length === 0 && questionMode === null ? (
              <p className="text-sm text-[color:var(--on-surface-variant)]">Start by asking about your product idea.</p>
            ) : null}

            <div ref={messagesEndRef} />
          </div>

          {/* Input form */}
          <form onSubmit={onSubmit} className="border-t border-[color:var(--outline-variant)]/35 p-3">
            {selectedDraftPart !== null && questionMode === null ? (
              <div className="mb-2 flex items-center justify-between gap-3 rounded-xl bg-[color:var(--surface-low)] px-3 py-2 text-xs text-[color:var(--foreground)] ring-1 ring-[color:var(--outline-variant)]/35">
                <p className="min-w-0 truncate">
                  Editing target: <span className="font-semibold">{selectedDraftPart.title}</span>
                </p>
                <button
                  type="button"
                  onClick={() => setSelectedDraftPart(null)}
                  className="rounded-full px-2 py-0.5 ring-1 ring-[color:var(--outline-variant)]/40 transition-colors hover:bg-[color:var(--surface-lowest)]"
                >
                  Clear
                </button>
              </div>
            ) : null}

            <div className="flex gap-2">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder={
                  questionMode !== null
                    ? "Answer the clarification form above to continue..."
                    : selectedDraftPart !== null
                      ? `Describe how to revise \"${selectedDraftPart.title}\"...`
                      : "Describe the software you want to build..."
                }
                className="w-full rounded-md bg-[color:var(--surface-low)] px-3 py-2 text-sm ring-1 ring-[color:var(--outline-variant)]/40 outline-none focus:ring-2 focus:ring-[color:var(--primary)]"
                disabled={!selectedChatId || isSending || questionMode !== null}
              />
              <button
                type="submit"
                disabled={!selectedChatId || isSending || questionMode !== null || !input.trim()}
                className="rounded-md bg-[color:var(--primary)] px-4 py-2 text-sm text-white disabled:opacity-60"
              >
                {isSending ? "Sending..." : "Send"}
              </button>
            </div>
            {error ? (
              <div className="mt-2 flex items-center gap-2">
                <p className="text-sm text-red-600">{error}</p>
                {retryPayload && !isSending ? (
                  <button
                    type="button"
                    onClick={() => void handleRetry()}
                    className="rounded-md border border-red-300 px-2.5 py-1 text-xs text-red-700 transition-colors hover:bg-red-50"
                  >
                    Retry
                  </button>
                ) : null}
              </div>
            ) : null}
          </form>
        </main>

        {/* ── Right sidebar: document / state ── */}
        <aside className="min-h-0 overflow-y-auto bg-[color:var(--surface-container)] p-4">
          <h2 className="text-sm font-semibold text-[color:var(--primary)]">SRS draft</h2>
          <p className="mt-1 text-xs text-[color:var(--on-surface-variant)]">
            Click a section or requirement to send a targeted revision request through chat.
          </p>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsPreviewOpen(true)}
              className="rounded-md bg-[color:var(--surface-lowest)] px-3 py-1.5 text-xs font-medium text-[color:var(--foreground)] ring-1 ring-[color:var(--outline-variant)]/35 hover:bg-[color:var(--surface-low)]"
            >
              Open document preview
            </button>
            <button
              type="button"
              onClick={() => void handleGenerateDiagrams()}
              disabled={!selectedChatId || isSending || isGeneratingDiagrams || !hasRenderableDraftParts || questionMode !== null}
              className="rounded-md bg-[color:var(--surface-lowest)] px-3 py-1.5 text-xs font-medium text-[color:var(--foreground)] ring-1 ring-[color:var(--outline-variant)]/35 hover:bg-[color:var(--surface-low)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isGeneratingDiagrams ? "Generating diagrams…" : "Generate diagrams"}
            </button>
          </div>

          <div className="mt-3 space-y-3">
            {visibleDraftSections.length === 0 ? (
              <div className="rounded-md bg-[color:var(--surface-lowest)] p-3 text-xs text-[color:var(--on-surface-variant)] ring-1 ring-[color:var(--outline-variant)]/35">
                No drafted sections yet.
              </div>
            ) : (
              visibleDraftSections.map((section) => (
                <div key={section.key} className="rounded-md bg-[color:var(--surface-lowest)] p-3 ring-1 ring-[color:var(--outline-variant)]/35">
                  <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-[color:var(--on-surface-variant)]">
                    {section.title}
                  </h3>

                  <div className="mt-2 space-y-2">
                    {section.parts.length === 0 ? (
                      <p className="text-xs text-[color:var(--on-surface-variant)]">
                        Drafting content for this section...
                      </p>
                    ) : (
                      section.parts.map((part, partIndex) => {
                        const isSelected = selectedDraftPart?.id === part.id;
                        const mermaidChart = extractFirstMermaidChart(part.content);

                        return (
                          <button
                            key={`${part.id}-${partIndex}`}
                            type="button"
                            onClick={() => setSelectedDraftPart(part)}
                            disabled={questionMode !== null || isSending}
                            className={`block w-full rounded-xl border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                              isSelected
                                ? "bg-[color:var(--surface-low)] ring-[color:var(--primary)]/45"
                                : "bg-[color:var(--surface-low)] ring-[color:var(--outline-variant)]/30 hover:bg-[color:var(--surface-lowest)]"
                            }`}
                          >
                            <p className="text-xs font-medium text-[color:var(--foreground)]">{part.title}</p>
                            <p className="mt-1 max-h-16 overflow-hidden text-xs leading-relaxed text-[color:var(--on-surface-variant)]">
                              {part.preview}
                            </p>
                            {mermaidChart ? (
                              <div className="mt-2 pointer-events-none rounded-lg bg-[color:var(--surface-lowest)] p-2 ring-1 ring-[color:var(--outline-variant)]/35">
                                <MermaidBlock chart={mermaidChart} />
                              </div>
                            ) : null}
                          </button>
                        );
                      })
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

        </aside>
      </div>

      {isPreviewOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4">
          <div className="flex h-[85vh] w-full max-w-5xl flex-col rounded-xl bg-[color:var(--surface-lowest)] shadow-xl">
            <div className="flex items-center justify-between border-b border-[color:var(--outline-variant)]/35 px-4 py-3">
              <h3 className="text-sm font-semibold">
                Document preview
              </h3>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleDownloadDocx()}
                  disabled={isExportingDocx || !selectedChatId}
                  className="rounded-md px-3 py-1 text-xs ring-1 ring-[color:var(--outline-variant)]/45 hover:bg-[color:var(--surface-low)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isExportingDocx ? "Exporting…" : "Download .docx"}
                </button>
                <button
                  type="button"
                  onClick={() => setIsPreviewOpen(false)}
                  className="rounded-md px-3 py-1 text-xs ring-1 ring-[color:var(--outline-variant)]/45 hover:bg-[color:var(--surface-low)]"
                >
                  Close
                </button>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-auto px-4 py-3 text-sm text-[color:var(--foreground)]">
              <MarkdownContent
                content={
                  resolvedDocumentText ||
                  "The draft SRS document will appear here once sections are available."
                }
              />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
