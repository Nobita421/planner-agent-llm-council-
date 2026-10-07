"""Tests for the complete AEPP orchestrator pipeline in backend/main.py."""

import asyncio
import sys
from pathlib import Path
from httpx import AsyncClient, ASGITransport

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import app

SAMPLE_DOMAIN = """
(define (domain blocksworld)
  (:requirements :strips)
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

SAMPLE_PROBLEM = """
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


async def test_status_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/pddl-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "pyperplan" in data
        assert "mock_mode_available" in data
        assert data["mock_mode_available"] is True


async def test_solve_pddl_pipeline_success():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "domain_pddl": SAMPLE_DOMAIN,
            "problem_pddl": SAMPLE_PROBLEM,
            "user_constraints": {"max_time": 30},
        }
        resp = await client.post("/api/solve-pddl", json=payload)
        assert resp.status_code == 200, f"Error: {resp.text}"
        data = resp.json()

        # Step 1: Metrics
        assert "metrics" in data
        assert data["metrics"]["domain_name"] == "blocksworld"
        assert data["metrics"]["problem_name"] == "bw-sussman"
        assert data["metrics"]["objects_count"] == 3

        # Step 2: Debate
        assert "debate" in data
        assert len(data["debate"]["stage1"]) == 3
        assert len(data["debate"]["stage2"]) == 3
        assert "judge_verdict" in data["debate"]
        assert "decision" in data["debate"]["judge_verdict"]

        # Step 3 & 4: Execution & Validation
        assert "execution" in data
        assert len(data["execution"]["plan"]) > 0
        assert data["validation"]["valid"] is True
        assert data["validation"]["cost"] > 0

        # Step 6: XAI & Telemetry
        assert len(data["xai_summary"]) > 0
        assert data["telemetry_id"] > 0
        assert data["status"] in ("success", "fallback_success")


async def test_solve_pddl_pipeline_fallback():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Pass a problem with impossible goals to trigger the fallback manager
        unsolvable_problem = """
        (define (problem bw-impossible)
          (:domain blocksworld)
          (:objects a b)
          (:init (ontable a) (clear a) (ontable b) (clear b) (handempty))
          (:goal (and (holding a) (holding b)))
        )
        """
        payload = {
            "domain_pddl": SAMPLE_DOMAIN,
            "problem_pddl": unsolvable_problem,
            "user_constraints": {"max_time": 2, "force_strategy": "optimal"},
        }
        resp = await client.post("/api/solve-pddl", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        # Fallback should have been triggered across strategy ladder
        assert data["execution"]["fallback_triggered"] is True
        assert len(data["execution"]["fallback_history"]) > 0


async def test_telemetry_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/telemetry")
        assert resp.status_code == 200
        data = resp.json()
        assert "records" in data
        assert data["count"] > 0
        latest = data["records"][0]
        assert "problem_name" in latest
        assert "chosen_profile" in latest


if __name__ == "__main__":
    async def main():
        print("Testing /api/pddl-status...")
        await test_status_endpoint()
        print("Testing /api/solve-pddl pipeline (success)...")
        await test_solve_pddl_pipeline_success()
        print("Testing /api/solve-pddl pipeline (fallback)...")
        await test_solve_pddl_pipeline_fallback()
        print("Testing /api/telemetry...")
        await test_telemetry_endpoint()
        print("ALL PIPELINE INTEGRATION TESTS PASSED SUCCESSFULLY!")

    asyncio.run(main())
