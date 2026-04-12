import { ChatRunStatus, Prisma } from "@prisma/client";

import {
  backendFetch,
  consumeSseResponse,
  formatClarificationPrompt,
  type BackendStatusEvent,
  type ClarificationQuestion,
} from "@/lib/backend";
import { prisma } from "@/lib/prisma";

type RevisionTarget = {
  title: string;
  content: string;
  sectionKey?: string;
};

type StatusEventRecord = BackendStatusEvent & {
  finishedAt: string;
};

type TimingMap = Map<string, number>;
type RunMode = "full" | "diagrams_only" | "section_revision";

const DEFAULT_STAGE_MS = 45000;
const ORDERED_STAGES_FULL = [
  "retrieve_rag_context",
  "elicit_requirements",
  "evaluate_completeness",
  "ask_clarifying_questions",
  "classify_requirements",
  "draft_section_1",
  "draft_section_2",
  "draft_section_3_iface",
  "draft_section_3_fr",
  "draft_section_3_nfr",
  "draft_section_4",
  "generate_mermaid",
  "validate_mermaid",
  "correct_mermaid",
  "qa_review",
  "finalize_document",
] as const;
const ORDERED_STAGES_NO_DIAGRAMS = [
  "retrieve_rag_context",
  "elicit_requirements",
  "evaluate_completeness",
  "ask_clarifying_questions",
  "classify_requirements",
  "draft_section_1",
  "draft_section_2",
  "draft_section_3_iface",
  "draft_section_3_fr",
  "draft_section_3_nfr",
  "draft_section_4",
  "qa_review",
  "finalize_document",
] as const;
const ORDERED_STAGES_DIAGRAMS_ONLY = [
  "generate_mermaid",
  "validate_mermaid",
  "correct_mermaid",
  "finalize_document",
] as const;
const ORDERED_STAGES_SECTION_REVISION = [
  "revise_selected_section",
  "finalize_document",
] as const;
const PARALLEL_DRAFT_STAGES = [
  "draft_section_1",
  "draft_section_2",
  "draft_section_3_iface",
  "draft_section_3_fr",
  "draft_section_3_nfr",
] as const;
const DRAFT_NODE_TO_SECTION_KEY: Record<string, string> = {
  draft_section_1: "s1",
  draft_section_2: "s2",
  draft_section_3_iface: "s3_iface",
  draft_section_3_fr: "s3_fr",
  draft_section_3_nfr: "s3_nfr",
  draft_section_4: "s4",
};
const MESSAGE_GUARD_NODE = "message_guard";

function extractLiveSectionsFromState(state: unknown): Record<string, string> {
  if (!state || typeof state !== "object" || Array.isArray(state)) {
    return {};
  }

  const raw = (state as Record<string, unknown>).live_sections;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return {};
  }

  const sections: Record<string, string> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value !== "string") {
      continue;
    }

    const trimmed = value.trim();
    if (trimmed) {
      sections[key] = trimmed;
    }
  }

  return sections;
}

