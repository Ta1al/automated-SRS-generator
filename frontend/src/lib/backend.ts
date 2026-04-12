export type ClarificationQuestion = {
  category?: string;
  question: string;
  suggested_options?: string[];
  rationale?: string;
};

export type BackendStatusEvent = {
  node: string;
  status: string;
};

type SseConsumerOptions = {
  onEvent?: (eventName: string, data: unknown) => void;
  onProjectTitle?: (payload: { projectTitle: string }) => void;
  onToken?: (payload: { content: string; node?: string }) => void;
  onStatus?: (payload: BackendStatusEvent) => void;
  onQuestion?: (payload: {
    prompt: string;
    questions: ClarificationQuestion[];
  }) => void;
  onComplete?: (payload: { document: string }) => void;
  onResult?: (payload: unknown) => void;
};

type ParsedQuestionEvent = {
  prompt?: string;
  questions?: unknown;
};

function parseJsonData(rawData: string): unknown {
  try {
    return JSON.parse(rawData);
  } catch {
    return rawData;
  }
}

export function normalizeClarificationQuestions(rawQuestions: unknown): ClarificationQuestion[] {
  if (!Array.isArray(rawQuestions)) {
    return [];
  }

  return rawQuestions.flatMap((item) => {
    if (typeof item === "string") {
      const question = item.trim();
      return question ? [{ question }] : [];
    }

    if (!item || typeof item !== "object") {
      return [];
    }

    const candidate = item as Record<string, unknown>;
    const question = typeof candidate.question === "string" ? candidate.question.trim() : "";
    if (!question) {
      return [];
    }

    const suggestedOptions = Array.isArray(candidate.suggested_options)
      ? Array.from(
          new Set(
            candidate.suggested_options
              .map((option) => (typeof option === "string" ? option.trim() : ""))
              .filter(Boolean),
          ),
        )
      : [];

    return [
      {
        category:
          typeof candidate.category === "string" && candidate.category.trim()
            ? candidate.category.trim()
            : undefined,
        question,
        suggested_options: suggestedOptions,
        rationale:
          typeof candidate.rationale === "string" && candidate.rationale.trim()
            ? candidate.rationale.trim()
            : undefined,
      },
    ];
  });
}

export function formatClarificationPrompt(payload: {
  prompt?: string;
  questions?: ClarificationQuestion[];
}) {
  const normalizedQuestions = payload.questions ?? [];
  const sections = normalizedQuestions.map((item, index) => {
    const lines = [`${index + 1}. ${item.question}`];

    if (item.category) {
      lines[0] = `${index + 1}. [${item.category}] ${item.question}`;
    }

    if (item.suggested_options?.length) {
      lines.push("Suggested options:");
      lines.push(...item.suggested_options.map((option) => `- ${option}`));
    }

    if (item.rationale) {
      lines.push(`Why this matters: ${item.rationale}`);
    }

    return lines.join("\n");
  });

  const prompt = payload.prompt?.trim();
  return [prompt, sections.join("\n\n")].filter(Boolean).join("\n\n").trim();
}

export async function backendFetch(path: string, init?: RequestInit) {
  const baseUrl = process.env.BACKEND_API_URL;
  if (!baseUrl) {
    throw new Error("BACKEND_API_URL is required");
  }
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  return response;
}

export async function consumeSseResponse(
  response: Response,
  options: SseConsumerOptions = {},
) {
  if (!response.body) {
    throw new Error("Missing response body from backend stream.");
  }

  const decoder = new TextDecoder();
  const reader = response.body.getReader();

  let chunkBuffer = "";
  let eventName = "";
  let dataLines: string[] = [];
  let assistantText = "";
  let finalDocument = "";
  let projectTitle = "";
  let questionPrompt = "";
  let questions: ClarificationQuestion[] = [];
  const statuses: BackendStatusEvent[] = [];
  let result: unknown;

  const flushEvent = () => {
    if (dataLines.length === 0) {
      eventName = "";
      return;
    }

    const currentEventName = eventName || "message";
    const rawData = dataLines.join("\n");
    const parsed = parseJsonData(rawData);

    options.onEvent?.(currentEventName, parsed);

    if (currentEventName === "token" && parsed && typeof parsed === "object") {
      const content =
        typeof (parsed as { content?: unknown }).content === "string"
          ? ((parsed as { content: string }).content ?? "")
          : "";
      const node =
        typeof (parsed as { node?: unknown }).node === "string"
          ? ((parsed as { node?: string }).node ?? undefined)
          : undefined;

      assistantText += content;
      options.onToken?.({ content, node });
    }

    if (currentEventName === "project_title" && parsed && typeof parsed === "object") {
      const nextTitle =
        typeof (parsed as { project_title?: unknown }).project_title === "string"
          ? (parsed as { project_title: string }).project_title.replace(/\s+/g, " ").trim().slice(0, 120)
          : "";

      if (nextTitle) {
        projectTitle = nextTitle;
        options.onProjectTitle?.({ projectTitle: nextTitle });
      }
    }

    if (currentEventName === "status" && parsed && typeof parsed === "object") {
      const payload = {
        node:
          typeof (parsed as { node?: unknown }).node === "string"
            ? (parsed as { node: string }).node
            : "unknown",
        status:
          typeof (parsed as { status?: unknown }).status === "string"
            ? (parsed as { status: string }).status
            : "unknown",
      };
      statuses.push(payload);
      options.onStatus?.(payload);
    }

    if (currentEventName === "question") {
      const payload = (parsed && typeof parsed === "object" ? parsed : {}) as ParsedQuestionEvent;
      questions = normalizeClarificationQuestions(payload.questions);
      questionPrompt =
        typeof payload.prompt === "string" && payload.prompt.trim()
          ? payload.prompt.trim()
          : formatClarificationPrompt({ questions });
      options.onQuestion?.({ prompt: questionPrompt, questions });
    }

    if (currentEventName === "complete" && parsed && typeof parsed === "object") {
      finalDocument =
        typeof (parsed as { document?: unknown }).document === "string"
          ? ((parsed as { document: string }).document ?? "")
          : "";
      options.onComplete?.({ document: finalDocument });
    }

    if (currentEventName === "result") {
      result = parsed;
      options.onResult?.(parsed);
    }

    if (currentEventName === "error") {
      const message =
        parsed &&
        typeof parsed === "object" &&
        typeof (parsed as { message?: unknown }).message === "string"
          ? (parsed as { message: string }).message
          : "SRS backend returned an error.";
      throw new Error(message);
    }

    eventName = "";
    dataLines = [];
  };

  const processLine = (line: string) => {
    if (!line) {
      flushEvent();
      return;
    }

    if (line.startsWith(":")) {
      return;
    }

    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
      return;
    }

    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    chunkBuffer += decoder.decode(value, { stream: true });
    const lines = chunkBuffer.split(/\r?\n/);
    chunkBuffer = lines.pop() ?? "";

    for (const line of lines) {
      processLine(line);
    }
  }

  chunkBuffer += decoder.decode();
  if (chunkBuffer) {
    for (const line of chunkBuffer.split(/\r?\n/)) {
      processLine(line);
    }
  }
  flushEvent();

  // When questions are present `assistantText` is raw LLM JSON that was
  // already parsed into `questions` — skip it and use only the formatted version.
  const normalizedAssistant =
    questions.length > 0
      ? formatClarificationPrompt({ prompt: questionPrompt, questions })
      : assistantText.trim();

  return {
    assistantMessage: normalizedAssistant,
    finalDocument,
    projectTitle,
    questionPrompt,
    questions,
    statuses,
    result,
  };
}
