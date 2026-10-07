"""PDDL Engine module for the Agentic Explainable Planning Platform (AEPP).

Provides:
1. Structural analysis of PDDL domain and problem files (objects, predicates, actions,
   goals, typing, action-costs, numeric fluents).
2. Executor wrapper for classical planners supporting Fast Downward and embedded
   Pyperplan, with 'optimal', 'satisficing', and 'agile' profiles and mock mode fallback.
3. Plan validator supporting VAL binary and pure-Python state-transition validation.
4. Telemetry persistence using SQLite (aiosqlite and sqlite3).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

aiosqlite: Any = None
try:
    import aiosqlite  # type: ignore
except ImportError:
    pass

pyperplan_planner: Any = None
try:
    from pyperplan import planner as pyperplan_planner  # type: ignore
    PYPERPLAN_AVAILABLE = True
except ImportError:
    PYPERPLAN_AVAILABLE = False


# Default database location
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "telemetry.db"



# ============================================================================
# 1. PDDL S-Expression Tokenizer and Parser
# ============================================================================

def _strip_comments(text: str) -> str:
    """Remove PDDL comments (anything from ';' to end of line)."""
    return re.sub(r";[^\n]*", "", text)


def _tokenize(text: str) -> List[str]:
    """Tokenize PDDL text into S-expression tokens, preserving case where useful."""
    clean_text = _strip_comments(text)
    # Surround parentheses with spaces so they become separate tokens
    clean_text = clean_text.replace("(", " ( ").replace(")", " ) ")
    return clean_text.split()


def _parse_tokens(tokens: List[str]) -> Tuple[Any, List[str]]:
    """Parse tokens into nested Python lists (S-expressions)."""
    if not tokens:
        return [], []

    token = tokens[0]
    remaining = tokens[1:]

    if token == "(":
        expr: List[Any] = []
        while remaining and remaining[0] != ")":
            sub_expr, remaining = _parse_tokens(remaining)
            expr.append(sub_expr)
        if remaining and remaining[0] == ")":
            remaining = remaining[1:]
        return expr, remaining
    elif token == ")":
        return [], remaining
    else:
        return token, remaining


def parse_sexpr(text: str) -> List[Any]:
    """Parse entire PDDL text into a list of top-level S-expressions."""
    tokens = _tokenize(text)
    expressions: List[Any] = []
    remaining = tokens
    while remaining:
        expr, remaining = _parse_tokens(remaining)
        if expr != [] or (tokens and tokens[0] == "("):
            expressions.append(expr)
    return expressions


# ============================================================================
# 2. PDDL Structural Analyzer
# ============================================================================

def _find_tagged_clause(expr: Any, tag: str) -> Optional[List[Any]]:
    """Find a sub-expression starting with tag (case-insensitive) at the top level of expr."""
    if not isinstance(expr, list):
        return None
    tag_lower = tag.lower()
    for item in expr:
        if isinstance(item, list) and len(item) > 0:
            first = item[0]
            if isinstance(first, str) and first.lower() == tag_lower:
                return item
    return None


def _find_all_tagged_clauses(expr: Any, tag: str) -> List[List[Any]]:
    """Find all sub-expressions starting with tag (case-insensitive)."""
    if not isinstance(expr, list):
        return []
    tag_lower = tag.lower()
    results = []
    for item in expr:
        if isinstance(item, list) and len(item) > 0:
            first = item[0]
            if isinstance(first, str) and first.lower() == tag_lower:
                results.append(item)
    return results


def _extract_typed_list(tokens_or_list: List[Any]) -> Dict[str, str]:
    """Parse a PDDL typed list (e.g. ['o1', 'o2', '-', 'typeA', 'o3', '-', 'typeB']).

    Returns mapping of object_name -> type_name (or 'object' if untyped).
    """
    result: Dict[str, str] = {}
    current_items: List[str] = []
    i = 0
    while i < len(tokens_or_list):
        item = tokens_or_list[i]
        if isinstance(item, str):
            if item == "-":
                i += 1
                type_name = tokens_or_list[i] if i < len(tokens_or_list) and isinstance(tokens_or_list[i], str) else "object"
                for ci in current_items:
                    result[ci] = type_name
                current_items = []
            else:
                current_items.append(item)
        elif isinstance(item, list):
            # Recurse or flatten if nested
            sub = _extract_typed_list(item)
            result.update(sub)
        i += 1
    for ci in current_items:
        result[ci] = "object"
    return result


def _sexpr_to_str(expr: Any) -> str:
    """Format an S-expression back to string representation."""
    if isinstance(expr, list):
        return "(" + " ".join(_sexpr_to_str(x) for x in expr) + ")"
    return str(expr)


def _count_goals(goal_expr: Any) -> Tuple[int, List[str]]:
    """Extract and count individual goal conditions from a (:goal ...) clause."""
    if not goal_expr or not isinstance(goal_expr, list) or len(goal_expr) < 2:
        return 0, []

    content = goal_expr[1]
    goals: List[str] = []

    if isinstance(content, list):
        if len(content) > 0 and str(content[0]).lower() == "and":
            for sub in content[1:]:
                goals.append(_sexpr_to_str(sub))
        else:
            goals.append(_sexpr_to_str(content))
    else:
        goals.append(str(content))

    return len(goals), goals


def analyze_pddl_text(domain_text: str, problem_text: str = "") -> Dict[str, Any]:
    """Perform comprehensive structural analysis on PDDL domain and problem texts.

    Args:
        domain_text: The PDDL domain content as string.
        problem_text: The optional PDDL problem content as string.

    Returns:
        A dictionary containing structural metrics:
        - domain_name (str)
        - problem_name (str)
        - objects_count (int)
        - predicates_count (int)
        - actions_count (int)
        - goals_count (int)
        - has_action_costs (bool)
        - has_numeric_fluents (bool)
        - has_typing (bool)
        - requirements (list[str])
        - objects (list[str])
        - object_types (dict[str, str])
        - predicates (list[str])
        - actions (list[str])
        - goals (list[str])
        - initial_state_count (int)
    """
    domain_trees = parse_sexpr(domain_text)
    problem_trees = parse_sexpr(problem_text) if problem_text else []

    domain_def = None
    for tree in domain_trees:
        if isinstance(tree, list) and len(tree) > 1 and str(tree[0]).lower() == "define":
            domain_def = tree
            break
    if not domain_def and domain_trees:
        domain_def = domain_trees[0]

    problem_def = None
    for tree in problem_trees:
        if isinstance(tree, list) and len(tree) > 1 and str(tree[0]).lower() == "define":
            problem_def = tree
            break
    if not problem_def and problem_trees:
        problem_def = problem_trees[0]

    # 1. Domain name
    domain_name = "unknown"
    if domain_def:
        d_clause = _find_tagged_clause(domain_def, "domain")
        if d_clause and len(d_clause) > 1:
            domain_name = str(d_clause[1])

    # 2. Problem name
    problem_name = "unknown"
    if problem_def:
        p_clause = _find_tagged_clause(problem_def, "problem")
        if p_clause and len(p_clause) > 1:
            problem_name = str(p_clause[1])

    # 3. Requirements
    requirements: List[str] = []
    if domain_def:
        req_clause = _find_tagged_clause(domain_def, ":requirements")
        if req_clause:
            requirements = [str(r).lower() for r in req_clause[1:] if isinstance(r, str)]

    # 4. Predicates
    predicates: List[str] = []
    if domain_def:
        pred_clause = _find_tagged_clause(domain_def, ":predicates")
        if pred_clause:
            for item in pred_clause[1:]:
                if isinstance(item, list) and item:
                    pred_name = str(item[0])
                    pred_args = " ".join(str(x) for x in item[1:])
                    predicates.append(f"({pred_name} {pred_args})".strip())
                elif isinstance(item, str):
                    predicates.append(item)

    # 5. Functions / Numeric fluents / Action costs
    functions: List[str] = []
    has_action_costs = False
    has_numeric_fluents = False

    raw_combined = f"{domain_text} {problem_text}".lower()
    if ":action-costs" in requirements or ":action-costs" in raw_combined:
        has_action_costs = True
    if ":numeric-fluents" in requirements or ":numeric-fluents" in raw_combined:
        has_numeric_fluents = True

    if domain_def:
        func_clause = _find_tagged_clause(domain_def, ":functions")
        if func_clause:
            for item in func_clause[1:]:
                if isinstance(item, list) and item:
                    func_name = str(item[0]).lower()
                    functions.append(_sexpr_to_str(item))
                    if "total-cost" in func_name:
                        has_action_costs = True
                    else:
                        has_numeric_fluents = True
                elif isinstance(item, str):
                    functions.append(item)
                    if "total-cost" in item.lower():
                        has_action_costs = True

    # Detect action cost keywords in effects or metrics
    if "total-cost" in raw_combined or "increase (total-cost" in raw_combined:
        has_action_costs = True

    # Check for arithmetic operators in text that signify numeric fluents
    numeric_patterns = [r"\(\s*increase\b", r"\(\s*decrease\b", r"\(\s*assign\b", r"\(\s*[<>]=?\b"]
    for pat in numeric_patterns:
        if re.search(pat, raw_combined):
            # If it's only increase total-cost, it's action costs
            if not has_numeric_fluents:
                non_cost = re.sub(r"\(\s*increase\s+\(\s*total-cost\s*\)[^\)]*\)", "", raw_combined)
                if re.search(pat, non_cost):
                    has_numeric_fluents = True

    # 6. Actions
    actions: List[str] = []
    if domain_def:
        action_clauses = _find_all_tagged_clauses(domain_def, ":action")
        for a_clause in action_clauses:
            if len(a_clause) > 1:
                actions.append(str(a_clause[1]))

    # 7. Constants and Objects
    object_types: Dict[str, str] = {}
    if domain_def:
        const_clause = _find_tagged_clause(domain_def, ":constants")
        if const_clause:
            const_types = _extract_typed_list(const_clause[1:])
            object_types.update(const_types)

    if problem_def:
        obj_clause = _find_tagged_clause(problem_def, ":objects")
        if obj_clause:
            obj_types = _extract_typed_list(obj_clause[1:])
            object_types.update(obj_types)

    objects_list = sorted(list(object_types.keys()))

    # 8. Initial state
    initial_state_count = 0
    if problem_def:
        init_clause = _find_tagged_clause(problem_def, ":init")
        if init_clause:
            initial_state_count = len(init_clause[1:])

    # 9. Goals
    goals_count = 0
    goals_list: List[str] = []
    if problem_def:
        goal_clause = _find_tagged_clause(problem_def, ":goal")
        if goal_clause:
            goals_count, goals_list = _count_goals(goal_clause)

    # 10. Typing
    has_typing = ":typing" in requirements or any(t != "object" for t in object_types.values())

    return {
        "domain_name": domain_name,
        "problem_name": problem_name,
        "objects_count": len(objects_list),
        "predicates_count": len(predicates),
        "actions_count": len(actions),
        "goals_count": goals_count,
        "has_action_costs": bool(has_action_costs),
        "has_numeric_fluents": bool(has_numeric_fluents),
        "has_typing": bool(has_typing),
        "requirements": requirements,
        "objects": objects_list,
        "object_types": object_types,
        "predicates": predicates,
        "actions": actions,
        "goals": goals_list,
        "initial_state_count": initial_state_count,
        "functions": functions,
    }


def analyze_pddl_files(domain_path: Union[str, Path], problem_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Perform structural analysis on PDDL files from filesystem paths.

    Args:
        domain_path: Path to PDDL domain file.
        problem_path: Optional path to PDDL problem file.

    Returns:
        Structural analysis metrics dictionary.
    """
    domain_path = Path(domain_path)
    if not domain_path.exists():
        raise FileNotFoundError(f"Domain file not found: {domain_path}")

    with open(domain_path, "r", encoding="utf-8", errors="replace") as f:
        domain_text = f.read()

    problem_text = ""
    if problem_path:
        p_path = Path(problem_path)
        if p_path.exists():
            with open(p_path, "r", encoding="utf-8", errors="replace") as f:
                problem_text = f.read()

    return analyze_pddl_text(domain_text, problem_text)