function shouldPersistAssistantMessage(message: string) {
  const trimmed = message.trim();
  if (!trimmed) {
    return false;
  }

  if (
    (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
    (trimmed.startsWith("[") && trimmed.endsWith("]"))
  ) {
    return false;
  }

  return true;
}

function buildBackendMessage(message: string) {
  return message;
}

async function loadTimingMap() {
  const stats = await prisma.stageTimingStat.findMany();
  const map: TimingMap = new Map();

  for (const stat of stats) {
    map.set(stat.node, stat.avgDurationMs || DEFAULT_STAGE_MS);
  }

  return map;
}

function getNodeEstimateMs(node: string, timingMap: TimingMap) {
  return timingMap.get(node) ?? DEFAULT_STAGE_MS;
}

function estimateRemainingMs(params: {
  timingMap: TimingMap;
  finishedNodes: Set<string>;
  currentNode: string | null;
  currentNodeStarted: Date | null;
  orderedStages: readonly string[];
  includeParallelDraftStages: boolean;
}) {
  const {
    timingMap,
    finishedNodes,
    currentNode,
    currentNodeStarted,
    orderedStages,
    includeParallelDraftStages,
  } = params;
  const now = Date.now();
  const parallelSet = new Set(PARALLEL_DRAFT_STAGES);

  const getRemainingForNode = (node: string) => {
    if (finishedNodes.has(node)) {
      return 0;
    }

    const estimate = getNodeEstimateMs(node, timingMap);
    if (currentNode === node && currentNodeStarted) {
      return Math.max(0, estimate - (now - currentNodeStarted.getTime()));
    }

    return estimate;
  };

  const remainingParallel = includeParallelDraftStages
    ? PARALLEL_DRAFT_STAGES.filter((node) => !finishedNodes.has(node)).map((node) =>
        getRemainingForNode(node),
      )
    : [];

  let remaining = remainingParallel.length > 0 ? Math.max(...remainingParallel) : 0;

  for (const node of orderedStages) {
    if (parallelSet.has(node as (typeof PARALLEL_DRAFT_STAGES)[number])) {
      continue;
    }
    remaining += getRemainingForNode(node);
  }

  if (currentNode && !orderedStages.includes(currentNode)) {
    remaining += getRemainingForNode(currentNode);
  }

  return Math.max(0, remaining);
}

function toEtaSeconds(milliseconds: number) {
  return Math.max(0, Math.round(milliseconds / 1000));
}

async function updateStageTiming(node: string, durationMs: number) {
  const existing = await prisma.stageTimingStat.findUnique({ where: { node } });

  if (!existing) {
    await prisma.stageTimingStat.create({
      data: {
        node,
        sampleCount: 1,
        avgDurationMs: durationMs,
      },
    });

    return {
      sampleCount: 1,
      avgDurationMs: durationMs,
    };
  }

  const sampleCount = existing.sampleCount + 1;
  const avgDurationMs = (existing.avgDurationMs * existing.sampleCount + durationMs) / sampleCount;

  await prisma.stageTimingStat.update({
    where: { node },
    data: {
      sampleCount,
      avgDurationMs,
    },
  });

  return {
    sampleCount,
    avgDurationMs,
  };
}

function normalizeQuestions(rawQuestions: ClarificationQuestion[] | undefined) {
  if (!rawQuestions || rawQuestions.length === 0) {
    return [] as ClarificationQuestion[];
  }

  return rawQuestions.map((question) => ({
    category: question.category,
    question: question.question,
    suggested_options: question.suggested_options,
    rationale: question.rationale,
  }));
}

function normalizeProjectTitle(value: unknown) {
  if (typeof value !== "string") {
    return "";
  }

  return value.replace(/\s+/g, " ").trim().slice(0, 120);
}

function extractProjectTitleFromState(state: Record<string, unknown> | null) {
  if (!state) {
    return "";
  }

  const direct = normalizeProjectTitle(state.project_title);
  if (direct) {
    return direct;
  }

  const documentBuffer = typeof state.document_buffer === "string" ? state.document_buffer.trim() : "";
  if (!documentBuffer || !(documentBuffer.startsWith("{") && documentBuffer.endsWith("}"))) {
    return "";
  }

  try {
    const parsed = JSON.parse(documentBuffer) as Record<string, unknown>;
    const fromTopLevel = normalizeProjectTitle(parsed.project_title);
    if (fromTopLevel) {
      return fromTopLevel;
    }

    const preliminary = parsed.preliminary_sections;
    if (preliminary && typeof preliminary === "object" && !Array.isArray(preliminary)) {
      return normalizeProjectTitle((preliminary as Record<string, unknown>).product_name);
    }
  } catch {
    return "";
  }

  return "";
}

export async function getRunSummary(runId: string) {
  const run = await prisma.chatRun.findUnique({
    where: { id: runId },
    include: {
      chat: {
        select: {
          title: true,
        },
      },
    },
  });
  if (!run) {
    return null;
  }

  const statusEvents = Array.isArray(run.statusEvents)
    ? (run.statusEvents as unknown as StatusEventRecord[])
    : [];
  const questions = Array.isArray(run.questionsJson)
    ? (run.questionsJson as unknown as ClarificationQuestion[])
    : [];

  return {
    id: run.id,
    status: run.status,
    chatTitle: run.chat.title,
    currentNode: run.currentNode,
    etaSeconds: run.etaSeconds,
    errorMessage: run.errorMessage,
    startedAt: run.startedAt,
    completedAt: run.completedAt,
    questionPrompt: run.questionPrompt,
    questions,
    statuses: statusEvents.map((event) => ({
      node: event.node,
      status: event.status,
    })),
  };
}

export async function getLatestNonTerminalRun(chatId: string) {
  const run = await prisma.chatRun.findFirst({
    where: {
      chatId,
    },
    orderBy: { startedAt: "desc" },
  });

  if (!run) {
    return null;
  }

  if (run.status !== ChatRunStatus.RUNNING && run.status !== ChatRunStatus.NEEDS_INPUT) {
    return null;
  }

  return getRunSummary(run.id);
}

export async function startBackgroundChatRun(params: {
  runId: string;
  chatId: string;
  message: string;
  revisionTarget?: RevisionTarget;
  generateDiagrams?: boolean;
  diagramsOnly?: boolean;
}) {
  const {
    runId,
    chatId,
    message,
    revisionTarget,
    generateDiagrams = false,
    diagramsOnly = false,
  } = params;
  const runMode: RunMode = diagramsOnly
    ? "diagrams_only"
    : revisionTarget
      ? "section_revision"
      : "full";
  const shouldGenerateDiagrams = diagramsOnly ? true : generateDiagrams;
  const orderedStages =
    runMode === "diagrams_only"
      ? ORDERED_STAGES_DIAGRAMS_ONLY
      : runMode === "section_revision"
        ? ORDERED_STAGES_SECTION_REVISION
      : shouldGenerateDiagrams
        ? ORDERED_STAGES_FULL
        : ORDERED_STAGES_NO_DIAGRAMS;
  const includeParallelDraftStages = runMode === "full";
  const backendMessage = buildBackendMessage(message);
  const timingMap = await loadTimingMap();
  const statusEvents: StatusEventRecord[] = [];
  const finishedNodes = new Set<string>();
  const nodeStartedAt = new Map<string, number>();
  const runStart = Date.now();
  let lastFinished = runStart;

  const initialEtaSeconds = toEtaSeconds(
    estimateRemainingMs({
      timingMap,
      finishedNodes,
      currentNode: null,
      currentNodeStarted: null,
      orderedStages,
      includeParallelDraftStages,
    }),
  );

  await prisma.chatRun.update({
    where: { id: runId },
    data: {
      status: ChatRunStatus.RUNNING,
      currentNode: null,
      currentNodeStarted: null,
      statusEvents: statusEvents as unknown as Prisma.InputJsonValue,
      etaSeconds: initialEtaSeconds,
      errorMessage: null,
    },
  });

  try {
    const chat = await prisma.chat.findUnique({
      where: { id: chatId },
      select: {
        id: true,
        title: true,
        currentDocument: true,
        backendThreadId: true,
        stateJson: true,
      },
    });

    if (!chat) {
      throw new Error("Chat not found.");
    }

    const sectionSeed =
      chat.stateJson &&
      typeof chat.stateJson === "object" &&
      !Array.isArray(chat.stateJson) &&
      (chat.stateJson as Record<string, unknown>).sections &&
      typeof (chat.stateJson as Record<string, unknown>).sections === "object" &&
      !Array.isArray((chat.stateJson as Record<string, unknown>).sections)
        ? Object.fromEntries(
            Object.entries((chat.stateJson as Record<string, unknown>).sections as Record<string, unknown>)
              .filter(([, value]) => typeof value === "string")
              .map(([key, value]) => [key, value as string]),
          )
        : undefined;
    const liveSectionsByKey: Record<string, string> = {};
    let stateJsonSnapshot: Record<string, unknown> =
      chat.stateJson && typeof chat.stateJson === "object" && !Array.isArray(chat.stateJson)
        ? { ...(chat.stateJson as Record<string, unknown>) }
        : {};
    let lastLiveSectionPersistMs = 0;

    const persistLiveSections = async (force = false) => {
      const now = Date.now();
      if (!force && now - lastLiveSectionPersistMs < 500) {
        return;
      }

      lastLiveSectionPersistMs = now;
      stateJsonSnapshot = {
        ...stateJsonSnapshot,
        live_sections: { ...liveSectionsByKey },
      };

      await prisma.chat.update({
        where: { id: chat.id },
        data: {
          stateJson: stateJsonSnapshot as Prisma.InputJsonValue,
        },
      });
    };

    await prisma.chat.update({
      where: { id: chat.id },
      data: {
        stateJson: {
          ...stateJsonSnapshot,
          live_sections: {},
        } as Prisma.InputJsonValue,
      },
    });

    const interactResponse = await backendFetch(`/api/sessions/${chat.backendThreadId}/interact`, {
      method: "POST",
      body: JSON.stringify({
        message: backendMessage,
        mode: runMode,
        generate_diagrams: shouldGenerateDiagrams,
        section_seed: sectionSeed,
        revision_mode: runMode === "section_revision",
        revision_target_section_key: revisionTarget?.sectionKey,
        revision_target_title: revisionTarget?.title,
        revision_target_content: revisionTarget?.content,
      }),
    });

    if (!interactResponse.ok) {
      const errorBody = await interactResponse.text();
      throw new Error(errorBody || "Failed to interact with SRS backend.");
    }

    let activeNode: string | null = null;
    let activeNodeStarted: Date | null = null;
    let streamedProjectTitle = "";
    let sawGuardrailRedirect = false;

    const summary = await consumeSseResponse(interactResponse, {
      onProjectTitle: ({ projectTitle }) => {
        streamedProjectTitle = projectTitle;
        prisma.chat.update({
          where: { id: chat.id },
          data: {
            title: projectTitle,
          },
        }).catch((err) => {
          console.error(
            `[chat-runner] Failed to persist project title for chat ${chat.id}:`,
            err,
          );
        });
      },
      onToken: ({ content, node }) => {
        if (node === MESSAGE_GUARD_NODE) {
          sawGuardrailRedirect = true;
        }

        const targetSection =
          (node ? DRAFT_NODE_TO_SECTION_KEY[node] || "" : "") ||
          (node === "revise_selected_section" ? (revisionTarget?.sectionKey || "") : "");

        if (targetSection && content) {
          liveSectionsByKey[targetSection] = `${liveSectionsByKey[targetSection] || ""}${content}`;
          persistLiveSections(false).catch((err) => {
            console.error(
              `[chat-runner] Failed to persist live section buffer for run ${runId}:`,
              err,
            );
          });
        }

        if (!node || node === MESSAGE_GUARD_NODE) {
          return;
        }

        if (!nodeStartedAt.has(node)) {
          nodeStartedAt.set(node, Date.now());
        }

        if (activeNode !== node) {
          activeNode = node;
          activeNodeStarted = new Date();
          const etaSeconds = toEtaSeconds(
            estimateRemainingMs({
              timingMap,
              finishedNodes,
              currentNode: activeNode,
              currentNodeStarted: activeNodeStarted,
              orderedStages,
              includeParallelDraftStages,
            }),
          );

          prisma.chatRun.update({
            where: { id: runId },
            data: {
              currentNode: activeNode,
              currentNodeStarted: activeNodeStarted,
              etaSeconds,
            },
          }).catch((err) => {
            console.error(
              `[chat-runner] Failed to update current node for run ${runId}:`,
              err,
            );
          });
        }
      },
      onStatus: (status) => {
        if (status.status !== "finished") {
          return;
        }

        if (finishedNodes.has(status.node)) {
          return;
        }

        const nowMs = Date.now();
        const durationMs = Math.max(0, nowMs - (nodeStartedAt.get(status.node) ?? lastFinished));
        lastFinished = nowMs;
        finishedNodes.add(status.node);

        statusEvents.push({
          ...status,
          finishedAt: new Date(nowMs).toISOString(),
        });

        const etaSeconds = toEtaSeconds(
          estimateRemainingMs({
            timingMap,
            finishedNodes,
            currentNode: activeNode,
            currentNodeStarted: activeNodeStarted,
            orderedStages,
            includeParallelDraftStages,
          }),
        );

        (async () => {
          try {
            const nextStat = await updateStageTiming(status.node, durationMs);
            timingMap.set(status.node, nextStat.avgDurationMs);

            await prisma.chatRun.update({
              where: { id: runId },
              data: {
                statusEvents: statusEvents as unknown as Prisma.InputJsonValue,
                currentNode: activeNode === status.node ? null : activeNode,
                currentNodeStarted: activeNode === status.node ? null : activeNodeStarted,
                etaSeconds,
              },
            });
          } catch (err) {
            console.error(
              `[chat-runner] Failed to update status for run ${runId} on node ${status.node}:`,
              err,
            );
          }
        })();

        if (activeNode === status.node) {
          activeNode = null;
          activeNodeStarted = null;
        }
      },
    });

    await persistLiveSections(true).catch((err) => {
      console.error(
        `[chat-runner] Failed to flush live section buffer for run ${runId}:`,
        err,
      );
    });

    let latestState: Record<string, unknown> | null = null;
    if (!sawGuardrailRedirect) {
      try {
        const stateResponse = await backendFetch(`/api/sessions/${chat.backendThreadId}/state`);
        if (stateResponse.ok) {
          const payload = (await stateResponse.json()) as Record<string, unknown>;
          latestState = payload;
        }
      } catch {
      }
    }

    let currentDocument = chat.currentDocument;

    if (!sawGuardrailRedirect) {
      currentDocument =
        summary.finalDocument ||
        (typeof latestState?.final_document === "string" ? latestState.final_document : "") ||
        chat.currentDocument;
    }

    if (!sawGuardrailRedirect && !currentDocument) {
      const documentResponse = await backendFetch(`/api/sessions/${chat.backendThreadId}/document`);
      if (documentResponse.ok) {
        const documentPayload = await documentResponse.json();
        currentDocument = documentPayload.document ?? null;
      }
    }

    const hasDraftSections =
      !!latestState &&
      typeof latestState.sections === "object" &&
      latestState.sections !== null &&
      !Array.isArray(latestState.sections) &&
      Object.keys(latestState.sections as Record<string, unknown>).length > 0;

    let normalizedQuestions = normalizeQuestions(summary.questions);
    let resolvedQuestionPrompt = summary.questionPrompt || "";
    const stateNext = Array.isArray(latestState?.next) ? latestState.next : [];

    if (
      normalizedQuestions.length === 0 &&
      stateNext.includes("ask_clarifying_questions")
    ) {
      const fallbackQuestions = Array.isArray(latestState?.missing_context)
        ? (latestState?.missing_context as ClarificationQuestion[])
        : [];
      normalizedQuestions = normalizeQuestions(fallbackQuestions);

      if (normalizedQuestions.length > 0) {
        resolvedQuestionPrompt = formatClarificationPrompt({
          questions: normalizedQuestions,
        });
      }
    }
    const generatedProjectTitle = extractProjectTitleFromState(latestState);

    let persistedAssistantMessage = "";
    if (sawGuardrailRedirect && shouldPersistAssistantMessage(summary.assistantMessage)) {
      persistedAssistantMessage = summary.assistantMessage;
    } else if (normalizedQuestions.length > 0) {
      persistedAssistantMessage =
        resolvedQuestionPrompt ||
        "I need a few clarifications before continuing. Please answer them in the clarification form.";
    } else if (currentDocument || hasDraftSections) {
      persistedAssistantMessage =
        runMode === "diagrams_only"
          ? "I generated diagrams for the current draft. Open document preview to review them."
          : runMode === "section_revision"
            ? "I updated the selected section in the SRS draft. Review it in the right panel and request more refinements if needed."
          : "I updated the SRS draft. Review the sections in the right panel and select any part to request revisions.";
    } else if (shouldPersistAssistantMessage(summary.assistantMessage)) {
      persistedAssistantMessage = summary.assistantMessage;
    }

    const nextTitle =
      streamedProjectTitle ||
      generatedProjectTitle ||
      (chat.title === "New Chat" ? message.slice(0, 60) : chat.title);
    const normalizedCurrentDocument = currentDocument || null;

    const chatUpdateData: {
      title: string;
      currentDocument: string | null;
      stateJson?: Prisma.InputJsonValue;
    } = {
      title: nextTitle,
      currentDocument: normalizedCurrentDocument,
    };

    if (latestState) {
      const bufferedLiveSections = extractLiveSectionsFromState(stateJsonSnapshot);
      const mergedState = {
        ...latestState,
        live_sections: bufferedLiveSections,
      };
      chatUpdateData.stateJson = mergedState as Prisma.InputJsonValue;
    }

    await prisma.$transaction(async (tx) => {
      if (persistedAssistantMessage) {
        await tx.chatMessage.create({
          data: {
            chatId: chat.id,
            role: "ASSISTANT",
            content: persistedAssistantMessage,
          },
        });
      }

      await tx.chat.update({
        where: { id: chat.id },
        data: chatUpdateData,
      });

      await tx.chatRun.update({
        where: { id: runId },
        data: {
          status:
            normalizedQuestions.length > 0 ? ChatRunStatus.NEEDS_INPUT : ChatRunStatus.COMPLETED,
          currentNode: null,
          currentNodeStarted: null,
          statusEvents: statusEvents as unknown as Prisma.InputJsonValue,
          questionPrompt: resolvedQuestionPrompt || null,
          questionsJson:
            normalizedQuestions.length > 0
              ? (normalizedQuestions as unknown as Prisma.InputJsonValue)
              : Prisma.JsonNull,
          etaSeconds: 0,
          completedAt: new Date(),
          errorMessage: null,
        },
      });
    });
  } catch (error) {
    try {
      const existingChat = await prisma.chat.findUnique({
        where: { id: chatId },
        select: { stateJson: true },
      });
      const stateSnapshot =
        existingChat?.stateJson &&
        typeof existingChat.stateJson === "object" &&
        !Array.isArray(existingChat.stateJson)
          ? { ...(existingChat.stateJson as Record<string, unknown>) }
          : {};

      await prisma.chat.update({
        where: { id: chatId },
        data: {
          stateJson: {
            ...stateSnapshot,
            live_sections: {},
          } as Prisma.InputJsonValue,
        },
      });
    } catch {
    }

    await prisma.chatRun.update({
      where: { id: runId },
      data: {
        status: ChatRunStatus.FAILED,
        currentNode: null,
        currentNodeStarted: null,
        errorMessage: error instanceof Error ? error.message : "Failed to complete SRS generation.",
        etaSeconds: null,
        completedAt: new Date(),
      },
    });
  }
}
