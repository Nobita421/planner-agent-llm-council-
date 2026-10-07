"""Automated Portfolio & Benchmark Evaluation Test Suite.

Verifies:
1. PDDL Engine execution and plan validation across 6 canonical IPC benchmarks
   (Blocksworld, Gripper, Logistics).
2. Council deliberation, Judge JSON extraction, and XAI rationale.
3. Fallback manager loop recovery and SQLite telemetry persistence.
"""

import asyncio
import os
import sys
from pathlib import Path
from httpx import AsyncClient, ASGITransport

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.pddl_engine import (
    extract_metrics,
    run_planner,
    validate_plan,
    fetch_telemetry,
)
from backend.council import (
    run_full_council,
    parse_judge_decision,
)
from backend.main import app

BENCHMARKS_DIR = Path(__file__).resolve().parent.parent / "benchmarks"


def get_benchmark_cases():
    return [
        {
            "domain_name": "blocksworld",
            "case_name": "Blocksworld Sussman (Simple)",
            "domain_path": BENCHMARKS_DIR / "blocksworld" / "domain.pddl",
            "problem_path": BENCHMARKS_DIR / "blocksworld" / "prob01_simple.pddl",
            "expected_objects": 3,
            "expected_goals": 2,
        },
        {
            "domain_name": "blocksworld",
            "case_name": "Blocksworld 6-Blocks (Complex)",
            "domain_path": BENCHMARKS_DIR / "blocksworld" / "domain.pddl",
            "problem_path": BENCHMARKS_DIR / "blocksworld" / "prob02_complex.pddl",
            "expected_objects": 6,
            "expected_goals": 5,
        },
        {
            "domain_name": "gripper",
            "case_name": "Gripper 2-Balls (Simple)",
            "domain_path": BENCHMARKS_DIR / "gripper" / "domain.pddl",
            "problem_path": BENCHMARKS_DIR / "gripper" / "prob01_simple.pddl",
            "expected_objects": 6,  # 2 rooms + 2 balls + 2 grippers
            "expected_goals": 2,
        },
        {
            "domain_name": "gripper",
            "case_name": "Gripper 6-Balls (Complex)",
            "domain_path": BENCHMARKS_DIR / "gripper" / "domain.pddl",
            "problem_path": BENCHMARKS_DIR / "gripper" / "prob02_complex.pddl",
            "expected_objects": 10,  # 2 rooms + 6 balls + 2 grippers
            "expected_goals": 6,
        },
        {
            "domain_name": "logistics",
            "case_name": "Logistics 1-City (Simple)",
            "domain_path": BENCHMARKS_DIR / "logistics" / "domain.pddl",
            "problem_path": BENCHMARKS_DIR / "logistics" / "prob01_simple.pddl",
            "expected_objects": 5,  # 1 package + 1 truck + 2 locs + 1 city
            "expected_goals": 1,
        },
        {
            "domain_name": "logistics",
            "case_name": "Logistics Multi-City (Complex)",
            "domain_path": BENCHMARKS_DIR / "logistics" / "domain.pddl",
            "problem_path": BENCHMARKS_DIR / "logistics" / "prob02_complex.pddl",
            "expected_objects": 11,
            "expected_goals": 2,
        },
    ]


def test_benchmarks_structural_analysis():
    print("\n--- 1. Testing Benchmark Structural Analysis ---")
    for case in get_benchmark_cases():
        metrics = extract_metrics(case["domain_path"], case["problem_path"])
        assert metrics["objects_count"] == case["expected_objects"], (
            f"{case['case_name']}: Expected {case['expected_objects']} objects, got {metrics['objects_count']}"
        )
        assert metrics["goals_count"] == case["expected_goals"], (
            f"{case['case_name']}: Expected {case['expected_goals']} goals, got {metrics['goals_count']}"
        )
        assert metrics["actions_count"] > 0
        assert metrics["predicates_count"] > 0
        print(f"  [OK] {case['case_name']} -> {metrics['objects_count']} objs, {metrics['actions_count']} acts, {metrics['goals_count']} goals")