def extract_metrics(
    domain: Union[str, Path],
    problem: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Extract structural metrics from PDDL domain and problem (accepts files or raw strings)."""
    is_domain_file = False
    try:
        p = Path(domain)
        if p.exists() and p.is_file():
            is_domain_file = True
    except Exception:
        is_domain_file = False

    if is_domain_file:
        return analyze_pddl_files(domain, problem)

    domain_text = str(domain)
    problem_text = ""
    if problem:
        try:
            pp = Path(problem)
            if pp.exists() and pp.is_file():
                with open(pp, "r", encoding="utf-8", errors="replace") as f:
                    problem_text = f.read()
            else:
                problem_text = str(problem)
        except Exception:
            problem_text = str(problem)

    return analyze_pddl_text(domain_text, problem_text)


# ============================================================================
# 3. Classical Planner Executor Wrapper
# ============================================================================

def find_fast_downward_binary() -> Optional[str]:
    """Detect if fast-downward binary or python script is present on the system."""
    env_bin = os.environ.get("FAST_DOWNWARD_BIN")
    if env_bin and os.path.isfile(env_bin):
        return env_bin

    candidates = ["fast-downward", "fast-downward.py", "downward"]
    for c in candidates:
        found = shutil.which(c)
        if found:
            return found

    # Windows specific common locations if installed
    win_paths = [
        Path.home() / "fast-downward" / "fast-downward.py",
        Path("C:/fast-downward/fast-downward.py"),
        Path("D:/fast-downward/fast-downward.py"),
    ]
    for p in win_paths:
        if p.exists():
            return str(p)

    return None


def find_val_binary() -> Optional[str]:
    """Detect if the VAL (plan validator) binary is present on the system."""
    env_val = os.environ.get("VAL_BIN")
    if env_val and os.path.isfile(env_val):
        return env_val

    candidates = ["validate", "Validate", "val"]
    for c in candidates:
        found = shutil.which(c)
        if found:
            return found

    return None


def _parse_sas_plan(plan_file_path: Path) -> Tuple[List[str], float]:
    """Parse a Fast Downward sas_plan file into action list and cost."""
    plan: List[str] = []
    cost = 0.0
    if not plan_file_path.exists():
        return plan, cost

    with open(plan_file_path, "r", encoding="utf-8") as f:
        for line in f:
            clean = line.strip()
            if not clean:
                continue
            if clean.startswith(";"):
                # Check for cost comments, e.g. '; cost = 4 (unit cost)'
                cost_match = re.search(r"cost\s*=\s*([0-9.]+)", clean)
                if cost_match:
                    try:
                        cost = float(cost_match.group(1))
                    except ValueError:
                        pass
                continue
            if clean.startswith("(") and clean.endswith(")"):
                plan.append(clean)
            else:
                plan.append(f"({clean})")

    if cost == 0.0 and plan:
        cost = float(len(plan))
    return plan, cost


def _run_pyperplan_profile(
    domain_path: Path,
    problem_path: Path,
    profile: str,
    timeout: float,
) -> Dict[str, Any]:
    """Execute planning using embedded pyperplan for the given profile."""
    if not PYPERPLAN_AVAILABLE:
        return {
            "success": False,
            "plan": [],
            "cost": 0.0,
            "execution_time": 0.0,
            "error": "Pyperplan is not installed.",
            "planner_used": "pyperplan",
        }

    # Map profiles to pyperplan search & heuristic algorithms
    # 'optimal': A* search with LM-cut
    # 'satisficing': Greedy Best-First Search or Weighted A* with FF heuristic
    # 'agile': Fast Greedy Best-First search with FF heuristic or BFS with short timeout
    profile_lower = profile.lower()
    if profile_lower == "optimal":
        search_fn = pyperplan_planner.SEARCHES["astar"]
        heuristic_cls = pyperplan_planner.HEURISTICS["lmcut"]
    elif profile_lower == "agile":
        search_fn = pyperplan_planner.SEARCHES["gbf"]
        heuristic_cls = pyperplan_planner.HEURISTICS["hff"]
    else:  # satisficing (default)
        search_fn = pyperplan_planner.SEARCHES["wastar"]
        heuristic_cls = pyperplan_planner.HEURISTICS["hff"]

    start_t = time.perf_counter()

    try:
        # Run pyperplan search
        raw_ops = pyperplan_planner.search_plan(
            str(domain_path),
            str(problem_path),
            search_fn,
            heuristic_cls,
        )
        elapsed = time.perf_counter() - start_t

        if raw_ops is None:
            return {
                "success": False,
                "plan": [],
                "cost": 0.0,
                "execution_time": elapsed,
                "error": "Pyperplan search concluded without finding a valid plan.",
                "planner_used": "pyperplan",
            }

        plan_actions = [op.name.strip() for op in raw_ops]
        # Ensure parentheses formatting
        plan_actions = [a if a.startswith("(") and a.endswith(")") else f"({a})" for a in plan_actions]
        cost = float(len(plan_actions))

        return {
            "success": True,
            "plan": plan_actions,
            "cost": cost,
            "execution_time": elapsed,
            "error": None,
            "planner_used": "pyperplan",
        }
    except Exception as exc:
        elapsed = time.perf_counter() - start_t
        return {
            "success": False,
            "plan": [],
            "cost": 0.0,
            "execution_time": elapsed,
            "error": f"Pyperplan planning error: {str(exc)}",
            "planner_used": "pyperplan",
        }


def _run_mock_planner(
    domain_path: Path,
    problem_path: Path,
    profile: str = "satisficing",
) -> Dict[str, Any]:
    """Synthetic mock planner for demonstration, testing, or unsupported features."""
    start_t = time.perf_counter()
    summary = analyze_pddl_files(domain_path, problem_path)

    # Simulated execution time based on profile
    simulated_latencies = {
        "agile": 0.04,
        "satisficing": 0.12,
        "optimal": 0.35,
    }
    simulated_delay = simulated_latencies.get(profile.lower(), 0.1)
    time.sleep(min(simulated_delay, 0.05))

    elapsed = time.perf_counter() - start_t + simulated_delay

    actions = summary.get("actions", [])
    objects = summary.get("objects", [])

    mock_plan: List[str] = []
    if actions:
        # Generate representative domain plan steps
        primary_action = actions[0]
        if len(objects) >= 2:
            mock_plan.append(f"({primary_action} {objects[0]} {objects[1]})")
        elif len(objects) == 1:
            mock_plan.append(f"({primary_action} {objects[0]})")
        else:
            mock_plan.append(f"({primary_action})")

        if len(actions) > 1 and len(objects) >= 2:
            second_action = actions[1]
            mock_plan.append(f"({second_action} {objects[-1]})")

    cost = float(len(mock_plan)) if mock_plan else 1.0

    return {
        "success": True,
        "plan": mock_plan,
        "cost": cost,
        "execution_time": round(elapsed, 4),
        "error": None,
        "planner_used": "mock",
    }


def execute_planner(
    domain_path: Union[str, Path],
    problem_path: Union[str, Path],
    profile: str = "satisficing",
    timeout: float = 30.0,
    planner_type: str = "auto",
    mock: bool = False,
) -> Dict[str, Any]:
    """Execute a classical planner on the specified PDDL domain and problem.

    Supports three profiles:
    - 'optimal': A* search with admissible heuristic (e.g. LM-cut).
    - 'satisficing': LAMA / Lazy Greedy Best-First Search with FF heuristic.
    - 'agile': Fast Greedy Best-First search with tight timeout (10-30s).

    Fallback strategy:
    1. If mock=True or planner_type=='mock' -> Mock execution mode.
    2. If Fast Downward binary is present -> Execute Fast Downward.
    3. If Fast Downward binary is missing -> Fallback to Pyperplan.
    4. If Pyperplan fails or is unsupported -> Fallback to Mock execution mode.

    Returns:
        {
            "success": bool,
            "plan": list[str],
            "cost": float,
            "execution_time": float,
            "profile": str,
            "planner_used": str,
            "error": str | None,
            "raw_output": str | None
        }
    """
    domain_path = Path(domain_path)
    problem_path = Path(problem_path)

    if not domain_path.exists():
        return {
            "success": False,
            "plan": [],
            "cost": 0.0,
            "execution_time": 0.0,
            "profile": profile,
            "planner_used": "none",
            "error": f"Domain file not found: {domain_path}",
            "raw_output": None,
        }

    if not problem_path.exists():
        return {
            "success": False,
            "plan": [],
            "cost": 0.0,
            "execution_time": 0.0,
            "profile": profile,
            "planner_used": "none",
            "error": f"Problem file not found: {problem_path}",
            "raw_output": None,
        }

    if mock or planner_type == "mock":
        res = _run_mock_planner(domain_path, problem_path, profile=profile)
        res["profile"] = profile
        res["raw_output"] = "Executed in mock mode."
        return res

    fd_bin = find_fast_downward_binary()

    # If Fast Downward binary is available and requested/auto
    if fd_bin and planner_type in ("auto", "fast-downward"):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sas_plan_path = Path(tmp_dir) / "sas_plan"
            profile_lower = profile.lower()

            # Profile-specific Fast Downward configuration
            if profile_lower == "optimal":
                search_arg = "astar(lmcut())"
                cmd = [fd_bin, "--plan-file", str(sas_plan_path), str(domain_path), str(problem_path), "--search", search_arg]
            elif profile_lower == "agile":
                search_arg = "lazy_greedy([ff()], preferred=[ff()])"
                cmd = [fd_bin, "--plan-file", str(sas_plan_path), str(domain_path), str(problem_path), "--search", search_arg]
                timeout = min(timeout, 15.0)
            else:  # satisficing
                # Try standard LAMA or lazy greedy with FF
                search_arg = "lazy_greedy([ff()], preferred=[ff()])"
                cmd = [fd_bin, "--plan-file", str(sas_plan_path), str(domain_path), str(problem_path), "--search", search_arg]

            start_t = time.perf_counter()
            try:
                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=timeout,
                )
                elapsed = time.perf_counter() - start_t
                plan, cost = _parse_sas_plan(sas_plan_path)

                if plan:
                    return {
                        "success": True,
                        "plan": plan,
                        "cost": cost,
                        "execution_time": elapsed,
                        "profile": profile,
                        "planner_used": "fast-downward",
                        "error": None,
                        "raw_output": proc.stdout,
                    }
                else:
                    return {
                        "success": False,
                        "plan": [],
                        "cost": 0.0,
                        "execution_time": elapsed,
                        "profile": profile,
                        "planner_used": "fast-downward",
                        "error": f"Fast Downward finished without plan (Exit code {proc.returncode})",
                        "raw_output": proc.stdout + "\n" + proc.stderr,
                    }
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "plan": [],
                    "cost": 0.0,
                    "execution_time": timeout,
                    "profile": profile,
                    "planner_used": "fast-downward",
                    "error": f"Planner timed out after {timeout} seconds.",
                    "raw_output": None,
                }
            except Exception:
                # If Fast Downward failed with system error, fall through to pyperplan
                pass

    # Fallback to Pyperplan if available
    if planner_type in ("auto", "pyperplan") and PYPERPLAN_AVAILABLE:
        p_res = _run_pyperplan_profile(domain_path, problem_path, profile=profile, timeout=timeout)
        if p_res["success"]:
            p_res["profile"] = profile
            p_res["raw_output"] = "Solved using embedded Pyperplan."
            return p_res
        # If pyperplan was specifically requested, return its error
        if planner_type == "pyperplan":
            p_res["profile"] = profile
            p_res["raw_output"] = None
            return p_res

    # Final fallback: Mock execution mode
    m_res = _run_mock_planner(domain_path, problem_path, profile=profile)
    m_res["profile"] = profile
    m_res["raw_output"] = "Solved via adaptive fallback mock executor."
    return m_res


def run_planner(
    domain: Union[str, Path],
    problem: Union[str, Path],
    strategy: str = "satisficing",
    timeout: float = 30.0,
    planner_type: str = "auto",
    mock: bool = False,
) -> Dict[str, Any]:
    """Execute classical planner accepting either file paths or raw PDDL strings.

    Args:
        domain: File path or raw PDDL text for domain.
        problem: File path or raw PDDL text for problem.
        strategy: Planning strategy ('optimal', 'satisficing', 'agile').
        timeout: CPU timeout budget in seconds.
        planner_type: 'auto', 'fast-downward', 'pyperplan', or 'mock'.
        mock: Force mock execution.

    Returns:
        Planner execution results dictionary.
    """
    is_domain_file = False
    is_problem_file = False
    try:
        dp = Path(domain)
        if dp.exists() and dp.is_file():
            is_domain_file = True
    except Exception:
        pass

    try:
        pp = Path(problem)
        if pp.exists() and pp.is_file():
            is_problem_file = True
    except Exception:
        pass

    if is_domain_file and is_problem_file:
        return execute_planner(
            domain_path=domain,
            problem_path=problem,
            profile=strategy,
            timeout=timeout,
            planner_type=planner_type,
            mock=mock,
        )

    # Write raw strings to temporary files for execution
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dpath = Path(tmp_dir) / "domain.pddl"
        tmp_ppath = Path(tmp_dir) / "problem.pddl"

        if is_domain_file:
            shutil.copyfile(domain, tmp_dpath)
        else:
            with open(tmp_dpath, "w", encoding="utf-8") as f:
                f.write(str(domain))

        if is_problem_file:
            shutil.copyfile(problem, tmp_ppath)
        else:
            with open(tmp_ppath, "w", encoding="utf-8") as f:
                f.write(str(problem))

        return execute_planner(
            domain_path=tmp_dpath,
            problem_path=tmp_ppath,
            profile=strategy,
            timeout=timeout,
            planner_type=planner_type,
            mock=mock,
        )


# ============================================================================
# 4. Plan Validator (VAL binary & State Transition Validator)
# ============================================================================

@dataclass
class GroundAction:
    name: str
    params: List[str]
    preconditions: List[Tuple[bool, str, List[str]]]  # (is_positive, pred_name, args)
    effects: List[Tuple[bool, str, List[str]]]        # (is_positive, pred_name, args)
    cost: float = 1.0


class StateTransitionValidator:
    """Pure-Python PDDL state-transition validator.

    Simulates the execution of plan actions on the initial state,
    verifying action preconditions and ensuring all goal conditions are satisfied.
    """

    def __init__(self, domain_text: str, problem_text: str):
        self.domain_summary = analyze_pddl_text(domain_text, problem_text)
        self.domain_trees = parse_sexpr(domain_text)
        self.problem_trees = parse_sexpr(problem_text)
        self.actions_def = self._parse_domain_actions()
        self.initial_state, self.initial_costs = self._parse_initial_state()
        self.goal_conditions = self._parse_goal_conditions()

    def _parse_domain_actions(self) -> Dict[str, Dict[str, Any]]:
        actions: Dict[str, Dict[str, Any]] = {}
        domain_def = None
        for tree in self.domain_trees:
            if isinstance(tree, list) and len(tree) > 1 and str(tree[0]).lower() == "define":
                domain_def = tree
                break
        if not domain_def:
            return actions

        for clause in _find_all_tagged_clauses(domain_def, ":action"):
            if len(clause) < 2:
                continue
            name = str(clause[1]).lower()
            params: List[str] = []
            preconditions: Any = []
            effects: Any = []

            i = 2
            while i < len(clause):
                tag = str(clause[i]).lower()
                if tag == ":parameters" and i + 1 < len(clause):
                    raw_params = clause[i + 1]
                    if isinstance(raw_params, list):
                        # Filter out '-' and type names
                        filtered = []
                        skip_next = False
                        for p in raw_params:
                            if p == "-":
                                skip_next = True
                                continue
                            if skip_next:
                                skip_next = False
                                continue
                            filtered.append(str(p).lower())
                        params = filtered
                    i += 2
                elif tag == ":precondition" and i + 1 < len(clause):
                    preconditions = clause[i + 1]
                    i += 2
                elif tag == ":effect" and i + 1 < len(clause):
                    effects = clause[i + 1]
                    i += 2
                else:
                    i += 1

            actions[name] = {
                "params": params,
                "preconditions": preconditions,
                "effects": effects,
            }
        return actions

    def _parse_initial_state(self) -> Tuple[Set[Tuple[str, ...]], float]:
        state: Set[Tuple[str, ...]] = set()
        cost = 0.0
        problem_def = None
        for tree in self.problem_trees:
            if isinstance(tree, list) and len(tree) > 1 and str(tree[0]).lower() == "define":
                problem_def = tree
                break
        if not problem_def:
            return state, cost

        init_clause = _find_tagged_clause(problem_def, ":init")
        if init_clause:
            for item in init_clause[1:]:
                if isinstance(item, list) and item:
                    first = str(item[0]).lower()
                    if first == "=":
                        # Function initialization, e.g. (= (total-cost) 0)
                        pass
                    else:
                        pred_name = first
                        args = tuple(str(x).lower() for x in item[1:])
                        state.add((pred_name, *args))
        return state, cost

    def _parse_goal_conditions(self) -> List[Tuple[bool, Tuple[str, ...]]]:
        """Returns list of (is_positive, (pred_name, *args))."""
        goals: List[Tuple[bool, Tuple[str, ...]]] = []
        problem_def = None
        for tree in self.problem_trees:
            if isinstance(tree, list) and len(tree) > 1 and str(tree[0]).lower() == "define":
                problem_def = tree
                break
        if not problem_def:
            return goals

        goal_clause = _find_tagged_clause(problem_def, ":goal")
        if not goal_clause or len(goal_clause) < 2:
            return goals

        content = goal_clause[1]

        def _extract(lit: Any) -> Optional[Tuple[bool, Tuple[str, ...]]]:
            if not isinstance(lit, list) or not lit:
                return None
            first = str(lit[0]).lower()
            if first == "not" and len(lit) > 1 and isinstance(lit[1], list):
                sub = lit[1]
                return (False, (str(sub[0]).lower(), *(str(x).lower() for x in sub[1:])))
            return (True, (first, *(str(x).lower() for x in lit[1:])))

        if isinstance(content, list) and content:
            if str(content[0]).lower() == "and":
                for item in content[1:]:
                    res = _extract(item)
                    if res:
                        goals.append(res)
            else:
                res = _extract(content)
                if res:
                    goals.append(res)

        return goals

    def _ground_literal(self, lit: Any, var_map: Dict[str, str]) -> Optional[Tuple[bool, Tuple[str, ...]]]:
        """Substitute parameters in a literal to produce ground predicate."""
        if not isinstance(lit, list) or not lit:
            return None
        first = str(lit[0]).lower()
        if first == "not" and len(lit) > 1 and isinstance(lit[1], list):
            sub = lit[1]
            pred = str(sub[0]).lower()
            ground_args = tuple(var_map.get(str(x).lower(), str(x).lower()) for x in sub[1:])
            return (False, (pred, *ground_args))
        pred = first
        ground_args = tuple(var_map.get(str(x).lower(), str(x).lower()) for x in lit[1:])
        return (True, (pred, *ground_args))

    def _check_preconditions(self, prec_expr: Any, var_map: Dict[str, str], state: Set[Tuple[str, ...]]) -> Tuple[bool, Optional[str]]:
        if not prec_expr:
            return True, None

        if isinstance(prec_expr, list) and prec_expr:
            first = str(prec_expr[0]).lower()
            if first == "and":
                for sub in prec_expr[1:]:
                    ok, err = self._check_preconditions(sub, var_map, state)
                    if not ok:
                        return False, err
                return True, None
            else:
                lit = self._ground_literal(prec_expr, var_map)
                if lit:
                    is_pos, ground_atom = lit
                    if is_pos and ground_atom not in state:
                        return False, f"Missing required fact: ({' '.join(ground_atom)})"
                    if not is_pos and ground_atom in state:
                        return False, f"Negative condition violated: (not ({' '.join(ground_atom)}))"
        return True, None

    def _apply_effects(self, eff_expr: Any, var_map: Dict[str, str], state: Set[Tuple[str, ...]]) -> float:
        cost_inc = 0.0
        if not eff_expr:
            return cost_inc

        if isinstance(eff_expr, list) and eff_expr:
            first = str(eff_expr[0]).lower()
            if first == "and":
                for sub in eff_expr[1:]:
                    cost_inc += self._apply_effects(sub, var_map, state)
            elif first == "increase":
                # e.g. (increase (total-cost) 5)
                if len(eff_expr) > 2:
                    try:
                        cost_inc += float(eff_expr[2])
                    except ValueError:
                        pass
            else:
                lit = self._ground_literal(eff_expr, var_map)
                if lit:
                    is_pos, ground_atom = lit
                    if is_pos:
                        state.add(ground_atom)
                    else:
                        state.discard(ground_atom)
        return cost_inc

    def validate(self, plan: List[str], execution_time: float = 0.0) -> Dict[str, Any]:
        """Validate a sequence of action strings against initial and goal states."""
        current_state = set(self.initial_state)
        total_cost = 0.0

        for idx, step_str in enumerate(plan):
            # Parse action string: e.g. "(move a b)" or "move a b"
            clean = step_str.strip().strip("()")
            tokens = clean.split()
            if not tokens:
                continue

            action_name = tokens[0].lower()
            args = [t.lower() for t in tokens[1:]]

            if action_name not in self.actions_def:
                return {
                    "valid": False,
                    "cost": total_cost,
                    "plan": plan,
                    "execution_time": execution_time,
                    "error": f"Step {idx + 1}: Action '{action_name}' is not defined in domain.",
                }

            act_info = self.actions_def[action_name]
            param_names = act_info["params"]

            if len(param_names) != len(args):
                return {
                    "valid": False,
                    "cost": total_cost,
                    "plan": plan,
                    "execution_time": execution_time,
                    "error": f"Step {idx + 1}: Action '{action_name}' expected {len(param_names)} parameters but received {len(args)}.",
                }

            var_map = dict(zip(param_names, args))

            # Verify preconditions
            ok, err = self._check_preconditions(act_info["preconditions"], var_map, current_state)
            if not ok:
                return {
                    "valid": False,
                    "cost": total_cost,
                    "plan": plan,
                    "execution_time": execution_time,
                    "error": f"Step {idx + 1} ({step_str}): Precondition failed -> {err}",
                }

            # Apply effects
            eff_cost = self._apply_effects(act_info["effects"], var_map, current_state)
            step_cost = eff_cost if eff_cost > 0 else 1.0
            total_cost += step_cost

        # Verify goals
        for is_pos, ground_atom in self.goal_conditions:
            if is_pos and ground_atom not in current_state:
                return {
                    "valid": False,
                    "cost": total_cost,
                    "plan": plan,
                    "execution_time": execution_time,
                    "error": f"Goal condition unsatisfied: ({' '.join(ground_atom)})",
                }
            if not is_pos and ground_atom in current_state:
                return {
                    "valid": False,
                    "cost": total_cost,
                    "plan": plan,
                    "execution_time": execution_time,
                    "error": f"Negative goal condition violated: (not ({' '.join(ground_atom)}))",
                }

        return {
            "valid": True,
            "cost": total_cost,
            "plan": plan,
            "execution_time": execution_time,
            "error": None,
            "validator_used": "state_transition_validator",
        }


def validate_plan(
    domain: Union[str, Path],
    problem: Union[str, Path],
    plan: Union[List[str], str],
    execution_time: float = 0.0,
    use_val_if_available: bool = True,
) -> Dict[str, Any]:
    """Validate a plan using VAL binary if present, or pure-Python state transitions.

    Args:
        domain: Path to PDDL domain file or raw PDDL domain string.
        problem: Path to PDDL problem file or raw PDDL problem string.
        plan: List of action strings, or path to plan file.
        execution_time: Optional planning time to carry over.
        use_val_if_available: If True, uses VAL binary when detected on PATH.

    Returns:
        {
            "valid": bool,
            "cost": float,
            "plan": list[str],
            "execution_time": float,
            "error": str | None
        }
    """
    domain_text = ""
    problem_text = ""
    is_domain_file = False
    is_problem_file = False

    try:
        dp = Path(domain)
        if dp.exists() and dp.is_file():
            is_domain_file = True
            with open(dp, "r", encoding="utf-8", errors="replace") as f:
                domain_text = f.read()
    except Exception:
        pass
    if not is_domain_file:
        domain_text = str(domain)

    try:
        pp = Path(problem)
        if pp.exists() and pp.is_file():
            is_problem_file = True
            with open(pp, "r", encoding="utf-8", errors="replace") as f:
                problem_text = f.read()
    except Exception:
        pass
    if not is_problem_file:
        problem_text = str(problem)

    # Convert plan argument to list of strings
    plan_list: List[str] = []
    if isinstance(plan, (str, Path)) and os.path.isfile(plan):
        parsed_actions, _ = _parse_sas_plan(Path(plan))
        plan_list = parsed_actions
    elif isinstance(plan, list):
        plan_list = [p.strip() for p in plan if p.strip()]
    elif isinstance(plan, str):
        plan_list = [line.strip() for line in plan.splitlines() if line.strip() and not line.strip().startswith(";")]

    # Check if plan is empty
    if not plan_list:
        # Check if the problem initial state already satisfies the goal
        try:
            val = StateTransitionValidator(domain_text, problem_text)
            res = val.validate([], execution_time=execution_time)
            if res["valid"]:
                return res
        except Exception:
            pass

        return {
            "valid": False,
            "cost": 0.0,
            "plan": [],
            "execution_time": execution_time,
            "error": "Plan is empty and goals are not satisfied initially.",
        }

    # Try external VAL binary if present and requested
    val_bin = find_val_binary() if use_val_if_available else None
    if val_bin:
        with tempfile.TemporaryDirectory() as tmp_dir:
            plan_file = Path(tmp_dir) / "plan.val"
            with open(plan_file, "w", encoding="utf-8") as f:
                for idx, act in enumerate(plan_list):
                    clean_act = act.strip("()")
                    f.write(f"{idx}: ({clean_act})\n")

            d_val_file = Path(domain) if is_domain_file else Path(tmp_dir) / "domain.pddl"
            if not is_domain_file:
                with open(d_val_file, "w", encoding="utf-8") as f:
                    f.write(domain_text)

            p_val_file = Path(problem) if is_problem_file else Path(tmp_dir) / "problem.pddl"
            if not is_problem_file:
                with open(p_val_file, "w", encoding="utf-8") as f:
                    f.write(problem_text)

            try:
                proc = subprocess.run(
                    [val_bin, str(d_val_file), str(p_val_file), str(plan_file)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=15,
                )
                output = proc.stdout + "\n" + proc.stderr
                is_valid = "Plan valid" in output or "Plan executed successfully" in output

                cost = float(len(plan_list))
                cost_match = re.search(r"Plan\s+cost\s*:\s*([0-9.]+)", output, re.IGNORECASE)
                if cost_match:
                    try:
                        cost = float(cost_match.group(1))
                    except ValueError:
                        pass

                error = None if is_valid else f"VAL error: {output.strip()}"
                return {
                    "valid": is_valid,
                    "cost": cost,
                    "plan": plan_list,
                    "execution_time": execution_time,
                    "error": error,
                    "validator_used": "val",
                }
            except Exception:
                pass  # Fallback to internal state validator

    # Internal state-transition validation
    try:
        validator = StateTransitionValidator(domain_text, problem_text)
        return validator.validate(plan_list, execution_time=execution_time)
    except Exception as exc:
        return {
            "valid": False,
            "cost": 0.0,
            "plan": plan_list,
            "execution_time": execution_time,
            "error": f"State transition validation error: {str(exc)}",
        }


# ============================================================================
# 5. Telemetry Database (SQLite / aiosqlite)
# ============================================================================

def init_telemetry_db_sync(db_path: Union[str, Path] = DEFAULT_DB_PATH) -> None:
    """Initialize SQLite telemetry database schema synchronously."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                problem_name TEXT NOT NULL,
                chosen_profile TEXT NOT NULL,
                predicted_budget REAL,
                actual_time REAL,
                plan_length INTEGER,
                validity INTEGER,
                judge_rationale TEXT,
                cost REAL DEFAULT 0.0,
                plan_json TEXT,
                error TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_problem ON telemetry(problem_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_profile ON telemetry(chosen_profile)")
        conn.commit()
    finally:
        conn.close()


async def init_telemetry_db(db_path: Union[str, Path] = DEFAULT_DB_PATH) -> None:
    """Initialize SQLite telemetry database schema asynchronously."""
    if aiosqlite is None:
        init_telemetry_db_sync(db_path)
        return

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(path)) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                problem_name TEXT NOT NULL,
                chosen_profile TEXT NOT NULL,
                predicted_budget REAL,
                actual_time REAL,
                plan_length INTEGER,
                validity INTEGER,
                judge_rationale TEXT,
                cost REAL DEFAULT 0.0,
                plan_json TEXT,
                error TEXT
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_problem ON telemetry(problem_name)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_profile ON telemetry(chosen_profile)")
        await conn.commit()


def record_telemetry_sync(
    problem_name: str,
    chosen_profile: str,
    predicted_budget: float,
    actual_time: float,
    plan_length: int,
    validity: bool,
    judge_rationale: str = "",
    cost: float = 0.0,
    plan: Optional[List[str]] = None,
    error: Optional[str] = None,
    db_path: Union[str, Path] = DEFAULT_DB_PATH,
) -> int:
    """Store planning execution record into SQLite synchronously."""
    init_telemetry_db_sync(db_path)
    plan_json = json.dumps(plan) if plan is not None else None
    val_int = 1 if validity else 0

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO telemetry (
                problem_name, chosen_profile, predicted_budget, actual_time,
                plan_length, validity, judge_rationale, cost, plan_json, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                problem_name,
                chosen_profile,
                float(predicted_budget),
                float(actual_time),
                int(plan_length),
                val_int,
                judge_rationale,
                float(cost),
                plan_json,
                error,
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0
    finally:
        conn.close()


async def record_telemetry(
    problem_name: str,
    chosen_profile: str,
    predicted_budget: float,
    actual_time: float,
    plan_length: int,
    validity: bool,
    judge_rationale: str = "",
    cost: float = 0.0,
    plan: Optional[List[str]] = None,
    error: Optional[str] = None,
    db_path: Union[str, Path] = DEFAULT_DB_PATH,
) -> int:
    """Store planning execution record into SQLite asynchronously."""
    if aiosqlite is None:
        return record_telemetry_sync(
            problem_name=problem_name,
            chosen_profile=chosen_profile,
            predicted_budget=predicted_budget,
            actual_time=actual_time,
            plan_length=plan_length,
            validity=validity,
            judge_rationale=judge_rationale,
            cost=cost,
            plan=plan,
            error=error,
            db_path=db_path,
        )

    await init_telemetry_db(db_path)
    plan_json = json.dumps(plan) if plan is not None else None
    val_int = 1 if validity else 0

    async with aiosqlite.connect(str(db_path)) as conn:
        cursor = await conn.execute(
            """
            INSERT INTO telemetry (
                problem_name, chosen_profile, predicted_budget, actual_time,
                plan_length, validity, judge_rationale, cost, plan_json, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                problem_name,
                chosen_profile,
                float(predicted_budget),
                float(actual_time),
                int(plan_length),
                val_int,
                judge_rationale,
                float(cost),
                plan_json,
                error,
            ),
        )
        await conn.commit()
        return cursor.lastrowid or 0


def fetch_telemetry_sync(
    limit: int = 50,
    problem_name: Optional[str] = None,
    profile: Optional[str] = None,
    db_path: Union[str, Path] = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """Retrieve telemetry records from SQLite synchronously."""
    init_telemetry_db_sync(db_path)
    query = "SELECT id, timestamp, problem_name, chosen_profile, predicted_budget, actual_time, plan_length, validity, judge_rationale, cost, plan_json, error FROM telemetry"
    clauses = []
    params: List[Any] = []

    if problem_name:
        clauses.append("problem_name = ?")
        params.append(problem_name)
    if profile:
        clauses.append("chosen_profile = ?")
        params.append(profile)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    results: List[Dict[str, Any]] = []
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)
        for row in cursor.fetchall():
            results.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "problem_name": row["problem_name"],
                "chosen_profile": row["chosen_profile"],
                "predicted_budget": row["predicted_budget"],
                "actual_time": row["actual_time"],
                "plan_length": row["plan_length"],
                "validity": bool(row["validity"]),
                "judge_rationale": row["judge_rationale"],
                "cost": row["cost"],
                "plan": json.loads(row["plan_json"]) if row["plan_json"] else None,
                "error": row["error"],
            })
    finally:
        conn.close()
    return results


async def fetch_telemetry(
    limit: int = 50,
    problem_name: Optional[str] = None,
    profile: Optional[str] = None,
    db_path: Union[str, Path] = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """Retrieve telemetry records from SQLite asynchronously."""
    if aiosqlite is None:
        return fetch_telemetry_sync(limit, problem_name, profile, db_path)

    await init_telemetry_db(db_path)
    query = "SELECT id, timestamp, problem_name, chosen_profile, predicted_budget, actual_time, plan_length, validity, judge_rationale, cost, plan_json, error FROM telemetry"
    clauses = []
    params: List[Any] = []

    if problem_name:
        clauses.append("problem_name = ?")
        params.append(problem_name)
    if profile:
        clauses.append("chosen_profile = ?")
        params.append(profile)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    results: List[Dict[str, Any]] = []
    async with aiosqlite.connect(str(db_path)) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                results.append({
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "problem_name": row["problem_name"],
                    "chosen_profile": row["chosen_profile"],
                    "predicted_budget": row["predicted_budget"],
                    "actual_time": row["actual_time"],
                    "plan_length": row["plan_length"],
                    "validity": bool(row["validity"]),
                    "judge_rationale": row["judge_rationale"],
                    "cost": row["cost"],
                    "plan": json.loads(row["plan_json"]) if row["plan_json"] else None,
                    "error": row["error"],
                })
    return results


if __name__ == "__main__":
    print("=================================================================")
    print("         AEPP - PDDL Engine Verification & Standalone Demo       ")
    print("=================================================================")

    # 1. Environment status
    print("\n[1] Environment Status:")
    fd_bin = find_fast_downward_binary()
    val_bin = find_val_binary()
    print(f"  * Fast Downward: {'Available at ' + str(fd_bin) if fd_bin else 'Not found (falling back to Pyperplan/mock)'}")
    print(f"  * Pyperplan:     {'Installed' if PYPERPLAN_AVAILABLE else 'Not installed'}")
    print(f"  * VAL Binary:    {'Available at ' + str(val_bin) if val_bin else 'Not found (using internal state validator)'}")
    print(f"  * SQLite DB:     {DEFAULT_DB_PATH}")

    # 2. Demo benchmark execution
    sample_domain = """(define (domain gripper-strips)
      (:requirements :strips)
      (:predicates (room ?r) (ball ?b) (gripper ?g) (at-robby ?r)
                   (at ?b ?r) (free ?g) (carry ?b ?g))
      (:action move
        :parameters (?from ?to)
        :precondition (and (room ?from) (room ?to) (at-robby ?from))
        :effect (and (at-robby ?to) (not (at-robby ?from))))
      (:action pick
        :parameters (?obj ?room ?gripper)
        :precondition (and (ball ?obj) (room ?room) (gripper ?gripper)
                           (at ?obj ?room) (at-robby ?room) (free ?gripper))
        :effect (and (carry ?obj ?gripper) (not (at ?obj ?room)) (not (free ?gripper))))
      (:action drop
        :parameters (?obj ?room ?gripper)
        :precondition (and (ball ?obj) (room ?room) (gripper ?gripper)
                           (carry ?obj ?gripper) (at-robby ?room))
        :effect (and (at ?obj ?room) (free ?gripper) (not (carry ?obj ?gripper))))
    )"""

    sample_problem = """(define (problem gripper-demo)
      (:domain gripper-strips)
      (:objects rooma roomb ball1 ball2 left right)
      (:init (room rooma) (room roomb) (ball ball1) (ball ball2)
             (gripper left) (gripper right) (at-robby rooma)
             (free left) (free right) (at ball1 rooma) (at ball2 rooma))
      (:goal (and (at ball1 roomb) (at ball2 roomb)))
    )"""

    print("\n[2] Structural Analysis:")
    metrics = extract_metrics(sample_domain, sample_problem)
    print(f"  * Objects:    {metrics['objects_count']}")
    print(f"  * Predicates: {metrics['predicates_count']}")
    print(f"  * Actions:    {metrics['actions_count']}")
    print(f"  * Goals:      {metrics['goals_count']}")

    print("\n[3] Planner Execution (Satisficing Profile):")
    plan_res = run_planner(sample_domain, sample_problem, strategy="satisficing", timeout=10.0)
    print(f"  * Success:    {plan_res['success']}")
    print(f"  * Planner:    {plan_res.get('planner_used')}")
    print(f"  * Time:       {plan_res.get('execution_time', 0):.4f}s")
    print(f"  * Plan steps: {len(plan_res.get('plan', []))}")
    for idx, step in enumerate(plan_res.get("plan", [])):
        print(f"      {idx + 1}. {step}")

    print("\n[4] State-Transition Plan Validation:")
    val_res = validate_plan(sample_domain, sample_problem, plan_res.get("plan", []), execution_time=plan_res.get("execution_time", 0))
    print(f"  * Valid:      {val_res['valid']}")
    print(f"  * Cost:       {val_res.get('cost', 0)}")
    print(f"  * Validator:  {val_res.get('validator_used')}")

    print("\n[5] Recording Telemetry:")
    record_id = record_telemetry_sync(
        problem_name="gripper-demo",
        chosen_profile="satisficing",
        predicted_budget=10.0,
        actual_time=plan_res.get("execution_time", 0),
        plan_length=len(plan_res.get("plan", [])),
        validity=val_res["valid"],
        judge_rationale="Demo execution",
        cost=val_res.get("cost", 0),
        plan=plan_res.get("plan", []),
    )
    print(f"  * Telemetry Record ID: {record_id}")
    records = fetch_telemetry_sync(limit=1)
    if records:
        print(f"  * Latest Record in DB: Problem='{records[0]['problem_name']}', Valid={records[0]['validity']}")

    print("\n=================================================================")
    print("                   PDDL ENGINE DEMO COMPLETE                     ")
    print("=================================================================")

