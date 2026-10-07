"""3-stage AI Planning Council orchestration for the Agentic Explainable Planning Platform (AEPP).

Orchestrates a deliberation among three specialized planning agents:
1. Optimal Agent: A* search, admissible heuristics, optimality guarantees.
2. Satisficing Agent: Heuristic trade-offs, LAMA, multi-heuristic search, cost vs runtime.
3. Agile Agent: Fast first-plan discovery, tight deadlines, greedy search, emergency plans.
4. Judge Agent (Chairman): Synthesizes the debate and outputs an Explainable Decision (XAI)
   with strict JSON configuration.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    CHAIRMAN_MODEL,
    COUNCIL_MODELS,
    JUDGE_ROLE,
    PLANNING_COUNCIL_ROLES,
)
from .openrouter import query_model
from .pddl_engine import analyze_pddl_text


# ============================================================================
# Context & PDDL Preparation Helpers
# ============================================================================

def extract_pddl_from_text(text: str) -> Tuple[str, str]:
    """Extract domain and problem PDDL blocks from a user query if embedded."""
    domain_text = ""
    problem_text = ""

    # Look for (define (domain ...))
    domain_match = re.search(r"\(\s*define\s*\(\s*domain[\s\S]*?\n\s*\)\s*\)", text, re.IGNORECASE)
    if not domain_match:
        # Broader match till balanced or double closing paren
        domain_match = re.search(r"\(\s*define\s*\(\s*domain[\s\S]*?\)\s*\)", text, re.IGNORECASE)
    if domain_match:
        domain_text = domain_match.group(0)

    # Look for (define (problem ...))
    problem_match = re.search(r"\(\s*define\s*\(\s*problem[\s\S]*?\n\s*\)\s*\)", text, re.IGNORECASE)
    if not problem_match:
        problem_match = re.search(r"\(\s*define\s*\(\s*problem[\s\S]*?\)\s*\)", text, re.IGNORECASE)
    if problem_match:
        problem_text = problem_match.group(0)

    return domain_text, problem_text


def prepare_planning_context(
    user_query: str,
    domain_text: str = "",
    problem_text: str = "",
) -> Dict[str, Any]:
    """Prepare structural metrics and contextualized prompt segments from input."""
    # Extract embedded PDDL if not passed explicitly
    if not domain_text or not problem_text:
        extracted_d, extracted_p = extract_pddl_from_text(user_query)
        if not domain_text:
            domain_text = extracted_d
        if not problem_text:
            problem_text = extracted_p

    metrics = analyze_pddl_text(domain_text, problem_text) if (domain_text or problem_text) else {
        "domain_name": "custom-domain",
        "problem_name": "custom-problem",
        "objects_count": 0,
        "predicates_count": 0,
        "actions_count": 0,
        "goals_count": 0,
        "has_action_costs": False,
        "has_numeric_fluents": False,
        "has_typing": False,
        "requirements": [],
        "objects": [],
        "predicates": [],
        "actions": [],
        "goals": [],
    }

    # Estimate complexity indicator
    objects_cnt = metrics.get("objects_count", 0)
    actions_cnt = metrics.get("actions_count", 0)
    goals_cnt = metrics.get("goals_count", 0)

    if objects_cnt > 15 or (objects_cnt > 8 and goals_cnt > 4):
        scale_indicator = "HIGH (Substantial combinatorial state space)"
    elif objects_cnt > 5 or goals_cnt > 2:
        scale_indicator = "MODERATE (Standard benchmark complexity)"
    else:
        scale_indicator = "COMPACT (Small state space; optimal search easily feasible)"

    metrics_summary_text = f"""--- PDDL STRUCTURAL METRICS SUMMARY ---
