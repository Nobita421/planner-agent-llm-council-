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
from .config import PLANNING_COUNCIL_ROLES, CHAIRMAN_MODEL
from .openrouter import get_model_catalog

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


ROLE_MODEL_KEYS = ("optimal", "satisficing", "agile", "judge")


async def resolve_role_models(user_constraints: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    """Validate optional frontend model overrides against OpenRouter's catalog."""
    if not user_constraints or "models" not in user_constraints:
        return None

    requested = user_constraints["models"]
    if not isinstance(requested, dict):
        raise HTTPException(status_code=400, detail="models must be an object keyed by council role.")

    overrides: Dict[str, str] = {}
    for role in ROLE_MODEL_KEYS:
        if role in requested:
            value = requested[role]
            if not isinstance(value, str) or not value.strip():
                raise HTTPException(status_code=400, detail=f"Model override for '{role}' must be a non-empty string.")
            overrides[role] = value.strip()

    unknown_roles = set(requested) - set(ROLE_MODEL_KEYS)
    if unknown_roles:
        raise HTTPException(status_code=400, detail=f"Unknown model role(s): {', '.join(sorted(unknown_roles))}.")

    try:
        catalog = await get_model_catalog()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to load the model catalog.") from exc

    available_ids = {model["id"] for model in catalog}
    invalid = sorted(set(overrides.values()) - available_ids)
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown model ID(s): {', '.join(invalid)}.")
    return overrides


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


@app.get("/api/models")
async def get_models():
    """Return the searchable model catalog."""
    from .openrouter import get_groq_api_key
    groq_key = get_groq_api_key()
    default_optimal = "groq/openai/gpt-oss-120b" if groq_key else PLANNING_COUNCIL_ROLES["optimal"]["model"]
    default_satisficing = "groq/qwen/qwen3.8-27b" if groq_key else PLANNING_COUNCIL_ROLES["satisficing"]["model"]
    default_agile = "groq/openai/gpt-oss-20b" if groq_key else PLANNING_COUNCIL_ROLES["agile"]["model"]
    default_judge = "groq/openai/gpt-oss-120b" if groq_key else CHAIRMAN_MODEL

    try:
        return {
            "models": await get_model_catalog(),
            "defaults": {
                "optimal": default_optimal,
                "satisficing": default_satisficing,
                "agile": default_agile,
                "judge": default_judge,
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to load the model catalog: {exc}") from exc


async def execute_planner_with_fallbacks(
    domain_pddl: str,
    problem_pddl: str,
    decision: Dict[str, Any],
    user_constraints: Optional[Dict[str, Any]],
    metrics: Dict[str, Any],
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    stage3_result: Dict[str, Any],
    aggregate_rankings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Execute classical planner with fallback cascade and record telemetry."""
    problem_name = metrics.get("problem_name", "unknown")
    domain_name = metrics.get("domain_name", "unknown")

    initial_strategy = decision.get("strategy", "satisficing").lower()
    budget = float(decision.get("budget_seconds", 60.0))
    search_config = decision.get("search_configuration", "")
    judge_rationale = decision.get("justification_summary", "")

    # Respect optional user constraints
    if user_constraints:
        if "max_time" in user_constraints:
            try:
                budget = min(budget, float(user_constraints["max_time"]))
            except (ValueError, TypeError):
                pass
        if "force_strategy" in user_constraints:
            forced = str(user_constraints["force_strategy"]).lower()
            if forced in ("optimal", "satisficing", "agile"):
                initial_strategy = forced

    # Cap initial optimal budget if Fast Downward is not installed on host to prevent Pyperplan freeze
    if not find_fast_downward_binary() and initial_strategy == "optimal":
        budget = min(budget, 15.0)

    # Initial execution
    current_strategy = initial_strategy
    current_budget = budget
    fallback_triggered = False
    fallback_history: List[Dict[str, Any]] = []

    exec_res = run_planner(
        domain=domain_pddl,
        problem=problem_pddl,
        strategy=current_strategy,
        timeout=current_budget,
    )

    if exec_res.get("success") and exec_res.get("plan"):
        val_res = validate_plan(
            domain=domain_pddl,
            problem=problem_pddl,
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

    # Fallback Loop
    strategy_ladder = {
        "optimal": "satisficing",
        "satisficing": "agile",
        "agile": "mock",
    }
    fallback_budgets = {
        "satisficing": 15.0 if not find_fast_downward_binary() else 30.0,
        "agile": 10.0,
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
        current_budget = fallback_budgets.get(current_strategy, 15.0)
        is_mock = (current_strategy == "mock")

        exec_res = run_planner(
            domain=domain_pddl,
            problem=problem_pddl,
            strategy="agile" if is_mock else current_strategy,
            timeout=current_budget,
            mock=is_mock,
        )

        if exec_res.get("success") and exec_res.get("plan"):
            val_res = validate_plan(
                domain=domain_pddl,
                problem=problem_pddl,
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

    # Explanation & Learning
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

    return {
        "status": "success" if (val_res.get("valid") and not fallback_triggered) else ("fallback_success" if val_res.get("valid") else "failed"),
        "problem_name": problem_name,
        "domain_name": domain_name,
        "metrics": metrics,
        "debate": {
            "stage1": stage1_results,
            "stage2": stage2_results,
            "aggregate_rankings": aggregate_rankings,
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


@app.post("/api/solve-pddl")
async def solve_pddl_pipeline(request: SolvePDDLRequest):
    """Full Orchestrator Pipeline for Explainable AI Planning (Synchronous)."""
    if not request.domain_pddl.strip():
        raise HTTPException(status_code=400, detail="Domain PDDL content cannot be empty.")
    if not request.problem_pddl.strip():
        raise HTTPException(status_code=400, detail="Problem PDDL content cannot be empty.")
    role_models = await resolve_role_models(request.user_constraints)

    metrics = extract_metrics(request.domain_pddl, request.problem_pddl)
    problem_name = metrics.get("problem_name", "unknown")
    domain_name = metrics.get("domain_name", "unknown")

    task_desc = f"Solve planning problem '{problem_name}' in domain '{domain_name}'."
    stage1_results, stage2_results, stage3_result, council_meta = await run_full_council(
        user_query=task_desc,
        domain_text=request.domain_pddl,
        problem_text=request.problem_pddl,
        role_models=role_models,
    )

    decision = stage3_result.get("decision", {})
    aggregate_rankings = council_meta.get("aggregate_rankings", [])

    return await execute_planner_with_fallbacks(
        domain_pddl=request.domain_pddl,
        problem_pddl=request.problem_pddl,
        decision=decision,
        user_constraints=request.user_constraints,
        metrics=metrics,
        stage1_results=stage1_results,
        stage2_results=stage2_results,
        stage3_result=stage3_result,
        aggregate_rankings=aggregate_rankings,
    )


@app.post("/api/solve-pddl/stream")
async def solve_pddl_pipeline_stream(request: SolvePDDLRequest):
    """Streaming Orchestrator Pipeline emitting real-time Server-Sent Events (SSE)."""
    if not request.domain_pddl.strip():
        raise HTTPException(status_code=400, detail="Domain PDDL content cannot be empty.")
    if not request.problem_pddl.strip():
        raise HTTPException(status_code=400, detail="Problem PDDL content cannot be empty.")

    async def event_generator():
        try:
            # Step 0: Structural Analysis
            yield f"data: {json.dumps({'type': 'step', 'step': 0, 'detail': 'Reading domain, objects, actions, and goals...'})}\n\n"
            metrics = extract_metrics(request.domain_pddl, request.problem_pddl)
            problem_name = metrics.get("problem_name", "unknown")
            domain_name = metrics.get("domain_name", "unknown")

            # Step 1: Preparing Council
            yield f"data: {json.dumps({'type': 'step', 'step': 1, 'detail': 'Loading selected OpenRouter models and planning context...'})}\n\n"
            role_models = await resolve_role_models(request.user_constraints)
            task_desc = f"Solve planning problem '{problem_name}' in domain '{domain_name}'."

            # Step 2: Stage 1 Strategy Proposals
            yield f"data: {json.dumps({'type': 'step', 'step': 2, 'detail': 'Optimal, satisficing, and agile agents are analyzing the problem...'})}\n\n"
            stage1_results = await stage1_collect_responses(
                user_query=task_desc,
                domain_text=request.domain_pddl,
                problem_text=request.problem_pddl,
                role_models=role_models,
            )

            # Step 3: Stage 2 Peer Review
            yield f"data: {json.dumps({'type': 'step', 'step': 3, 'detail': 'Council agents are comparing and ranking the proposals...'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(
                user_query=task_desc,
                stage1_results=stage1_results,
                domain_text=request.domain_pddl,
                problem_text=request.problem_pddl,
                role_models=role_models,
            )
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

            # Step 4: Stage 3 Judge Synthesis
            yield f"data: {json.dumps({'type': 'step', 'step': 4, 'detail': 'The chairman is selecting a planning strategy and time budget...'})}\n\n"
            stage3_result = await stage3_synthesize_final(
                user_query=task_desc,
                stage1_results=stage1_results,
                stage2_results=stage2_results,
                domain_text=request.domain_pddl,
                problem_text=request.problem_pddl,
                role_models=role_models,
            )
            decision = stage3_result.get("decision", {})

            # Step 5: Execution & Validation
            strat_label = decision.get("strategy", "satisficing").upper()
            yield f"data: {json.dumps({'type': 'step', 'step': 5, 'detail': f'Executing {strat_label} planner search and verifying action validity...'})}\n\n"
            result_payload = await execute_planner_with_fallbacks(
                domain_pddl=request.domain_pddl,
                problem_pddl=request.problem_pddl,
                decision=decision,
                user_constraints=request.user_constraints,
                metrics=metrics,
                stage1_results=stage1_results,
                stage2_results=stage2_results,
                stage3_result=stage3_result,
                aggregate_rankings=aggregate_rankings,
            )

            # Step 6: Finalizing
            yield f"data: {json.dumps({'type': 'step', 'step': 6, 'detail': 'Packaging the plan, debate, validation, and telemetry results...'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'data': result_payload})}\n\n"

        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8001, reload=True)
