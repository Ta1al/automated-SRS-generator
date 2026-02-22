from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional
import uuid
from pathlib import Path
import json

from cli.graph_controller import build_graph

# simple in-memory session storage
_sessions: Dict[str, Dict[str, Any]] = {}

app = FastAPI(title="SRS Generator API")


class IdeaRequest(BaseModel):
    idea: str


class StepRequest(BaseModel):
    session_id: str
    answer: Optional[str] = None


@app.post("/graph/start")
def start_graph(req: IdeaRequest):
    gid = str(uuid.uuid4())
    graph = build_graph()
    ctx = graph.run({"idea": req.idea})
    _sessions[gid] = ctx
    return {"session_id": gid, "context": ctx}


@app.post("/graph/step")
def step_graph(req: StepRequest):
    ctx = _sessions.get(req.session_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="session not found")
    if req.answer is not None:
        # store last answer somewhere simple
        answers = ctx.setdefault("answers", {})
        # a simple policy: put under 'last'
        answers["last"] = req.answer
    graph = build_graph()
    new_ctx = graph.run(ctx)
    _sessions[req.session_id] = new_ctx
    return {"session_id": req.session_id, "context": new_ctx}


@app.get("/graph/{session_id}")
def get_context(session_id: str):
    ctx = _sessions.get(session_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session_id, "context": ctx}