- Domain Name: {metrics.get('domain_name')}
- Problem Name: {metrics.get('problem_name')}
- Object Count: {objects_cnt} {f"(Objects: {', '.join(metrics.get('objects', [])[:10])}...)" if objects_cnt > 10 else f"(Objects: {', '.join(metrics.get('objects', []))})"}
- Predicate Count: {metrics.get('predicates_count')}
- Action Operator Count: {actions_cnt} (Actions: {', '.join(metrics.get('actions', []))})
- Goal Count: {goals_cnt} (Goals: {', '.join(metrics.get('goals', []))})
- Action Costs Present: {metrics.get('has_action_costs')}
- Numeric Fluents Present: {metrics.get('has_numeric_fluents')}
- Typing Constraints Present: {metrics.get('has_typing')}
- Estimated Scale: {scale_indicator}
----------------------------------------"""

    return {
        "user_query": user_query,
        "domain_text": domain_text,
        "problem_text": problem_text,
        "metrics": metrics,
        "metrics_summary_text": metrics_summary_text,
        "scale_indicator": scale_indicator,
    }


# ============================================================================
# Stage 1: Initial Arguments (Specialized Roles)
# ============================================================================

def _build_stage1_prompt_for_role(role_id: str, context: Dict[str, Any]) -> str:
    """Construct tailored initial argument prompt for each council role."""
    metrics_summary = context["metrics_summary_text"]
    user_query = context["user_query"]
    domain_snippet = context["domain_text"][:2500] if context["domain_text"] else "[No explicit domain PDDL provided]"
    problem_snippet = context["problem_text"][:2500] if context["problem_text"] else "[No explicit problem PDDL provided]"

    common_header = f"""You are participating in the AI Planning Council for the Agentic Explainable Planning Platform (AEPP).

User Request / Problem Description:
{user_query}

{metrics_summary}

PDDL Domain Specification:
```pddl
{domain_snippet}
```

PDDL Problem Specification:
```pddl
{problem_snippet}
```
"""

    if role_id == "optimal":
        return common_header + """
YOUR ROLE: OPTIMAL PLANNING SPECIALIST (Optimal Agent)
Specialization: A* search, admissible heuristics (LM-cut, merge-and-shrink), guarantees of minimal cost, lower-bound estimates, and state space feasibility analysis.

Your Task:
1. Provide a rigorous argument advocating for (or assessing the feasibility of) an OPTIMAL search strategy for this specific problem.
2. Analyze whether the state space and branching factor permit optimal search within standard memory (e.g., 4GB) and time limits.
3. Recommend specific planner search flags (e.g., Fast Downward 'astar(lmcut())' or 'astar(merge_and_shrink())').
4. Propose a concrete CPU timeout budget in seconds (e.g., 30s, 60s, 120s, 300s).
5. State clearly under what conditions optimal search guarantees minimal cost without risking combinatorial explosion.
"""

    elif role_id == "satisficing":
        return common_header + """
YOUR ROLE: SATISFICING PLANNING SPECIALIST (Satisficing Agent)
Specialization: Heuristic search trade-offs, LAMA (iterated greedy search with landmarks and FF), multi-heuristic search, goal count relaxation, and balancing plan cost vs runtime.

Your Task:
1. Provide a compelling argument advocating for a SATISFICING search strategy for this specific problem.
2. Explain the trade-offs between plan cost and search time: why spending exponential effort on guaranteed optimality is inefficient or risky here.
3. Recommend specific planner search flags (e.g., Fast Downward '--alias seq-sat-lama-2011' or 'lazy_greedy([ff()], preferred=[ff()])').
4. Propose a concrete CPU timeout budget in seconds (e.g., 30s, 60s, 120s).
5. Explain how multiple heuristics, preferred operators, or landmarks will guide the search around plateaus.
"""

    else:  # agile
        return common_header + """
YOUR ROLE: AGILE PLANNING SPECIALIST (Agile Agent)
Specialization: Fast first-plan discovery, satisfiability under tight deadlines, greedy search, unit-cost relaxation, and emergency plan synthesis.

