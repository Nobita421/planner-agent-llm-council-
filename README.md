# Agentic Explainable Planning Platform (AEPP)

![llmcouncil](header.jpg)

The **Agentic Explainable Planning Platform (AEPP)** combines multi-agent LLM council deliberation with classical automated planning engines (Fast Downward, Pyperplan) and state-transition validation. Instead of treating planning as an opaque black box or relying purely on LLM hallucination for action sequences, AEPP leverages specialized AI agents to analyze problem complexity, debate algorithmic search strategies, execute classical solvers, validate plans against formal PDDL semantics, and autonomously recover from solver failures.

---

## 🚀 Key Features

1. **Multi-Agent Deliberation Council**:
   - **Optimal Agent**: Specializes in $A^*$ search, admissible heuristics (LM-Cut, Merge-and-Shrink), optimality bounds, and state-space combinatorial analysis.
   - **Satisficing Agent**: Advocates for heuristic search trade-offs, LAMA, multi-heuristic search, and balancing plan cost against search time.
   - **Agile Agent**: Prioritizes fast first-plan discovery, greedy best-first search, and satisfiability under tight computational deadlines.
   - **Judge / Chairman**: Synthesizes the debate, analyzes problem structural metrics, and renders a structured verdict in strict JSON with an Explainable AI (XAI) rationale.

2. **PDDL Structural Analysis**:
   - Fast recursive S-expression parser extracting object counts, predicates, actions, goal predicates, and detecting numeric fluents / action costs.

3. **Planners & Execution Profiles**:
   - **Optimal**: $A^*$ search with admissible heuristics.
   - **Satisficing**: Heuristic search with sub-optimal trade-offs (e.g. LAMA / Lazy Greedy).
   - **Agile**: Sub-second / tight-deadline greedy search.
   - Seamlessly executes native **Fast Downward** when present, falls back to embedded **Pyperplan**, or invokes adaptive mock synthesis.

4. **Plan Validation Engine**:
   - Validates generated action plans against formal PDDL domain physics.
   - Supports external `validate` (VAL) binary with automatic fallback to an internal, zero-dependency **pure-Python state-transition validator**.

5. **Autonomous Fallback Ladder**:
   - If a primary planner configuration fails (e.g., timeout, memory limit, or unachievable state), the platform automatically cascades through:
     $$\text{Optimal} \longrightarrow \text{Satisficing} \longrightarrow \text{Agile} \longrightarrow \text{Mock Recovery}$$
   - Telemetry tracks whether fallback was triggered and records full recovery history.

6. **SQLite Telemetry Engine**:
   - Automatically logs solver executions, plan length, metric footprints, validation status, and XAI verdicts to `backend/telemetry.db`.

7. **Modern React Dashboard**:
   - Side-by-side agent debate cards and anonymized peer critique matrix.
   - Interactive PDDL editor preloaded with canonical IPC benchmarks.
   - Step-by-step Plan Inspector with action sequencing and validation badges.
   - Telemetry Drawer displaying solver execution history and fallback rates.

---

## 🏛 Canonical IPC Benchmarks (`benchmarks/`)

The repository includes canonical benchmark domains from the International Planning Competition (IPC) in `benchmarks/`:

| Domain | Description | Simple Problem | Complex Problem |
| :--- | :--- | :--- | :--- |
| **`blocksworld`** | Classic combinatorial block stacking | `prob01_simple.pddl` (3-blocks Sussman Anomaly) | `prob02_complex.pddl` (6-blocks Stack) |
| **`gripper`** | Multi-gripper robot ball transport | `prob01_simple.pddl` (2 rooms, 2 balls) | `prob02_complex.pddl` (2 rooms, 6 balls) |
| **`logistics`** | Multi-agent logistics (trucks, airplanes, airports) | `prob01_simple.pddl` (1 city, 1 truck, 1 package) | `prob02_complex.pddl` (2 cities, airplanes, 2 packages) |

---

## ⚡ Quick-Start Guide

### Prerequisites
- **Python**: 3.10 or higher
- **uv**: Astral's Python package manager (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Node.js**: 18+ and `npm`

---

### Step 1: Install Dependencies

**Backend:**
```bash
uv sync
```

**Frontend:**
```bash
cd frontend
npm install
cd ..
```

---

### Step 2: (Optional) Configure OpenRouter API Key

Create a `.env` file in the root directory:
```bash
OPENROUTER_API_KEY=sk-or-v1-...
```

> **Note:** If `OPENROUTER_API_KEY` is not provided, the platform automatically switches to **offline mock council mode**, producing fully structured debates, JSON verdicts, and XAI justifications without external API calls.

---

### Step 3: Run the Application Locally

#### Option A: Run Servers Separately