def test_benchmarks_planner_and_validation():
    print("\n--- 2. Testing Classical Execution & State-Transition Validation ---")
    # Test execution across profiles on simple & complex benchmarks
    test_subsets = [
        ("Blocksworld Sussman", BENCHMARKS_DIR / "blocksworld" / "domain.pddl", BENCHMARKS_DIR / "blocksworld" / "prob01_simple.pddl", "optimal"),
        ("Gripper 2-Balls", BENCHMARKS_DIR / "gripper" / "domain.pddl", BENCHMARKS_DIR / "gripper" / "prob01_simple.pddl", "satisficing"),
        ("Logistics Simple", BENCHMARKS_DIR / "logistics" / "domain.pddl", BENCHMARKS_DIR / "logistics" / "prob01_simple.pddl", "agile"),
        ("Gripper 6-Balls", BENCHMARKS_DIR / "gripper" / "domain.pddl", BENCHMARKS_DIR / "gripper" / "prob02_complex.pddl", "satisficing"),
    ]

    for name, d_path, p_path, profile in test_subsets:
        res = run_planner(d_path, p_path, strategy=profile, timeout=30.0)
        assert res["success"] is True, f"Failed planning {name} with profile {profile}: {res.get('error')}"
        assert len(res["plan"]) > 0

        # Validate with pure-Python state-transition engine
        val = validate_plan(d_path, p_path, res["plan"], execution_time=res["execution_time"])
        assert val["valid"] is True, f"Validation failed for {name}: {val.get('error')}"
        assert val["cost"] > 0
        print(f"  [OK] {name} [{profile.upper()}] -> Plan Length: {len(res['plan'])}, Cost: {val['cost']}, Time: {res['execution_time']:.3f}s [VALIDATED]")


def test_mock_council_debate_and_judge_parsing():
    print("\n--- 3. Testing Council Deliberation & Judge Strict JSON Extraction ---")
    async def run_debate_test():
        case = get_benchmark_cases()[0]
        with open(case["domain_path"]) as df, open(case["problem_path"]) as pf:
            d_text, p_text = df.read(), pf.read()

        stage1, stage2, stage3, meta = await run_full_council(
            user_query=f"Solve {case['case_name']}",
            domain_text=d_text,
            problem_text=p_text,
        )

        assert len(stage1) == 3
        assert len(stage2) == 3
        assert "decision" in stage3

        dec = stage3["decision"]
        assert dec["strategy"] in ("optimal", "satisficing", "agile")
        assert dec["budget_seconds"] > 0
        assert len(dec["search_configuration"]) > 0
        assert len(dec["justification_summary"]) > 0
        print(f"  [OK] Council Verdict: Strategy='{dec['strategy']}', Budget={dec['budget_seconds']}s, Config='{dec['search_configuration']}'")
        print(f"  [OK] XAI Rationale: {dec['justification_summary']}")

    asyncio.run(run_debate_test())


def test_end_to_end_pipeline_and_fallback():
    print("\n--- 4. Testing End-to-End API Pipeline & Fallback Manager ---")
    async def run_pipeline_test():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Case A: Successful execution on Gripper benchmark
            gripper_case = get_benchmark_cases()[2]
            with open(gripper_case["domain_path"]) as df, open(gripper_case["problem_path"]) as pf:
                payload = {
                    "domain_pddl": df.read(),
                    "problem_pddl": pf.read(),
                    "user_constraints": {"max_time": 30},
                }
            resp = await client.post("/api/solve-pddl", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] in ("success", "fallback_success")
            assert data["validation"]["valid"] is True
            assert len(data["execution"]["plan"]) > 0
            print(f"  [OK] Gripper Benchmark E2E -> Status={data['status']}, Strategy={data['execution']['final_strategy']}, Plan Length={len(data['execution']['plan'])}")

            # Case B: Fallback verification on an unachievable goal
            impossible_pddl = """(define (problem bw-impossible)
              (:domain blocksworld)
              (:objects a b)
              (:init (ontable a) (clear a) (ontable b) (clear b) (handempty))
              (:goal (and (holding a) (holding b)))
            )"""
            with open(get_benchmark_cases()[0]["domain_path"]) as df:
                bw_domain = df.read()

            fail_payload = {
                "domain_pddl": bw_domain,
                "problem_pddl": impossible_pddl,
                "user_constraints": {"max_time": 2, "force_strategy": "optimal"},
            }
            resp_fail = await client.post("/api/solve-pddl", json=fail_payload)
            assert resp_fail.status_code == 200
            data_fail = resp_fail.json()
            assert data_fail["execution"]["fallback_triggered"] is True
            print(f"  [OK] Fallback Ladder Recovery -> Triggered={data_fail['execution']['fallback_triggered']}, History={len(data_fail['execution']['fallback_history'])} steps")

            # Verify telemetry was stored
            telem_resp = await client.get("/api/telemetry?limit=5")
            assert telem_resp.status_code == 200
            telem_data = telem_resp.json()
            assert telem_data["count"] > 0
            print(f"  [OK] SQLite Telemetry -> {telem_data['count']} records stored in telemetry.db")

    asyncio.run(run_pipeline_test())


if __name__ == "__main__":
    print("=================================================================")
    print("      AEPP IPC BENCHMARK & PORTFOLIO VERIFICATION SUITE         ")
    print("=================================================================")
    test_benchmarks_structural_analysis()
    test_benchmarks_planner_and_validation()
    test_mock_council_debate_and_judge_parsing()
    test_end_to_end_pipeline_and_fallback()
    print("\n=================================================================")
    print("  ALL PORTFOLIO BENCHMARK TESTS COMPLETED SUCCESSFULLY! (100%)  ")
    print("=================================================================")