Your Task:
1. Provide a compelling argument advocating for an AGILE (fast first-cut) search strategy for this specific problem.
2. Emphasize the critical importance of low latency, rapid satisfiability, and early plan validation under tight constraints.
3. Recommend specific agile planner search flags (e.g., Fast Downward 'lazy_greedy([ff()], preferred=[ff()])', unit-cost, 'bfs', or 'lama-first').
4. Propose a tight CPU timeout budget in seconds (e.g., 10s, 15s, 30s).
5. Warn against the danger of heavier heuristics exhausting time budgets before returning any executable plan.
"""


def _generate_fallback_stage1(role_id: str, context: Dict[str, Any]) -> str:
    """Generate high-fidelity domain-aware argument when API key is missing or call fails."""
    metrics = context["metrics"]
    obj_cnt = metrics.get("objects_count", 0)
    act_cnt = metrics.get("actions_count", 0)
    goal_cnt = metrics.get("goals_count", 0)
    domain_name = metrics.get("domain_name", "domain")
    prob_name = metrics.get("problem_name", "problem")

    if role_id == "optimal":
        if obj_cnt <= 6 and goal_cnt <= 3:
            feasibility = "highly feasible and strongly recommended"
            budget = 30
        else:
            feasibility = "demanding but viable with aggressive pruning"
            budget = 120
        return f"""### Strategy Proposal: OPTIMAL PLANNING (A* with Admissible Heuristics)
**Agent**: Optimal Agent (A* Specialist)
**Target Profile**: `optimal`
**Recommended Configuration**: `astar(lmcut())` (Landmark-Cut Heuristic)
**Proposed CPU Timeout Budget**: {budget} seconds

#### Structural Analysis & State Space Assessment:
- **Domain**: `{domain_name}` | **Problem**: `{prob_name}`
- **Objects**: {obj_cnt} | **Actions**: {act_cnt} | **Goals**: {goal_cnt}
- **State Space Evaluation**: Optimal search is {feasibility}. Because planning quality is essential, settling for sub-optimal actions risks irreversible cost overhead.

#### Technical Justification:
1. **Optimality Guarantees**: LM-Cut computes an admissible estimate by finding disjunctive action landmarks over delete-relaxation graphs, ensuring zero cost overestimation.
2. **Combinatorial Risk**: With {obj_cnt} objects, the grounding factor remains bounded. The admissible heuristic prunes unpromising branches effectively.
3. **Execution Flags**:
   - Fast Downward: `--search "astar(lmcut())"`
   - Memory Limit: 4096 MB | Timeout: {budget}s
"""

    elif role_id == "satisficing":
        budget = 60
        return f"""### Strategy Proposal: SATISFICING PLANNING (LAMA Multi-Heuristic)
**Agent**: Satisficing Agent (Heuristic Trade-off Specialist)
**Target Profile**: `satisficing`
**Recommended Configuration**: `--alias seq-sat-lama-2011` or `lazy_greedy([ff()], preferred=[ff()])`
**Proposed CPU Timeout Budget**: {budget} seconds

#### Structural Analysis & State Space Assessment:
- **Domain**: `{domain_name}` | **Problem**: `{prob_name}`
- **Objects**: {obj_cnt} | **Actions**: {act_cnt} | **Goals**: {goal_cnt}
- **Trade-off Evaluation**: Guaranteeing strict optimality is computationally wasteful when a high-quality satisficing plan can be obtained in orders of magnitude less time.

#### Technical Justification:
1. **LAMA Multi-Heuristic Search**: Combines the Fast-Forward (FF) heuristic with causal landmark counts and preferred operators.
2. **Plateau Navigation**: Alternating open lists prevent search stagnation in local plateaus without exponential node generation.
3. **Execution Flags**:
   - Fast Downward: `--alias seq-sat-lama-2011` (or `lazy_greedy([ff()], preferred=[ff()])`)
   - Timeout: {budget}s | Iterative improvement enabled