**Terminal 1 — Backend (Port 8001):**
```bash
uv run python -m backend.main
```

**Terminal 2 — Frontend (Port 5173):**
```bash
cd frontend
npm run dev
```

#### Option B: Use the Startup Script

On Linux/macOS or Git Bash / WSL:
```bash
chmod +x start.sh
./start.sh
```

---

### Step 4: Access the Web Dashboard

Open your browser and navigate to:
```
http://localhost:5173
```

- Select a benchmark preset (e.g. **Blocksworld Sussman**, **Gripper**, **Logistics**).
- Click **Run Council Planning**.
- Watch the 3 agents debate in real-time, view the Judge's selection, and inspect the verified plan steps.
- Click **Telemetry** in the top navigation bar to review execution history.

---

## 🧪 Automated Testing & Verification

Run the comprehensive end-to-end verification suite across all benchmarks:

```bash
uv run python tests/test_portfolio.py
```

This verifies:
1. **Structural Analysis**: PDDL object, predicate, action, and goal extraction on all 6 benchmark files.
2. **Classical Execution & Validation**: Optimal, Satisficing, and Agile planner runs and state-transition validation.
3. **Council Deliberation & Judge Parsing**: 3-agent arguments, peer critique, and strict JSON verdict extraction.
4. **End-to-End API Pipeline & Fallback**: Fast recovery under unachievable goals and SQLite telemetry recording.

Other modular test suites:
```bash
uv run python tests/test_pddl_engine.py  # PDDL parser, planner wrapper & validator tests
uv run python tests/test_council.py      # Multi-agent council deliberation tests
uv run python tests/test_pipeline.py     # FastAPI solve-pddl route & fallback tests
```

---

## 📡 API Reference

### `POST /api/solve-pddl`
Submits a domain and problem PDDL pair to the council and execution pipeline.

**Request Body:**
```json
{
  "domain_pddl": "(define (domain ...))",
  "problem_pddl": "(define (problem ...))",
  "user_constraints": {
    "max_time": 30.0,
    "force_strategy": null,
    "models": {
      "optimal": "provider/model-id",
      "satisficing": "provider/model-id",
      "agile": "provider/model-id",
      "judge": "provider/model-id"
    }
  }
}
```

The optional `models` object assigns separate OpenRouter models to the
Optimal, Satisficing, Agile, and Judge council roles. Model IDs should be
selected from `GET /api/models`. If omitted, the backend uses the models
configured by environment variables.

**Response:**
```json
{
  "status": "success",
  "metrics": {
    "objects_count": 6,
    "predicates_count": 3,
    "actions_count": 3,
    "goals_count": 2
  },
  "debate": {
    "stage1": [...],
    "stage2": [...],
    "aggregate_rankings": [...],
    "judge_verdict": {
      "response": "...",
      "decision": {
        "strategy": "satisficing",
        "budget_seconds": 30.0,
        "search_configuration": "lazy_greedy([ff()])",
        "justification_summary": "Problem scale warrants fast heuristic search."
      }
    }
  },
  "execution": {
    "initial_strategy": "satisficing",
    "final_strategy": "satisficing",
    "fallback_triggered": false,
    "fallback_history": [],
    "plan": ["(pick ball1 rooma left)", "(move rooma roomb)", "(drop ball1 roomb left)"],
    "execution_time": 0.012,
    "planner_used": "pyperplan",
    "cost": 3.0,
    "error": null
  },
  "validation": {
    "valid": true,
    "cost": 3.0,
    "plan": ["(pick ball1 rooma left)", "(move rooma roomb)", "(drop ball1 roomb left)"],
    "execution_time": 0.012,
    "error": null
  },
  "xai_summary": "Problem scale warrants fast heuristic search.",
  "telemetry_id": 1
}
```

If `OPENROUTER_API_KEY` is configured, the council uses live models through
OpenRouter. If it is omitted, model requests use the platform's built-in
offline fallback responses.

### `GET /api/telemetry?limit=50`
Returns historical planning runs stored in SQLite (`backend/telemetry.db`).

### `GET /api/models`
Returns the current OpenRouter model catalog for searchable frontend role
selectors. The backend caches the catalog briefly and includes the configured
default model ID for each council role.

### `GET /api/pddl-status`
Returns planner and validator availability (Fast Downward, Pyperplan, VAL binary).

---

## 🛠 Tech Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn, httpx, Pyperplan, SQLite (`aiosqlite`)
- **Frontend**: React 19, Vite, Lucide Icons
- **Package Management**: `uv` (Python), `npm` (JavaScript)
- **Deliberation / LLM Layer**: OpenRouter API (Claude 3.5 Sonnet, GPT-4o, Gemini 1.5 Pro) with offline mock fallback
