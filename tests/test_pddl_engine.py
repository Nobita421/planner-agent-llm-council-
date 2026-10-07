"""Tests for backend.pddl_engine."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.pddl_engine import (
    analyze_pddl_text,
    analyze_pddl_files,
    execute_planner,
    validate_plan,
    init_telemetry_db,
    init_telemetry_db_sync,
    record_telemetry,
    record_telemetry_sync,
    fetch_telemetry,
    fetch_telemetry_sync,
    DEFAULT_DB_PATH,
)

SAMPLE_STRIPS_DOMAIN = """
(define (domain blocksworld)
  (:requirements :strips :equality)
  (:predicates
    (on ?x ?y)
    (ontable ?x)
    (clear ?x)
    (handempty)
    (holding ?x)
  )

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

  (:action stack
    :parameters (?x ?y)
    :precondition (and (holding ?x) (clear ?y))
    :effect (and (not (holding ?x)) (not (clear ?y)) (clear ?x) (handempty) (on ?x ?y))
  )

  (:action unstack
    :parameters (?x ?y)
    :precondition (and (on ?x ?y) (clear ?x) (handempty))
    :effect (and (holding ?x) (clear ?y) (not (clear ?x)) (not (handempty)) (not (on ?x ?y)))
  )
)
"""

SAMPLE_STRIPS_PROBLEM = """
(define (problem bw-sussman)
  (:domain blocksworld)
  (:objects a b c)
  (:init
    (ontable a)
    (ontable b)
    (on c a)
    (clear b)
    (clear c)
    (handempty)
  )
  (:goal
    (and
      (on a b)
      (on b c)
    )
  )
)
"""

SAMPLE_NUMERIC_DOMAIN = """
(define (domain rover-numeric)
  (:requirements :strips :typing :numeric-fluents :action-costs)
  (:types rover waypoint)
  (:predicates
    (at ?r - rover ?w - waypoint)
    (can-traverse ?r - rover ?w1 - waypoint ?w2 - waypoint)
  )
  (:functions
    (battery-amount ?r - rover)
    (total-cost)
  )
  (:action drive
    :parameters (?r - rover ?from - waypoint ?to - waypoint)
    :precondition (and (at ?r ?from) (can-traverse ?r ?from ?to))
    :effect (and
      (not (at ?r ?from))
      (at ?r ?to)
      (decrease (battery-amount ?r) 10)
      (increase (total-cost) 5)
    )
  )
)
"""

SAMPLE_NUMERIC_PROBLEM = """
(define (problem rover-p1)
  (:domain rover-numeric)
  (:objects
    r1 - rover
    w1 w2 w3 - waypoint
  )
  (:init
    (at r1 w1)
    (can-traverse r1 w1 w2)
    (can-traverse r1 w2 w3)
    (= (battery-amount r1) 100)
    (= (total-cost) 0)
  )
  (:goal
    (at r1 w3)
  )
  (:metric minimize (total-cost))
)
"""


def test_structural_analysis_strips():
    summary = analyze_pddl_text(SAMPLE_STRIPS_DOMAIN, SAMPLE_STRIPS_PROBLEM)
    assert summary["domain_name"] == "blocksworld"
    assert summary["problem_name"] == "bw-sussman"
    assert summary["predicates_count"] == 5
    assert summary["actions_count"] == 4
    assert summary["objects_count"] == 3
    assert summary["goals_count"] == 2
    assert summary["has_action_costs"] is False
    assert summary["has_numeric_fluents"] is False
    assert "pick-up" in summary["actions"]
    assert "stack" in summary["actions"]
    assert "ontable" in summary["predicates"][1]


def test_structural_analysis_numeric_and_costs():
    summary = analyze_pddl_text(SAMPLE_NUMERIC_DOMAIN, SAMPLE_NUMERIC_PROBLEM)
    assert summary["domain_name"] == "rover-numeric"
    assert summary["problem_name"] == "rover-p1"
    assert summary["has_action_costs"] is True
    assert summary["has_numeric_fluents"] is True
    assert summary["has_typing"] is True
    assert summary["objects_count"] == 4
    assert summary["goals_count"] == 1


def test_planner_execution_pyperplan_profiles():
    with tempfile.TemporaryDirectory() as tmpdir:
        dpath = Path(tmpdir) / "domain.pddl"
        ppath = Path(tmpdir) / "problem.pddl"
        dpath.write_text(SAMPLE_STRIPS_DOMAIN)
        ppath.write_text(SAMPLE_STRIPS_PROBLEM)

        # 1. Optimal Profile
        res_opt = execute_planner(dpath, ppath, profile="optimal")
        assert res_opt["success"] is True
        assert len(res_opt["plan"]) > 0
        assert res_opt["cost"] == 6.0  # Sussman anomaly optimal is 6 steps
        assert res_opt["profile"] == "optimal"

        # 2. Satisficing Profile
        res_sat = execute_planner(dpath, ppath, profile="satisficing")
        assert res_sat["success"] is True
        assert len(res_sat["plan"]) > 0

        # 3. Agile Profile
        res_agile = execute_planner(dpath, ppath, profile="agile")
        assert res_agile["success"] is True
        assert len(res_agile["plan"]) > 0


def test_planner_mock_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        dpath = Path(tmpdir) / "domain.pddl"
        ppath = Path(tmpdir) / "problem.pddl"
        dpath.write_text(SAMPLE_STRIPS_DOMAIN)
        ppath.write_text(SAMPLE_STRIPS_PROBLEM)

        res = execute_planner(dpath, ppath, profile="optimal", mock=True)
        assert res["success"] is True
        assert res["planner_used"] == "mock"
        assert len(res["plan"]) > 0
        assert res["execution_time"] > 0


def test_plan_validation():
    with tempfile.TemporaryDirectory() as tmpdir:
        dpath = Path(tmpdir) / "domain.pddl"
        ppath = Path(tmpdir) / "problem.pddl"
        dpath.write_text(SAMPLE_STRIPS_DOMAIN)
        ppath.write_text(SAMPLE_STRIPS_PROBLEM)

        # Sussman anomaly valid plan:
        # 1. unstack c a
        # 2. put-down c
        # 3. pick-up b
        # 4. stack b c
        # 5. pick-up a
        # 6. stack a b
        valid_plan = [
            "(unstack c a)",
            "(put-down c)",
            "(pick-up b)",
            "(stack b c)",
            "(pick-up a)",
            "(stack a b)",
        ]

        val_res = validate_plan(dpath, ppath, valid_plan, execution_time=0.42, use_val_if_available=False)
        assert val_res["valid"] is True
        assert val_res["error"] is None
        assert val_res["cost"] == 6.0
        assert val_res["execution_time"] == 0.42

        # Invalid plan: wrong precondition
        invalid_plan = [
            "(pick-up a)",  # 'a' has 'c' on it! clear a is false!
        ]
        val_fail = validate_plan(dpath, ppath, invalid_plan, use_val_if_available=False)
        assert val_fail["valid"] is False
        assert "Precondition failed" in val_fail["error"]

        # Incomplete plan: ends before goal achieved
        incomplete_plan = [
            "(unstack c a)",
            "(put-down c)",
        ]
        val_inc = validate_plan(dpath, ppath, incomplete_plan, use_val_if_available=False)
        assert val_inc["valid"] is False
        assert "Goal condition unsatisfied" in val_inc["error"]


def test_telemetry_db_sync_and_async():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        test_db = Path(tmpdir) / "test_telemetry.db"

        # Sync operations
        init_telemetry_db_sync(test_db)
        rec_id1 = record_telemetry_sync(
            problem_name="bw-sussman",
            chosen_profile="optimal",
            predicted_budget=1.5,
            actual_time=0.42,
            plan_length=6,
            validity=True,
            judge_rationale="LM-cut found optimal 6-step solution within budget.",
            cost=6.0,
            plan=["(unstack c a)", "(put-down c)"],
            db_path=test_db,
        )
        assert rec_id1 > 0

        rows = fetch_telemetry_sync(db_path=test_db)
        assert len(rows) == 1
        assert rows[0]["problem_name"] == "bw-sussman"
        assert rows[0]["chosen_profile"] == "optimal"
        assert rows[0]["validity"] is True

        # Async operations
        async def run_async_test():
            await init_telemetry_db(test_db)
            rec_id2 = await record_telemetry(
                problem_name="rover-p1",
                chosen_profile="agile",
                predicted_budget=0.8,
                actual_time=0.15,
                plan_length=4,
                validity=True,
                judge_rationale="Agile profile met fast turnaround constraint.",
                cost=20.0,
                plan=["(drive r1 w1 w2)"],
                db_path=test_db,
            )
            assert rec_id2 > 0

            records = await fetch_telemetry(db_path=test_db)
            assert len(records) == 2
            assert records[0]["problem_name"] == "rover-p1"
            assert records[1]["problem_name"] == "bw-sussman"

        asyncio.run(run_async_test())


if __name__ == "__main__":
    test_structural_analysis_strips()
    test_structural_analysis_numeric_and_costs()
    test_planner_execution_pyperplan_profiles()
    test_planner_mock_mode()
    test_plan_validation()
    test_telemetry_db_sync_and_async()
    print("ALL TESTS PASSED SUCCESSFULLY!")
