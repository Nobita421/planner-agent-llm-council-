"""Tests for specialized planning council orchestration in backend/council.py."""

import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import PLANNING_COUNCIL_ROLES, JUDGE_ROLE, COUNCIL_MODELS, CHAIRMAN_MODEL
from backend.council import (
    extract_pddl_from_text,
    prepare_planning_context,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
    parse_judge_decision,
    run_full_council,
)

SAMPLE_PDDL_QUERY = """
Please solve this planning problem:

(define (domain blocksworld)
  (:requirements :strips)
  (:predicates (on ?x ?y) (ontable ?x) (clear ?x) (handempty) (holding ?x))
  (:action pick-up
    :parameters (?x)
    :precondition (and (clear ?x) (ontable ?x) (handempty))
    :effect (and (not (ontable ?x)) (not (clear ?x)) (not (handempty)) (holding ?x))
  )
  (:action put-down
    :parameters (?x)
    :precondition (holding ?x)
    :effect (and (not (holding ?x)) (clear ?x) (handempty) (ontable ?x))
  )
)

(define (problem bw-p1)
  (:domain blocksworld)
  (:objects a b)
  (:init (ontable a) (clear a) (ontable b) (clear b) (handempty))
  (:goal (holding a))
)
"""


def test_config_roles():
    assert "optimal" in PLANNING_COUNCIL_ROLES
    assert "satisficing" in PLANNING_COUNCIL_ROLES
    assert "agile" in PLANNING_COUNCIL_ROLES

    opt = PLANNING_COUNCIL_ROLES["optimal"]
    assert "A*" in opt["description"]
    assert "lmcut" in opt["preferred_heuristics"]

    sat = PLANNING_COUNCIL_ROLES["satisficing"]
    assert "LAMA" in sat["description"]

    agile = PLANNING_COUNCIL_ROLES["agile"]
    assert "greedy" in agile["description"].lower()

    assert JUDGE_ROLE["name"] == "Judge Agent"
    assert len(COUNCIL_MODELS) == 3
    assert CHAIRMAN_MODEL == JUDGE_ROLE["model"]


def test_context_preparation():
    d_text, p_text = extract_pddl_from_text(SAMPLE_PDDL_QUERY)
    assert "(define (domain blocksworld)" in d_text
    assert "(define (problem bw-p1)" in p_text

    context = prepare_planning_context(SAMPLE_PDDL_QUERY)
    assert context["metrics"]["domain_name"] == "blocksworld"
    assert context["metrics"]["problem_name"] == "bw-p1"
    assert context["metrics"]["objects_count"] == 2
    assert "STRUCTURAL METRICS SUMMARY" in context["metrics_summary_text"]


def test_parse_judge_decision():
    sample_judge_output = """
## Explainable AI Planning Decision
We have analyzed the problem and evaluated the council arguments.

```json
{
  "strategy": "optimal",
  "budget_seconds": 30,
  "search_configuration": "astar(lmcut())",
  "justification_summary": "Small state space allows A* with LM-cut to guarantee minimal cost."
}
```
"""
    decision = parse_judge_decision(sample_judge_output)
    assert decision["strategy"] == "optimal"
    assert decision["budget_seconds"] == 30.0
    assert "astar(lmcut())" in decision["search_configuration"]
    assert "Small state space" in decision["justification_summary"]


def test_full_council_deliberation():
    async def run_test():
        stage1_res, stage2_res, stage3_res, metadata = await run_full_council(SAMPLE_PDDL_QUERY)

        # Stage 1: 3 specialized agents
        assert len(stage1_res) == 3
        roles = [r["role"] for r in stage1_res]
        assert "optimal" in roles
        assert "satisficing" in roles
        assert "agile" in roles
        for r in stage1_res:
            assert len(r["response"]) > 50

        # Stage 2: Peer reviews
        assert len(stage2_res) == 3
        assert "label_to_model" in metadata
        assert len(metadata["aggregate_rankings"]) > 0

        # Stage 3: Judge verdict
        assert "decision" in stage3_res
        decision = stage3_res["decision"]
        assert decision["strategy"] in ("optimal", "satisficing", "agile")
        assert decision["budget_seconds"] > 0
        assert len(decision["justification_summary"]) > 0
        assert metadata["planning_decision"] == decision

    asyncio.run(run_test())


if __name__ == "__main__":
    test_config_roles()
    test_context_preparation()
    test_parse_judge_decision()
    test_full_council_deliberation()
    print("ALL COUNCIL TESTS PASSED SUCCESSFULLY!")
