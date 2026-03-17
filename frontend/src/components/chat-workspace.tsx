"use client";

import { Fragment, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  consumeSseResponse,
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

type InteractResponse = {
  chat: {
    id: string;
    title: string;
    currentDocument: string | null;
    stateJson: Record<string, unknown> | null;
    updatedAt: string;
  };
  messages: ChatMessage[];
  questionPrompt?: string;
  questions?: ClarificationQuestion[];
  statuses?: BackendStatusEvent[];
};

type QuestionMode = {
  introPrompt: string;
  questions: ClarificationQuestion[];
  currentIdx: number;
  answered: string[];
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
// Keep legacy alias so getWaitingOnLabel still compiles
const SECTION_THREE_NODES = PARALLEL_DRAFT_NODES;
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
  elicit_requirements: "Extracted the initial product outline",
  evaluate_completeness: "Audited the brief for missing requirements",
  ask_clarifying_questions: "Prepared follow-up questions",
  classify_requirements: "Classified requirements",
  draft_section_3_fr: "Drafted functional requirements",
  draft_section_3_nfr: "Drafted non-functional requirements",
  draft_section_3_iface: "Drafted interface requirements",
  draft_section_1: "Drafted introduction",
  draft_section_2: "Drafted product overview",
  draft_section_4: "Built verification matrix",
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
    .map((section) => section.content.trim())
    .filter(Boolean)
    .join("\n\n");
}

function extractDraftParts(sectionKey: string, content: string): DraftPart[] {
  const trimmedContent = content.trim();
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
        preview: trimmedContent.replace(/\s+/g, " ").slice(0, 180),
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
      preview: partContent.replace(/\s+/g, " ").slice(0, 180),
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
          preview: trimmedContent.replace(/\s+/g, " ").slice(0, 180),
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

function MarkdownContent({ content }: { content: string }) {
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
        code: ({ children }) => <code className="rounded bg-black/10 px-1 py-0.5">{children}</code>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
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

// ---------------------------------------------------------------------------
// QuestionBubble
// ---------------------------------------------------------------------------

function QuestionBubble({
  question,
  number,
  total,
  onOptionSelect,
}: {
  question: ClarificationQuestion;
  number: number;
  total: number;
  onOptionSelect?: (opt: string) => void;
}) {
  return (
    <div className="max-w-[85%] rounded-lg bg-zinc-100 px-4 py-3 text-sm text-black">
      <p className="mb-2 text-xs font-medium text-black/45 uppercase tracking-[0.14em]">
        Question {number} of {total}
        {question.category ? ` · ${question.category}` : ""}
      </p>
      <p className="font-medium leading-snug">{question.question}</p>

      {question.suggested_options && question.suggested_options.length > 0 ? (
        <div className="mt-3">
          <p className="mb-1.5 text-xs text-black/50">Suggested answers — click to use:</p>
          <div className="flex flex-wrap gap-1.5">
            {question.suggested_options.map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => onOptionSelect?.(opt)}
                className="rounded-full border border-black/15 bg-white px-2.5 py-0.5 text-xs hover:border-black/30 hover:bg-black/5 transition-colors"
              >
                {opt}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {question.rationale ? (
        <p className="mt-2 text-xs text-black/45 italic">{question.rationale}</p>
      ) : null}
    </div>
  );
}

function ReceivingBubble({
  waitingOn,
  statuses,
}: {
  waitingOn: string;
  statuses: BackendStatusEvent[];
}) {
  const recentStatuses = statuses.slice(-3);

  return (
    <div className="max-w-[85%] rounded-2xl bg-zinc-100 px-4 py-3 text-black">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 h-4 w-4 animate-spin rounded-full border-2 border-black/15 border-t-black" />
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-black/45">
            Receiving SRS update
          </p>
          <p className="mt-1 text-sm leading-snug">Waiting on {waitingOn.toLowerCase()}.</p>
        </div>
      </div>

      {recentStatuses.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {recentStatuses.map((status) => (
            <span
              key={`${status.node}-${status.status}`}
              className="rounded-full bg-white px-2.5 py-1 text-[11px] text-black/65 ring-1 ring-black/10"
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
    <div className="max-w-[85%] rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-black">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-amber-900/70">
            Selected SRS part
          </p>
          <p className="mt-1 text-sm font-medium leading-snug">{part.title}</p>
        </div>
        <button
          type="button"
          onClick={onClear}
          className="rounded-full border border-amber-300 px-2 py-0.5 text-[11px] text-amber-950 transition-colors hover:bg-amber-100"
        >
          Clear
        </button>
      </div>
      <div className="mt-3 max-h-52 overflow-y-auto whitespace-pre-wrap rounded-xl bg-white/75 px-3 py-2 text-xs leading-relaxed text-black/80">
        {part.content}
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
  const [retryPayload, setRetryPayload] = useState<{
    chatId: string;
    message: string;
    revisionTarget?: RevisionTarget;
  } | null>(null);

  // Ref used to hold the latest selectedChatId inside the sendToBackend closure.
  const selectedChatIdRef = useRef(selectedChatId);
  useEffect(() => {
    selectedChatIdRef.current = selectedChatId;
  }, [selectedChatId]);

  const activeBackendNodeRef = useRef(activeBackendNode);
  useEffect(() => {
    activeBackendNodeRef.current = activeBackendNode;
  }, [activeBackendNode]);

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
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Failed to create chat.";
      setError(message);
    }
  }

  async function loadChatDetails(chatId: string) {
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
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Failed to load messages.";
      setError(message);
    }
  }

  async function deleteChat(chatId: string) {
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
    const { chatId, message, revisionTarget } = retryPayload;
    setRetryPayload(null);
    setError("");
    await sendToBackend(chatId, message, revisionTarget);
  }

  async function sendToBackend(
    chatId: string,
    messageText: string,
    revisionTarget?: RevisionTarget,
  ) {
    setIsSending(true);
    setError("");
    setRetryPayload(null);
    setBackendStatuses([]);
    setLiveSectionDrafts({});
    setActiveBackendNode(null);

    const optimisticMessage: ChatMessage = {
      id: `optimistic-${Date.now()}`,
      role: "USER",
      content: messageText,
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticMessage]);

    try {
      const response = await fetch(`/api/chats/${chatId}/interact`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          revisionTarget
            ? { message: messageText, revisionTarget }
            : { message: messageText },
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

      const summary = await consumeSseResponse(response, {
        onStatus: (status) => {
          if (activeBackendNodeRef.current === status.node) {
            setActiveBackendNode(null);
          }
          setBackendStatuses((prev) => {
            if (prev.some((item) => item.node === status.node && item.status === status.status)) {
              return prev;
            }
            return [...prev, status];
          });
        },
        onToken: ({ content, node }) => {
          if (!content) return;

          if (node === "ask_clarifying_questions") {
            return;
          }

          if (node) {
            setActiveBackendNode(node);
          }

          if (node && DRAFT_NODE_TO_SECTION_KEY[node]) {
            const sectionKey = DRAFT_NODE_TO_SECTION_KEY[node];
            setLiveSectionDrafts((prev) => ({
              ...prev,
              [sectionKey]: (prev[sectionKey] || "") + content,
            }));
          }
        },
        onQuestion: ({ prompt, questions }) => {
          setActiveBackendNode(null);
          setQuestionMode({
            introPrompt: prompt,
            questions,
            currentIdx: 0,
            answered: [],
          });
        },
        onComplete: ({ document }) => {
          setActiveBackendNode(null);
          setDocumentText(document || "");
          setLiveSectionDrafts({});
        },
      });

      const payload = summary.result as InteractResponse | undefined;
      if (!payload) {
        throw new Error("Missing final interaction result.");
      }

      // When questions are active the saved ASSISTANT message mirrors what the
      // virtual question bubbles already show — exclude it from the visible list
      // so there's no duplication.  We keep the message in `messages` for
      // history but will filter it in the render pass.
      setMessages(payload.messages);
      setDocumentText(payload.chat.currentDocument || summary.finalDocument || "");
      setStateJson(payload.chat.stateJson || null);
      setBackendStatuses(payload.statuses?.length ? payload.statuses : summary.statuses);
      if (payload.chat.currentDocument || summary.finalDocument) {
        setLiveSectionDrafts({});
      }
      setActiveBackendNode(null);

      if (summary.questions.length) {
        setQuestionMode((prev) => {
          if (prev && prev.questions.length > 0) {
            return prev;
          }
          return {
            introPrompt: summary.questionPrompt || "",
            questions: summary.questions,
            currentIdx: 0,
            answered: [],
          };
        });
      } else {
        const assistantMessage =
          payload.messages
            .slice()
            .reverse()
            .find((message) => message.role === "ASSISTANT")?.content ?? "";
        const parsedFallback = parseAssistantClarificationContent(assistantMessage);

        if (parsedFallback) {
          setQuestionMode({
            introPrompt:
              parsedFallback.prompt || "I need a few clarifications before drafting the SRS.",
            questions: parsedFallback.questions,
            currentIdx: 0,
            answered: [],
          });
        } else {
          setQuestionMode(null);
        }
      }

      setChats((prev) =>
        prev
          .map((chat) =>
            chat.id === payload.chat.id
              ? {
                  ...chat,
                  title: payload.chat.title,
                  updatedAt: payload.chat.updatedAt,
                  currentDocument: payload.chat.currentDocument,
                  stateJson: payload.chat.stateJson,
                }
              : chat,
          )
          .sort(
            (first, second) =>
              new Date(second.updatedAt).getTime() - new Date(first.updatedAt).getTime(),
          ),
      );
    } catch (caughtError) {
      setMessages((prev) => prev.filter((message) => message.id !== optimisticMessage.id));
      setActiveBackendNode(null);
      const message =
        caughtError instanceof Error ? caughtError.message : "Failed to send message.";
      setError(message);
      setRetryPayload({ chatId, message: messageText, revisionTarget });
    } finally {
      setIsSending(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Form submit
  // ---------------------------------------------------------------------------

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const inputValue = input.trim();
    if (!inputValue) return;

    if (questionMode !== null) {
      // Collect the answer for the current question.
      const newAnswered = [...questionMode.answered, inputValue];
      setInput("");

      if (questionMode.currentIdx < questionMode.questions.length - 1) {
        // More questions to go — just advance the index.
        setQuestionMode({
          ...questionMode,
          currentIdx: questionMode.currentIdx + 1,
          answered: newAnswered,
        });
        return;
      }

      // All questions answered — compile a combined reply and send to backend.
      const compiled = questionMode.questions
        .map((q, i) => `Q: ${q.question}\nA: ${newAnswered[i]}`)
        .join("\n\n");

      setQuestionMode(null);

      const chatId = selectedChatIdRef.current;
      if (!chatId || isSending) return;
      await sendToBackend(chatId, compiled);
      return;
    }

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
      draftedSections.map((section) => ({
        ...section,
        title: formatSectionTitle(section.key),
        parts: extractDraftParts(section.key, section.content),
      })),
    [draftedSections],
  );

  const allDraftParts = useMemo(
    () => draftSections.flatMap((section) => section.parts),
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

  const waitingOnLabel = useMemo(
    () => getWaitingOnLabel(backendStatuses, activeBackendNode),
    [backendStatuses, activeBackendNode],
  );

  return (
    <div className="flex h-screen flex-col bg-zinc-50">
      <header className="flex items-center justify-between border-b border-black/10 bg-white px-4 py-3">
        <div>
          <h1 className="text-lg font-semibold">SRS Chat Workspace</h1>
          <p className="text-xs text-black/60">{userEmail}</p>
        </div>
        <button
          onClick={onLogout}
          className="rounded-md border border-black/15 px-3 py-1.5 text-sm"
        >
          Logout
        </button>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[260px_1fr_420px]">
        {/* ── Sidebar: chat list ── */}
        <aside className="flex min-h-0 flex-col border-r border-black/10 bg-white">
          <div className="flex items-center justify-between p-3">
            <h2 className="text-sm font-semibold">Previous chats</h2>
            <button
              onClick={createChat}
              className="rounded-md border border-black/15 px-2 py-1 text-xs"
            >
              New
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
            {isLoading ? <p className="px-1 text-sm text-black/60">Loading...</p> : null}
            {chats.length === 0 && !isLoading ? (
              <p className="px-1 text-sm text-black/60">No chats yet. Create one.</p>
            ) : null}

            {chats.map((chat) => {
              const isActive = chat.id === selectedChatId;
              return (
                <div
                  key={chat.id}
                  className={`mb-2 flex items-start gap-2 rounded-md border px-2 py-2 ${
                    isActive ? "border-black bg-black text-white" : "border-black/10 bg-white"
                  }`}
                >
                  <button
                    onClick={() => {
                      setSelectedChatId(chat.id);
                      void loadChatDetails(chat.id);
                    }}
                    className={`min-w-0 flex-1 text-left ${isActive ? "text-white" : "text-black"}`}
                  >
                    <p className="truncate text-sm font-medium">{chat.title || "Untitled"}</p>
                    <p className={`mt-1 text-xs ${isActive ? "text-white/70" : "text-black/60"}`}>
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
                        : "text-black/60 hover:bg-black/5"
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
        <main className="flex min-h-0 flex-col border-r border-black/10 bg-white">
          <div className="border-b border-black/10 px-4 py-3">
            <h2 className="text-sm font-semibold">Chat</h2>
            <p className="text-xs text-black/60">
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
                    ? "ml-auto bg-black text-white"
                    : "bg-zinc-100 text-black"
                }`}
              >
                {message.role === "ASSISTANT" ? (
                  <MarkdownContent content={message.content} />
                ) : (
                  message.content
                )}
              </div>
            ))}

            {/* One-by-one question mode */}
            {questionMode !== null ? (
              <>
                {/* Intro prompt (if any) */}
                {questionMode.introPrompt ? (
                  <div className="max-w-[85%] rounded-lg bg-zinc-100 px-3 py-2 text-sm whitespace-pre-wrap text-black">
                    {questionMode.introPrompt}
                  </div>
                ) : null}

                {/* Answered Q&A pairs so far */}
                {questionMode.questions.slice(0, questionMode.currentIdx).map((q, i) => (
                  <Fragment key={`qa-${i}`}>
                    <QuestionBubble
                      question={q}
                      number={i + 1}
                      total={questionMode.questions.length}
                    />
                    <div className="ml-auto max-w-[85%] rounded-lg bg-black px-3 py-2 text-sm whitespace-pre-wrap text-white">
                      {questionMode.answered[i]}
                    </div>
                  </Fragment>
                ))}

                {/* Current question */}
                <QuestionBubble
                  question={questionMode.questions[questionMode.currentIdx]}
                  number={questionMode.currentIdx + 1}
                  total={questionMode.questions.length}
                  onOptionSelect={(opt) => setInput(opt)}
                />
              </>
            ) : null}

            {selectedDraftPart !== null && questionMode === null ? (
              <SelectedDraftBubble
                part={selectedDraftPart}
                onClear={() => setSelectedDraftPart(null)}
              />
            ) : null}

            {isSending ? (
              <ReceivingBubble waitingOn={waitingOnLabel} statuses={backendStatuses} />
            ) : null}

            {visibleMessages.length === 0 && questionMode === null ? (
              <p className="text-sm text-black/60">Start by asking about your product idea.</p>
            ) : null}

            <div ref={messagesEndRef} />
          </div>

          {/* Input form */}
          <form onSubmit={onSubmit} className="border-t border-black/10 p-3">
            {selectedDraftPart !== null && questionMode === null ? (
              <div className="mb-2 flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">
                <p className="min-w-0 truncate">
                  Editing target: <span className="font-semibold">{selectedDraftPart.title}</span>
                </p>
                <button
                  type="button"
                  onClick={() => setSelectedDraftPart(null)}
                  className="rounded-full border border-amber-300 px-2 py-0.5 transition-colors hover:bg-amber-100"
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
                    ? `Answer question ${questionMode.currentIdx + 1} of ${questionMode.questions.length}…`
                    : selectedDraftPart !== null
                      ? `Describe how to revise \"${selectedDraftPart.title}\"...`
                      : "Describe the software you want to build..."
                }
                className="w-full rounded-md border border-black/15 px-3 py-2 text-sm"
                disabled={!selectedChatId || isSending}
              />
              <button
                type="submit"
                disabled={!selectedChatId || isSending || !input.trim()}
                className="rounded-md bg-black px-4 py-2 text-sm text-white disabled:opacity-60"
              >
                {isSending ? "Sending..." : questionMode !== null ? "Answer" : "Send"}
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
        <aside className="min-h-0 overflow-y-auto bg-zinc-50 p-4">
          <h2 className="text-sm font-semibold">SRS draft</h2>
          <p className="mt-1 text-xs text-black/60">
            Click a section or requirement to send a targeted revision request through chat.
          </p>

          <div className="mt-3 space-y-3">
            {draftSections.length === 0 ? (
              <div className="rounded-md border border-black/10 bg-white p-3 text-xs text-black/60">
                No drafted sections yet.
              </div>
            ) : (
              draftSections.map((section) => (
                <div key={section.key} className="rounded-md border border-black/10 bg-white p-3">
                  <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-black/70">
                    {section.title}
                  </h3>

                  <div className="mt-2 space-y-2">
                    {section.parts.map((part) => {
                      const isSelected = selectedDraftPart?.id === part.id;

                      return (
                        <button
                          key={part.id}
                          type="button"
                          onClick={() => setSelectedDraftPart(part)}
                          disabled={questionMode !== null || isSending}
                          className={`block w-full rounded-xl border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                            isSelected
                              ? "border-amber-300 bg-amber-50"
                              : "border-black/10 bg-zinc-50 hover:border-black/20 hover:bg-white"
                          }`}
                        >
                          <p className="text-xs font-medium text-black">{part.title}</p>
                          <p className="mt-1 max-h-16 overflow-hidden text-xs leading-relaxed text-black/65">
                            {part.preview}
                          </p>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="mt-4 rounded-md border border-black/10 bg-white p-3">
            <h3 className="text-xs font-semibold text-black/70">
              {selectedDraftPart ? `Preview · ${selectedDraftPart.title}` : "Document preview"}
            </h3>
            <div className="mt-2 max-h-[520px] overflow-auto text-xs text-black/90">
              <MarkdownContent
                content={
                  selectedDraftPart?.content ||
                  resolvedDocumentText ||
                  "The draft SRS document will appear here once sections are available."
                }
              />
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