"""

    else:  # agile
        budget = 15
        return f"""### Strategy Proposal: AGILE PLANNING (Fast First-Plan Discovery)
**Agent**: Agile Agent (Fast-Greedy Specialist)
**Target Profile**: `agile`
**Recommended Configuration**: `lazy_greedy([ff()], preferred=[ff()])` with unit cost
**Proposed CPU Timeout Budget**: {budget} seconds

#### Structural Analysis & State Space Assessment:
- **Domain**: `{domain_name}` | **Problem**: `{prob_name}`
- **Objects**: {obj_cnt} | **Actions**: {act_cnt} | **Goals**: {goal_cnt}
- **Urgency Evaluation**: In operational decision support, an executable plan delivered in {budget}s is infinitely superior to a theoretically optimal plan that times out.

#### Technical Justification:
1. **Aggressive Greedy Search**: Evaluates minimal node states and follows preferred operators immediately to reach goal states rapidly.
2. **Low Overhead**: Avoids heavy admissible heuristic computations (like LM-cut) which dominate per-node expansion time.
3. **Execution Flags**:
   - Fast Downward: `--search "lazy_greedy([ff()], preferred=[ff()])"`
   - Timeout: {budget}s (Fail-fast agile cutoff)
"""


async def stage1_collect_responses(
    user_query: str,
    domain_text: str = "",
    problem_text: str = "",
    role_models: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Stage 1: Collect tailored strategy arguments from the 3 specialized planning agents.

    Returns:
        List of dicts with keys: 'role', 'agent_name', 'model', 'response'
    """
    context = prepare_planning_context(user_query, domain_text, problem_text)

    roles = ["optimal", "satisficing", "agile"]
    tasks = []

    for role_id in roles:
        role_cfg = PLANNING_COUNCIL_ROLES[role_id]
        model = (role_models or {}).get(role_id, role_cfg["model"])
        prompt = _build_stage1_prompt_for_role(role_id, context)
        messages = [
            {"role": "system", "content": f"You are the {role_cfg['name']}. {role_cfg['description']}"},
            {"role": "user", "content": prompt},
        ]
        tasks.append(query_model(model, messages, timeout=60.0))

    raw_responses = await asyncio.gather(*tasks)

    stage1_results: List[Dict[str, Any]] = []
    for role_id, resp in zip(roles, raw_responses):
        role_cfg = PLANNING_COUNCIL_ROLES[role_id]
        if resp and resp.get("content"):
            content = resp["content"]
        else:
            # Fallback domain-aware reasoning if API unavailable
            content = _generate_fallback_stage1(role_id, context)

        stage1_results.append({
            "role": role_id,
            "agent_name": role_cfg["name"],
            "model": role_cfg["model"],
            "response": content,
        })

    return stage1_results


# ============================================================================
# Stage 2: Peer Review & Critique
# ============================================================================

def _build_stage2_peer_review_prompt(
    context: Dict[str, Any],
    stage1_results: List[Dict[str, Any]],
    reviewer_role: str,
) -> str:
    """Build peer review prompt critiquing competing proposals on combinatorial risks."""
    metrics_summary = context["metrics_summary_text"]
    user_query = context["user_query"]
    reviewer_cfg = PLANNING_COUNCIL_ROLES.get(reviewer_role, {})

    proposals_text = ""
    for idx, res in enumerate(stage1_results):
        label = chr(65 + idx)  # Response A, Response B, Response C
        proposals_text += f"\n\n--- Response {label} ({res.get('agent_name', 'Agent')}) ---\n{res.get('response', '')}\n"

    return f"""You are the {reviewer_cfg.get('name', 'Reviewer Agent')} participating in Stage 2 (Peer Review) of the AI Planning Council.

Problem Under Consideration:
{user_query}

{metrics_summary}

Below are the 3 Strategy Proposals submitted by the council members in Stage 1:
{proposals_text}

YOUR TASK:
1. Critically evaluate each proposal based on:
   - **Risk of Combinatorial Explosion**: Given the {context['metrics'].get('objects_count', 0)} objects and {context['metrics'].get('actions_count', 0)} action schemas, does the proposed strategy risk memory exhaustion or state explosion?
   - **Need for Plan Optimality**: Is cost minimisation strictly necessary, or does satisficing provide the better operational value?
   - **Timeout Budget Viability**: Is the proposed CPU budget realistic?
2. Critique each response individually (strengths and potential failure modes).
3. At the very end of your response, provide your definitive ranking of the proposals from best to worst.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as:
FINAL RANKING:
1. Response X
2. Response Y
3. Response Z

Now provide your peer review evaluation:"""


