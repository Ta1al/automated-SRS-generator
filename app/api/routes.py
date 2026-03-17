"""
FastAPI route handlers for the SRS generator.

Endpoints:
    POST /api/sessions
        Create a new elicitation session. Returns a unique thread_id.

    POST /api/sessions/{thread_id}/interact
        Send a user message and stream the response via Server-Sent Events.
        On the first call the graph is invoked fresh.
        On subsequent calls (after an interrupt) the graph is resumed.

    GET  /api/sessions/{thread_id}/document
        Retrieve the final assembled SRS document once the workflow completes.

    GET  /api/sessions/{thread_id}/state
        Inspect the current LangGraph state for debugging.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncGenerator

import openai

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel
from sse_starlette import EventSourceResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["srs"])

# ── Request / Response models ─────────────────────────────────────────────────


class InteractRequest(BaseModel):
    message: str


# ── Helper: detect if a thread is currently interrupted ──────────────────────


async def _is_interrupted(app_state: Any, thread_id: str) -> bool:
    """Check whether the graph for ``thread_id`` is paused at an interrupt."""
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await app_state.graph.aget_state(config)
        # LangGraph sets next=('ask_clarifying_questions',) when interrupted
        # before that node (because we used interrupt_before=[...])
        return bool(state and state.next and "ask_clarifying_questions" in state.next)
    except Exception:
        return False


# ── SSE event generator ───────────────────────────────────────────────────────


async def _stream_graph(
    app_state: Any,
    thread_id: str,
    message: str,
    is_resume: bool,
) -> AsyncGenerator[dict, None]:
    """
    Async generator that drives the LangGraph graph and yields SSE-compatible
    event dicts.

    Event types emitted:
        status   — node-level progress ({"node": "...", "status": "started"|"finished"})
        token    — streamed text chunk ({"content": "..."})
        question — HITL clarification request ({"questions": [...], "prompt": "..."})
        complete — workflow finished ({"document": "..."})
        error    — runtime error ({"message": "..."})
    """
    graph = app_state.graph
    config = {"configurable": {"thread_id": thread_id}}

    try:
        if is_resume:
            # Resume the paused graph with the user's answer
            inputs: Any = Command(resume={"message": message})
        else:
            # Fresh invocation
            inputs = {
                "chat_history": [HumanMessage(content=message)],
                "document_buffer": "",
                "missing_context": [],
                "requirements": [],
                "rag_context": "",
                "sections": {},
                "mermaid_blocks": [],
                "mermaid_errors": [],
                "mermaid_correction_attempts": 0,
                "is_complete": False,
                "qa_gaps": [],
                "final_document": "",
            }

        async for stream_event in graph.astream(
            inputs,
            config=config,
            stream_mode=["updates", "messages"],
        ):
            # stream_event is a tuple: (mode, data)
            mode, data = stream_event

            if mode == "messages":
                # data = (message_chunk, metadata)
                msg_chunk, meta = data
                if hasattr(msg_chunk, "content") and msg_chunk.content:
                    yield {
                        "event": "token",
                        "data": json.dumps(
                            {
                                "content": msg_chunk.content,
                                "node": meta.get("langgraph_node", ""),
                            }
                        ),
                    }

            elif mode == "updates":
                # data = {node_name: {state_updates}}
                for node_name, node_updates in data.items():

                    if node_name == "__interrupt__":
                        # Graph paused — surface the questions to the client
                        interrupts = node_updates if isinstance(node_updates, list) else []
                        for interrupt_obj in interrupts:
                            payload = getattr(interrupt_obj, "value", {})
                            yield {
                                "event": "question",
                                "data": json.dumps(
                                    {
                                        "questions": payload.get("questions", []),
                                        "prompt": payload.get("prompt", ""),
                                    }
                                ),
                            }
                        return  # Stop streaming; wait for user reply

                    # Emit node progress status
                    yield {
                        "event": "status",
                        "data": json.dumps(
                            {"node": node_name, "status": "finished"}
                        ),
                    }

                    # If the graph just finalised, emit the document
                    if node_name == "finalize_document":
                        final_doc = node_updates.get("final_document", "")
                        if final_doc:
                            yield {
                                "event": "complete",
                                "data": json.dumps({"document": final_doc}),
                            }
                            return

    except openai.APIError as exc:
        logger.exception("OpenAI API error during graph streaming for thread %s", thread_id)
        yield {
            "event": "error",
            "data": json.dumps({
                "message": "The AI service encountered a network error. Please retry.",
                "retryable": True,
            }),
        }
    except Exception:
        logger.exception("Error during graph streaming for thread %s", thread_id)
        yield {
            "event": "error",
            "data": json.dumps(
                {
                    "message": "Unexpected backend error while generating the SRS. Please retry.",
                    "retryable": False,
                }
            ),
        }


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/sessions", status_code=201)
async def create_session() -> JSONResponse:
    """
    Create a new SRS elicitation session.

    Returns:
        {"thread_id": "<uuid>"}
    """
    thread_id = str(uuid.uuid4())
    logger.info("New session created: %s", thread_id)
    return JSONResponse({"thread_id": thread_id}, status_code=201)


@router.post("/sessions/{thread_id}/interact")
async def interact(
    thread_id: str,
    body: InteractRequest,
    request: Request,
) -> EventSourceResponse:
    """
    Send a user message and stream the SRS generator's response.

    The first call starts the graph. Subsequent calls after an interrupt
    resume the paused graph with the user's clarification answers.
    """
    app_state = request.app.state
    if not hasattr(app_state, "graph") or app_state.graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialised.")

    is_resume = await _is_interrupted(app_state, thread_id)
    logger.info(
        "Interact: thread=%s resume=%s message=%.60s …",
        thread_id,
        is_resume,
        body.message,
    )

    async def event_generator() -> AsyncGenerator[dict, None]:
        if await request.is_disconnected():
            return
        async for event in _stream_graph(
            app_state, thread_id, body.message, is_resume
        ):
            if await request.is_disconnected():
                logger.info("Client disconnected mid-stream for thread %s", thread_id)
                break
            yield event

    return EventSourceResponse(event_generator(), ping=15)


@router.delete("/sessions/{thread_id}", status_code=204)
async def delete_session(thread_id: str, request: Request) -> None:
    """
    Delete all persisted LangGraph checkpoint state for a thread.
    """
    app_state = request.app.state
    if not hasattr(app_state, "graph") or app_state.graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialised.")

    checkpointer = getattr(app_state.graph, "checkpointer", None)
    if checkpointer is None:
        raise HTTPException(status_code=501, detail="Session deletion is not supported.")

    delete_thread = getattr(checkpointer, "adelete_thread", None)
    if not callable(delete_thread):
        raise HTTPException(status_code=501, detail="Session deletion is not supported.")

    try:
        await delete_thread(thread_id)
        logger.info("Deleted backend session state for thread %s", thread_id)
    except Exception as exc:
        logger.exception("Failed to delete backend session state for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to delete session state.") from exc


@router.get("/sessions/{thread_id}/document")
async def get_document(thread_id: str, request: Request) -> JSONResponse:
    """
    Return the final SRS Markdown document for a completed session.
    """
    app_state = request.app.state
    if not hasattr(app_state, "graph") or app_state.graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialised.")

    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await app_state.graph.aget_state(config)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Session not found: {exc}") from exc

    if state is None or not state.values:
        raise HTTPException(status_code=404, detail="Session not found.")

    final_doc = state.values.get("final_document", "")
    if not final_doc:
        raise HTTPException(
            status_code=202,
            detail="Document not yet complete. Continue the elicitation session.",
        )

    return JSONResponse({"thread_id": thread_id, "document": final_doc})


@router.get("/sessions/{thread_id}/state")
async def get_state(thread_id: str, request: Request) -> JSONResponse:
    """
    Debug endpoint — return the raw LangGraph state snapshot.
    """
    app_state = request.app.state
    if not hasattr(app_state, "graph") or app_state.graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialised.")

    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await app_state.graph.aget_state(config)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if state is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    return JSONResponse(
        {
            "thread_id": thread_id,
            "next": list(state.next) if state.next else [],
            "is_complete": state.values.get("is_complete", False),
            "missing_context_count": len(state.values.get("missing_context", [])),
            "requirements_count": len(state.values.get("requirements", [])),
            "sections_drafted": list(state.values.get("sections", {}).keys()),
            "mermaid_blocks_count": len(state.values.get("mermaid_blocks", [])),
            "missing_context": state.values.get("missing_context", []),
            "qa_gaps": state.values.get("qa_gaps", []),
            "sections": state.values.get("sections", {}),
            "final_document": state.values.get("final_document", ""),
        }
    )
