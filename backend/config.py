"""Configuration for the Agentic Explainable Planning Platform (AEPP) Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Specialized Council Agent Roles for Classical & Explainable AI Planning
PLANNING_COUNCIL_ROLES = {
    "optimal": {
        "role_id": "optimal",
        "name": "Optimal Agent",
        "title": "A* Admissible Planning Specialist",
        "description": (
            "Specializes in A* search, admissible heuristics, optimality guarantees, "
            "lower-bound estimates, and detects whether problem state space permits optimal "
            "search within memory/time bounds."
        ),
        "model": os.getenv("OPTIMAL_AGENT_MODEL", "openai/gpt-5.1"),
        "preferred_heuristics": ["lmcut", "merge_and_shrink", "blind"],
        "default_budget": 120,
    },
    "satisficing": {
        "role_id": "satisficing",
        "name": "Satisficing Agent",
        "title": "Heuristic Search & LAMA Specialist",
        "description": (
            "Specializes in heuristic search trade-offs, LAMA, multi-heuristic search, "
            "goal count relaxation, and balancing plan cost vs runtime."
        ),
        "model": os.getenv("SATISFICING_AGENT_MODEL", "anthropic/claude-sonnet-4.5"),
        "preferred_heuristics": ["lama", "hff", "cea", "hadd"],
        "default_budget": 60,
    },
    "agile": {
        "role_id": "agile",
        "name": "Agile Agent",
        "title": "Fast-Greedy & First-Plan Specialist",
        "description": (
            "Specializes in fast first-plan discovery, satisfiability under tight deadlines, "
            "greedy search, and emergency plan synthesis."
        ),
        "model": os.getenv("AGILE_AGENT_MODEL", "google/gemini-3-pro-preview"),
        "preferred_heuristics": ["lazy_greedy", "bfs", "unit_cost"],
        "default_budget": 15,
    },
}

JUDGE_ROLE = {
    "role_id": "judge",
    "name": "Judge Agent",
    "title": "Explainable Planning Chairman & Arbiter",
    "description": (
        "The chairman that evaluates the three arguments based on problem characteristics "
        "(objects, predicates, branching factor) and makes the final planner strategy choice."
    ),
    "model": os.getenv("CHAIRMAN_MODEL", "google/gemini-3-pro-preview"),
}

# Council models list for backwards compatibility
COUNCIL_MODELS = [
    PLANNING_COUNCIL_ROLES["optimal"]["model"],
    PLANNING_COUNCIL_ROLES["satisficing"]["model"],
    PLANNING_COUNCIL_ROLES["agile"]["model"],
]

# Chairman model for backwards compatibility
CHAIRMAN_MODEL = JUDGE_ROLE["model"]

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage
DATA_DIR = "data/conversations"
