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
type RunMode = "full" | "diagrams_only";

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
const PARALLEL_DRAFT_STAGES = [
  "draft_section_1",
  "draft_section_2",
  "draft_section_3_iface",
  "draft_section_3_fr",
  "draft_section_3_nfr",
] as const;

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

function buildBackendMessage(message: string, revisionTarget?: RevisionTarget) {
  if (!revisionTarget) {
    return message;
  }

  return [
    "Revise the existing SRS draft section below.",
    `Target section: ${revisionTarget.title}`,
    revisionTarget.sectionKey ? `Section key: ${revisionTarget.sectionKey}` : "",
    "Current section text:",
    revisionTarget.content,
    "Requested change:",
    message,
    "Update the SRS consistently and preserve unaffected requirements unless the requested change requires broader edits.",
  ]
    .filter(Boolean)
    .join("\n\n");
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

export async function getRunSummary(runId: string) {
  const run = await prisma.chatRun.findUnique({ where: { id: runId } });
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
      status: {
        in: [ChatRunStatus.RUNNING, ChatRunStatus.NEEDS_INPUT],
      },
    },
    orderBy: { startedAt: "desc" },
  });

  if (!run) {
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
  const runMode: RunMode = diagramsOnly ? "diagrams_only" : "full";
  const shouldGenerateDiagrams = diagramsOnly ? true : generateDiagrams;
  const orderedStages =
    runMode === "diagrams_only"
      ? ORDERED_STAGES_DIAGRAMS_ONLY
      : shouldGenerateDiagrams
        ? ORDERED_STAGES_FULL
        : ORDERED_STAGES_NO_DIAGRAMS;
  const includeParallelDraftStages = runMode === "full";
  const backendMessage = buildBackendMessage(message, revisionTarget);
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
      runMode === "diagrams_only" &&
      chat.stateJson &&
      typeof chat.stateJson === "object" &&
      !Array.isArray(chat.stateJson) &&
      (chat.stateJson as Record<string, unknown>).sections &&
      typeof (chat.stateJson as Record<string, unknown>).sections === "object" &&
      !Array.isArray((chat.stateJson as Record<string, unknown>).sections)
        ? ((chat.stateJson as Record<string, unknown>).sections as Record<string, string>)
        : undefined;

    const interactResponse = await backendFetch(`/api/sessions/${chat.backendThreadId}/interact`, {
      method: "POST",
      body: JSON.stringify({
        message: backendMessage,
        mode: runMode,
        generate_diagrams: shouldGenerateDiagrams,
        section_seed: sectionSeed,
      }),
    });

    if (!interactResponse.ok) {
      const errorBody = await interactResponse.text();
      throw new Error(errorBody || "Failed to interact with SRS backend.");
    }

    let activeNode: string | null = null;
    let activeNodeStarted: Date | null = null;

    const summary = await consumeSseResponse(interactResponse, {
      onToken: ({ node }) => {
        if (!node) {
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

    let latestState: Record<string, unknown> | null = null;
    try {
      const stateResponse = await backendFetch(`/api/sessions/${chat.backendThreadId}/state`);
      if (stateResponse.ok) {
        const payload = (await stateResponse.json()) as Record<string, unknown>;
        latestState = payload;
      }
    } catch {
    }

    let currentDocument =
      summary.finalDocument ||
      (typeof latestState?.final_document === "string" ? latestState.final_document : "") ||
      chat.currentDocument;

    if (!currentDocument) {
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

    const normalizedQuestions = normalizeQuestions(summary.questions);

    let persistedAssistantMessage = "";
    if (normalizedQuestions.length > 0) {
      persistedAssistantMessage = formatClarificationPrompt({
        prompt: summary.questionPrompt,
        questions: normalizedQuestions,
      });
    } else if (currentDocument || hasDraftSections) {
      persistedAssistantMessage =
        runMode === "diagrams_only"
          ? "I generated diagrams for the current draft. Open document preview to review them."
          : "I updated the SRS draft. Review the sections in the right panel and select any part to request revisions.";
    } else if (shouldPersistAssistantMessage(summary.assistantMessage)) {
      persistedAssistantMessage = summary.assistantMessage;
    }

    const nextTitle = chat.title === "New Chat" ? message.slice(0, 60) : chat.title;
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
      chatUpdateData.stateJson = latestState as Prisma.InputJsonValue;
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
          questionPrompt: summary.questionPrompt || null,
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