def _generate_fallback_stage2(
    reviewer_role: str,
    context: Dict[str, Any],
    stage1_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str],
) -> str:
    """Fallback peer review text when API is unavailable."""
    obj_cnt = context["metrics"].get("objects_count", 0)
    goal_cnt = context["metrics"].get("goals_count", 0)

    # Determine sensible default ranking based on problem size
    labels = list(label_to_model.keys())  # ["Response A", "Response B", "Response C"]
    if len(labels) < 3:
        labels = ["Response A", "Response B", "Response C"]

    # If small problem: Optimal > Satisficing > Agile
    # If medium/large problem: Satisficing > Agile > Optimal
    if obj_cnt <= 5 and goal_cnt <= 2:
        top_pref = labels[0]  # Optimal
        mid_pref = labels[1]  # Satisficing
        bot_pref = labels[2]  # Agile
        eval_reason = f"Given the compact state space ({obj_cnt} objects), optimal search incurs virtually zero explosion risk while guaranteeing minimum cost."
    else:
        top_pref = labels[1]  # Satisficing
        mid_pref = labels[2]  # Agile
        bot_pref = labels[0]  # Optimal
        eval_reason = f"Given {obj_cnt} objects and {goal_cnt} goals, A* with admissible heuristics carries severe risk of combinatorial state space blowup. Satisficing provides the optimal pragmatic balance."

    return f"""### Peer Review Critique by {PLANNING_COUNCIL_ROLES.get(reviewer_role, {}).get('name', reviewer_role)}

1. **Evaluation of Response A (Optimal Strategy)**:
   - *Strengths*: Guarantees minimal plan cost; rigorous lower-bound estimates.
   - *Risks*: If the state space expands exponentially, admissible heuristics like LM-cut may encounter memory exhaustion before finding the goal.

2. **Evaluation of Response B (Satisficing Strategy)**:
   - *Strengths*: LAMA multi-heuristic search navigates large state spaces reliably using landmark guidance and preferred operators.
   - *Risks*: Does not guarantee minimum cost, though iteratively improves plans.

3. **Evaluation of Response C (Agile Strategy)**:
   - *Strengths*: Minimal latency, excellent fail-fast protection under tight budgets.
   - *Risks*: May return longer paths with unnecessary action steps.

**Synthesis**: {eval_reason}

FINAL RANKING:
1. {top_pref}
2. {mid_pref}
3. {bot_pref}"""


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    domain_text: str = "",
    problem_text: str = "",
    role_models: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Stage 2: Each planning agent critiques the others and produces a ranked evaluation."""
    context = prepare_planning_context(user_query, domain_text, problem_text)

    # Label responses: Response A, Response B, Response C
    labels = [chr(65 + i) for i in range(len(stage1_results))]
    label_to_model = {
        f"Response {label}": result.get("model", "")
        for label, result in zip(labels, stage1_results)
    }

    roles = ["optimal", "satisficing", "agile"]
    tasks = []

    for idx, role_id in enumerate(roles):
        model = (role_models or {}).get(role_id, PLANNING_COUNCIL_ROLES[role_id]["model"])
        prompt = _build_stage2_peer_review_prompt(context, stage1_results, role_id)
        messages = [
            {"role": "system", "content": f"You are the {PLANNING_COUNCIL_ROLES[role_id]['name']} reviewing peer proposals."},
            {"role": "user", "content": prompt},
        ]
        tasks.append(query_model(model, messages, timeout=60.0))

    raw_responses = await asyncio.gather(*tasks)

    stage2_results: List[Dict[str, Any]] = []
    for role_id, resp in zip(roles, raw_responses):
        role_cfg = PLANNING_COUNCIL_ROLES[role_id]
        if resp and resp.get("content"):
            full_text = resp["content"]
        else:
            full_text = _generate_fallback_stage2(role_id, context, stage1_results, label_to_model)

        parsed = parse_ranking_from_text(full_text)
        stage2_results.append({
            "role": role_id,
            "agent_name": role_cfg["name"],
            "model": (role_models or {}).get(role_id, role_cfg["model"]),
            "ranking": full_text,
            "parsed_ranking": parsed,
        })

    return stage2_results, label_to_model


# ============================================================================
# Stage 3: Judge Verdict (Chairman) & Decision Extraction
# ============================================================================

def parse_judge_decision(judge_text: str) -> Dict[str, Any]:
    """Extract strict JSON decision block from the Judge response.

    Expected format:
    {
      "strategy": "satisficing",
      "budget_seconds": 60,
      "search_configuration": "lama",
      "justification_summary": "..."
    }
    """
    default_decision = {
        "strategy": "satisficing",
        "budget_seconds": 60,
        "search_configuration": "lazy_greedy([ff()], preferred=[ff()])",
        "justification_summary": "Balanced heuristic search selected to mitigate combinatorial risk.",
    }

    if not judge_text:
        return default_decision

    # Search for JSON markdown block or raw JSON object containing "strategy"
    patterns = [
        r"```(?:json)?\s*(\{[\s\S]*?\"strategy\"[\s\S]*?\})\s*```",
        r"(\{[\s\S]*?\"strategy\"[\s\S]*?\})",
    ]

    for pat in patterns:
        matches = re.findall(pat, judge_text, re.IGNORECASE)
        if matches:
            # Use the last matching JSON block (which should be at the end of the text)
            for candidate in reversed(matches):
                try:
                    data = json.loads(candidate.strip())
                    if isinstance(data, dict) and "strategy" in data:
                        strategy = str(data.get("strategy", "satisficing")).lower().strip()
                        if strategy not in ("optimal", "satisficing", "agile"):
                            strategy = "satisficing"

                        try:
                            budget = float(data.get("budget_seconds", 60))
                        except (ValueError, TypeError):
                            budget = 60.0

                        return {
                            "strategy": strategy,
                            "budget_seconds": budget,
                            "search_configuration": str(data.get("search_configuration", "")),
                            "justification_summary": str(data.get("justification_summary", "")),
                        }
                except json.JSONDecodeError:
                    continue

    return default_decision


def _build_stage3_judge_prompt(
    context: Dict[str, Any],
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
) -> str:
    """Build the prompt for the Judge Agent (Chairman)."""
    metrics_summary = context["metrics_summary_text"]
    user_query = context["user_query"]

    stage1_text = "\n\n".join([
        f"### {r.get('agent_name', 'Agent')} ({r.get('role', 'unknown')}):\n{r.get('response', '')}"
        for r in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"### {r.get('agent_name', 'Reviewer')} Critique:\n{r.get('ranking', '')}"
        for r in stage2_results
    ])

    return f"""You are the Judge Agent, Chairman of the AI Planning Council in the Agentic Explainable Planning Platform (AEPP).

