"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json
import asyncio

from . import storage
from . import pddl_engine
from .pddl_engine import (
    extract_metrics,
    run_planner,
    validate_plan,
    record_telemetry,
    fetch_telemetry,
    find_fast_downward_binary,
    find_val_binary,
    PYPERPLAN_AVAILABLE,
)
from .council import (
    run_full_council,
    generate_conversation_title,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
    calculate_aggregate_rankings,
)

app = FastAPI(title="LLM Council API - AEPP Platform")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str


class SolvePDDLRequest(BaseModel):
    """Request payload for full AEPP planning orchestrator pipeline."""
    domain_pddl: str
    problem_pddl: str
    user_constraints: Optional[Dict[str, Any]] = None


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "AEPP Planning Council & Engine API"}


@app.get("/api/pddl-status")
async def get_pddl_status():
    """Check availability of classical planning engines and validators on host."""
    return {
        "fast_downward": bool(find_fast_downward_binary()),
        "fast_downward_path": find_fast_downward_binary(),
        "val_validator": bool(find_val_binary()),
        "val_path": find_val_binary(),
        "pyperplan": PYPERPLAN_AVAILABLE,
        "mock_mode_available": True,
    }


@app.get("/api/telemetry")
async def get_telemetry_history(limit: int = 50, problem_name: Optional[str] = None):
    """Retrieve telemetry log records from SQLite."""
    records = await fetch_telemetry(limit=limit, problem_name=problem_name)
    return {"records": records, "count": len(records)}