Your Responsibility:
Synthesize the arguments and peer reviews from the Optimal, Satisficing, and Agile agents, evaluate them against concrete structural properties of the problem, and render an Explainable Planning Decision (XAI).

Problem Under Deliberation:
{user_query}

{metrics_summary}

STAGE 1 - Initial Strategy Proposals:
{stage1_text}

STAGE 2 - Peer Critiques & Rankings:
{stage2_text}

YOUR VERDICT INSTRUCTIONS:
1. Provide a comprehensive Explainable Decision (XAI) report:
   - **Executive Analysis**: Characterize the state space scale, branching factor, and constraints.
   - **Deliberation Assessment**: Weigh the Optimal, Satisficing, and Agile arguments. Identify key trade-offs and point out flaws in rejected proposals.
   - **Verdict Rationale**: Give a clear human-readable justification citing specific problem properties (e.g., number of objects, predicates, goal count).
2. Specify the exact planner configuration and timeout budget.
3. AT THE VERY END OF YOUR RESPONSE, OUTPUT STRICTLY THE FOLLOWING JSON BLOCK (no trailing commentary):
```json
{{
  "strategy": "<optimal|satisficing|agile>",
  "budget_seconds": <number>,
  "search_configuration": "<recommended flags or search alias>",
  "justification_summary": "<concise 1-2 sentence human-readable rationale>"
}}
```"""


def _generate_fallback_stage3(
    context: Dict[str, Any],
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
) -> str:
    """Fallback Judge response when API is unavailable."""
    metrics = context["metrics"]
    obj_cnt = metrics.get("objects_count", 0)
    goal_cnt = metrics.get("goals_count", 0)
    act_cnt = metrics.get("actions_count", 0)
    domain_name = metrics.get("domain_name", "domain")
    prob_name = metrics.get("problem_name", "problem")

    if obj_cnt <= 5 and goal_cnt <= 2:
        strategy = "optimal"
        budget = 30
        config = "astar(lmcut())"
        justification = (
            f"Problem '{prob_name}' has a compact state space ({obj_cnt} objects, {goal_cnt} goals). "
            f"A* with LM-cut guarantees minimal cost without risk of combinatorial explosion."
        )
    elif obj_cnt > 15:
        strategy = "agile"
        budget = 20
        config = "lazy_greedy([ff()], preferred=[ff()])"
        justification = (
            f"With {obj_cnt} objects and high branching factor, heavier heuristics risk timeout. "
            f"Agile greedy search secures rapid first-plan satisfiability within budget."
        )
    else:
        strategy = "satisficing"
        budget = 60
        config = "--alias seq-sat-lama-2011"
        justification = (
            f"With {obj_cnt} objects and {goal_cnt} goals, satisficing LAMA multi-heuristic search "
            f"balances search speed with good plan quality while avoiding A* memory exhaustion."
        )

    json_block = json.dumps({
        "strategy": strategy,
        "budget_seconds": budget,
        "search_configuration": config,
        "justification_summary": justification,
    }, indent=2)

    return f"""## Explainable AI Planning Decision (Judge Verdict)
**Chairman**: {JUDGE_ROLE['name']}
**Domain**: `{domain_name}` | **Problem**: `{prob_name}`

### 1. Executive Analysis & Problem Scale
The problem instance presents {obj_cnt} objects, {act_cnt} actions, and {goal_cnt} goal conditions.
The estimated scale is **{context['scale_indicator']}**.

### 2. Evaluation of Council Deliberation
- **Optimal Agent**: Strongly argued for A* admissibility. While zero-cost guarantees are desirable, heavy heuristics scale exponentially as objects increase.
- **Satisficing Agent**: Highlighted that LAMA landmark heuristics navigate plateaus smoothly without exponential node generation.
- **Agile Agent**: Emphasized fast first-cut satisfiability. Useful for emergency or dynamic plans, but may accept unnecessary plan length overhead.

### 3. Verdict Rationale
{justification}

### 4. Technical Strategy Specification
- **Selected Profile**: `{strategy}`
- **Planner Flags**: `{config}`
- **CPU Timeout Budget**: {budget}s

```json
{json_block}
```"""


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    domain_text: str = "",
    problem_text: str = "",
    role_models: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Stage 3: Chairman synthesizes final answer and produces explainable decision with strict JSON."""
    context = prepare_planning_context(user_query, domain_text, problem_text)
    prompt = _build_stage3_judge_prompt(context, stage1_results, stage2_results)

    messages = [
        {"role": "system", "content": f"You are the {JUDGE_ROLE['name']}. {JUDGE_ROLE['description']}"},
        {"role": "user", "content": prompt},
    ]

    judge_model = (role_models or {}).get("judge", CHAIRMAN_MODEL)
    response = await query_model(judge_model, messages, timeout=90.0)

    if response and response.get("content"):
        full_text = response["content"]
    else:
        full_text = _generate_fallback_stage3(context, stage1_results, stage2_results)

    decision = parse_judge_decision(full_text)

    return {
        "model": judge_model,
        "agent_name": JUDGE_ROLE["name"],
        "response": full_text,
        "decision": decision,
    }