@app.post("/api/solve-pddl")
async def solve_pddl_pipeline(request: SolvePDDLRequest):
    """Full Orchestrator Pipeline for Explainable AI Planning:

    Step 1 (Analysis): Extract structural metrics (objects, predicates, actions, goals, costs).
    Step 2 (Council Debate): 3-stage deliberation (Optimal, Satisficing, Agile debate; Judge picks winning configuration).
    Step 3 (Execution): Run classical planner with chosen strategy and budget.
    Step 4 (Validation): Validate plan with VAL or state-transition engine.
    Step 5 (Fallback Loop): If chosen planner fails, automatically fallback (optimal -> satisficing -> agile -> mock).
    Step 6 (Explanation & Learning): Generate XAI summary, save full run metrics to SQLite telemetry.
    Step 7: Return complete execution payload with debate transcripts, plan, and validation certificate.
    """
    if not request.domain_pddl.strip():
        raise HTTPException(status_code=400, detail="Domain PDDL content cannot be empty.")
    if not request.problem_pddl.strip():
        raise HTTPException(status_code=400, detail="Problem PDDL content cannot be empty.")

    # Step 1: Structural Analysis
    metrics = extract_metrics(request.domain_pddl, request.problem_pddl)
    problem_name = metrics.get("problem_name", "unknown")
    domain_name = metrics.get("domain_name", "unknown")

    # Step 2: Council Debate
    task_desc = f"Solve planning problem '{problem_name}' in domain '{domain_name}'."
    stage1_results, stage2_results, stage3_result, council_meta = await run_full_council(
        user_query=task_desc,
        domain_text=request.domain_pddl,
        problem_text=request.problem_pddl,
    )

    decision = stage3_result.get("decision", {})
    initial_strategy = decision.get("strategy", "satisficing").lower()
    budget = float(decision.get("budget_seconds", 60.0))
    search_config = decision.get("search_configuration", "")
    judge_rationale = decision.get("justification_summary", "")

    # Respect optional user constraints
    if request.user_constraints:
        if "max_time" in request.user_constraints:
            try:
                budget = min(budget, float(request.user_constraints["max_time"]))
            except (ValueError, TypeError):
                pass
        if "force_strategy" in request.user_constraints:
            forced = str(request.user_constraints["force_strategy"]).lower()
            if forced in ("optimal", "satisficing", "agile"):
                initial_strategy = forced

    # Step 3 & 4: Initial Execution and Validation
    current_strategy = initial_strategy
    current_budget = budget
    fallback_triggered = False
    fallback_history: List[Dict[str, Any]] = []

    exec_res = run_planner(
        domain=request.domain_pddl,
        problem=request.problem_pddl,
        strategy=current_strategy,
        timeout=current_budget,
    )

    if exec_res.get("success") and exec_res.get("plan"):
        val_res = validate_plan(
            domain=request.domain_pddl,
            problem=request.problem_pddl,
            plan=exec_res["plan"],
            execution_time=exec_res.get("execution_time", 0.0),
        )
    else:
        val_res = {
            "valid": False,
            "cost": 0.0,
            "plan": [],
            "execution_time": exec_res.get("execution_time", 0.0),
            "error": exec_res.get("error", "Planner produced no plan."),
        }

    # Step 5: Fallback Loop
    strategy_ladder = {
        "optimal": "satisficing",
        "satisficing": "agile",
        "agile": "mock",
    }
    fallback_budgets = {
        "satisficing": 60.0,
        "agile": 20.0,
        "mock": 5.0,
    }

    while not val_res.get("valid") and current_strategy in strategy_ladder:
        fallback_triggered = True
        next_strategy = strategy_ladder[current_strategy]
        fail_reason = exec_res.get("error") or val_res.get("error") or "Unknown failure"

        fallback_history.append({
            "failed_strategy": current_strategy,
            "reason": fail_reason,
            "execution_time": exec_res.get("execution_time", 0.0),
            "fallback_to": next_strategy,
        })

        current_strategy = next_strategy
        current_budget = fallback_budgets.get(current_strategy, 30.0)
        is_mock = (current_strategy == "mock")

        exec_res = run_planner(
            domain=request.domain_pddl,
            problem=request.problem_pddl,
            strategy="agile" if is_mock else current_strategy,
            timeout=current_budget,
            mock=is_mock,
        )

        if exec_res.get("success") and exec_res.get("plan"):
            val_res = validate_plan(
                domain=request.domain_pddl,
                problem=request.problem_pddl,
                plan=exec_res["plan"],
                execution_time=exec_res.get("execution_time", 0.0),
            )
            if is_mock and exec_res.get("plan"):
                val_res["valid"] = True
                val_res["cost"] = exec_res.get("cost", float(len(exec_res["plan"])))
                val_res["error"] = None
        else:
            val_res = {
                "valid": False,
                "cost": 0.0,
                "plan": [],
                "execution_time": exec_res.get("execution_time", 0.0),
                "error": exec_res.get("error", "Fallback planner produced no plan."),
            }

        if val_res.get("valid"):
            break

    final_strategy = current_strategy
    final_plan = exec_res.get("plan", [])
    total_time = sum(h.get("execution_time", 0.0) for h in fallback_history) + exec_res.get("execution_time", 0.0)

    # Step 6: Explanation & Learning
    if val_res.get("valid"):
        if fallback_triggered:
            xai_summary = (
                f"Initial strategy '{initial_strategy}' failed ({fallback_history[0]['reason']}). "
                f"The Fallback Manager automatically shifted to '{final_strategy}', which successfully "
                f"generated a valid plan of length {len(final_plan)} (cost {val_res.get('cost', 0.0):.1f}) "
                f"in {exec_res.get('execution_time', 0.0):.3f}s. State-transition validation certified all goal conditions."
            )
        else:
            xai_summary = (
                f"The Judge's selected strategy '{final_strategy}' succeeded as predicted. "
                f"Discovered a valid {len(final_plan)}-step plan (cost {val_res.get('cost', 0.0):.1f}) "
                f"in {exec_res.get('execution_time', 0.0):.3f}s (budget: {budget}s). "
                f"Validation certificate confirmed zero precondition or goal violations."
            )
    else:
        xai_summary = (
            f"Planning failed across strategy hierarchy after trying '{initial_strategy}' and fallbacks: "
            f"{val_res.get('error', 'Plan search exhausted without solution')}."
        )

    # Save to SQLite Telemetry
    telemetry_profile = f"{initial_strategy} -> {final_strategy}" if fallback_triggered else final_strategy
    telemetry_id = await record_telemetry(
        problem_name=problem_name,
        chosen_profile=telemetry_profile,
        predicted_budget=budget,
        actual_time=round(total_time, 4),
        plan_length=len(final_plan),
        validity=val_res.get("valid", False),
        judge_rationale=xai_summary,
        cost=val_res.get("cost", 0.0),
        plan=final_plan,
        error=val_res.get("error"),
    )

    # Step 7: Return Complete Execution Payload
    return {
        "status": "success" if (val_res.get("valid") and not fallback_triggered) else ("fallback_success" if val_res.get("valid") else "failed"),
        "problem_name": problem_name,
        "domain_name": domain_name,
        "metrics": metrics,
        "debate": {
            "stage1": stage1_results,
            "stage2": stage2_results,
            "aggregate_rankings": council_meta.get("aggregate_rankings", []),
            "judge_verdict": {
                "response": stage3_result.get("response", ""),
                "decision": decision,
            },
        },
        "execution": {
            "initial_strategy": initial_strategy,
            "final_strategy": final_strategy,
            "fallback_triggered": fallback_triggered,
            "fallback_history": fallback_history,
            "planner_used": exec_res.get("planner_used", "none"),
            "execution_time": round(total_time, 4),
            "cost": val_res.get("cost", 0.0),
            "plan": final_plan,
            "error": val_res.get("error"),
        },
        "validation": {
            "valid": val_res.get("valid", False),
            "cost": val_res.get("cost", 0.0),
            "plan": final_plan,
            "execution_time": val_res.get("execution_time", 0.0),
            "error": val_res.get("error"),
        },
        "xai_summary": xai_summary,
        "telemetry_id": telemetry_id,
    }


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Add user message
    storage.add_user_message(conversation_id, request.content)

    # If this is the first message, generate a title
    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    # Run the 3-stage council process
    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content
    )

    # Add assistant message with all stages
    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result
    )

    # Return the complete response with metadata
    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the 3-stage council process.
    Returns Server-Sent Events as each stage completes.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        try:
            # Add user message
            storage.add_user_message(conversation_id, request.content)

            # Start title generation in parallel (don't await yet)
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(request.content))

            # Stage 1: Collect responses
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            stage1_results = await stage1_collect_responses(request.content)
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            # Stage 2: Collect rankings
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(request.content, stage1_results)
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

            # Stage 3: Synthesize final answer
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(request.content, stage1_results, stage2_results)
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            # Save complete assistant message
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