# ============================================================================
# Utility & Orchestration Functions
# ============================================================================

def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """Parse the FINAL RANKING section from the model's response."""
    if "FINAL RANKING:" in ranking_text:
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            numbered_matches = re.findall(r"\d+\.\s*Response [A-Z]", ranking_section)
            if numbered_matches:
                return [re.search(r"Response [A-Z]", m).group() for m in numbered_matches]

            matches = re.findall(r"Response [A-Z]", ranking_section)
            if matches:
                return matches

    matches = re.findall(r"Response [A-Z]", ranking_text)
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Calculate aggregate rankings across all models."""
    from collections import defaultdict

    model_positions = defaultdict(list)

    for ranking in stage2_results:
        ranking_text = ranking.get("ranking", "")
        parsed_ranking = parse_ranking_from_text(ranking_text)

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append({
                "model": model,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions),
            })

    aggregate.sort(key=lambda x: x["average_rank"])
    return aggregate


async def generate_conversation_title(user_query: str) -> str:
    """Generate a short title for an AEPP planning session."""
    context = prepare_planning_context(user_query)
    metrics = context.get("metrics", {})
    prob_name = metrics.get("problem_name", "")
    dom_name = metrics.get("domain_name", "")

    if prob_name and prob_name != "custom-problem":
        return f"Planning: {dom_name} / {prob_name}"

    title_prompt = f"""Generate a concise title (3-5 words maximum) for this planning task.
Do not use quotes.
Task: {user_query[:300]}
Title:"""

    messages = [{"role": "user", "content": title_prompt}]
    resp = await query_model("google/gemini-2.5-flash", messages, timeout=15.0)

    if resp and resp.get("content"):
        title = resp["content"].strip().strip("\"'")
        if len(title) > 50:
            title = title[:47] + "..."
        return title

    return "AI Planning Council Deliberation"


async def run_full_council(
    user_query: str,
    domain_text: str = "",
    problem_text: str = "",
    role_models: Optional[Dict[str, str]] = None,
) -> Tuple[List, List, Dict, Dict]:
    """Run the complete 3-stage AI planning council process."""
    # Stage 1: Collect individual arguments from the 3 specialized agents
    stage1_results = await stage1_collect_responses(user_query, domain_text, problem_text, role_models)

    # Stage 2: Peer reviews and ranking
    stage2_results, label_to_model = await stage2_collect_rankings(
        user_query, stage1_results, domain_text, problem_text, role_models
    )

    # Calculate aggregate rankings
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

    # Stage 3: Judge synthesizes final explainable verdict
    stage3_result = await stage3_synthesize_final(
        user_query, stage1_results, stage2_results, domain_text, problem_text, role_models
    )

    # Prepare metadata with planning decision
    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings,
        "planning_decision": stage3_result.get("decision", {}),
    }

    return stage1_results, stage2_results, stage3_result, metadata
