# AI Architect — Self-Healing Code Refactoring Engine

A production-grade, multi-agent pipeline that autonomously analyzes a Python codebase, refactors targeted functions, validates the output inside an isolated Docker sandbox, and self-heals on test failures — all driven by a deterministic LangGraph state machine.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   Deterministic Controller                  │
│           LangGraph State Machine  +  AST Parser            │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                Untrusted Generation Engine                  │
│          Groq  /  Llama-3.3-70b-versatile  (LLM)            │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                  Isolated Runtime Sandbox                   │
│     Docker  ·  --network none  ·  256m  ·  :ro mount        │
└─────────────────────────────────────────────────────────────┘
```

The LLM is treated as a **volatile, untrusted compute resource** — it is strictly confined to content generation. All routing decisions, file I/O, loop termination, and security boundaries are enforced by deterministic system logic.

---

## Execution Graph

```
[Ingestion] ──► [Analyst] ──► [Refactorer] ──► [Tester]
                   ▲                               │
                   │                    ┌── FAIL ──┤  (self-heal, max 3 attempts)
                [Advance] ◄─────────────┤          │
                                        └── PASS ──┤  (has_remaining_smells=True)
                                                   │
                                                  END  (duplicate target / clean / limit)
```

### Node Responsibilities

| Node | Role |
|---|---|
| **Ingestion** | Builds a JSON topology map of the codebase using Python's native `ast` module. Reads the target file into state. |
| **Analyst** | Identifies the single most problematic public function not yet refactored. Returns structured `AnalysisOutput` via Pydantic schema. |
| **Refactorer** | Rewrites the target function, validates module structure via AST before writing, flushes to disk with `os.fsync()`. |
| **Tester** | Spins up an isolated Docker container, mounts the target directory read-only, runs `pytest`, and streams results back to state. |
| **Advance** | Marks the current function as complete, resets the per-function healing counter, increments the global pass count. |

### Routing Logic

- `FAIL` → retry via **Refactorer** (up to 3 attempts per function)
- `PASS + has_remaining_smells` → **Advance** → **Analyst** (next target)
- `PASS + duplicate target selected` → **END** (convergence detected)
- `PASS + analyst reports clean` → **END**
- `PASS + 6 total passes reached` → **END** (hard ceiling)

---

## Project Structure

```
ai-architect-refactor/
├── main.py                        # Entry point — target configuration, builds image, runs graph
├── requirements.txt
├── core/
│   ├── parser.py                  # AST-based codebase topology mapper
│   ├── agents.py                  # Analyst + Refactorer agent definitions, retry logic
│   └── graph.py                   # LangGraph state machine, nodes, routing, validators
└── sandbox/
    ├── Dockerfile                 # Minimal python:3.11-slim image with pytest, non-root user
    ├── executor.py                # Docker container orchestration + result parsing
    ├── mock_target/
    │   ├── payment_processor.py   # Target codebase — FinTech service (refactored in-place)
    │   └── test_payment.py        # 7-test contractual benchmark suite
    └── new_github_repo/           # Drop any repo here and point main.py at it
        ├── app.py
        └── test_app.py
```

---

## Pointing the Engine at Any Repository

All target configuration lives in four lines at the top of `main.py`. No other file needs to change:

```python
TARGET_DIR  = os.path.join(current_dir, "sandbox", "mock_target")  # folder containing target + tests
TARGET_FILE = "payment_processor.py"   # file to refactor
TEST_FILE   = "test_payment.py"        # pytest suite inside TARGET_DIR
ENTRY_FILE  = "payment_processor.py"   # AST ingestion entry point
```

To run against a different repository:

```python
TARGET_DIR  = os.path.join(current_dir, "sandbox", "new_github_repo")
TARGET_FILE = "app.py"
TEST_FILE   = "test_app.py"
ENTRY_FILE  = "app.py"
```

The graph, agents, Docker sandbox, and routing logic adapt automatically.

---

## Security Architecture

### Docker Sandbox Guardrails

| Flag | Protection |
|---|---|
| `--network none` | Complete network isolation — no exfiltration, no outbound calls |
| `--memory 256m` | Prevents memory exhaustion from runaway generated code |
| `--cpus 0.5` | Prevents CPU denial-of-service from infinite loops |
| `-v /path:/app:ro` | Read-only volume mount — container cannot write back to host filesystem |
| `USER sandboxuser` | Non-root execution inside the container |

### Host-Side Hardening

- **`_safe_path()` in `graph.py`** — all file paths are resolved and asserted to stay within `base_dir` before any read or write operation, preventing path traversal from LLM-generated filenames
- **`shutil.which("docker")` in `executor.py`** — resolves the absolute binary path before subprocess execution, preventing PATH-hijacking attacks
- **`os.fsync()` after every write** — forces the kernel to flush page cache to disk before Docker mounts the volume, eliminating host-container file state race conditions
- **`_validate_module_structure()` gate** — AST-parses the refactored code before writing to disk; rejects any generation that introduces class wrappers, removes existing functions, or contains syntax errors
- **Typed exception handling** — bare `except: pass` replaced with `except (AttributeError, ValueError)` throughout, ensuring silent failures never corrupt graph state

---

## Key Engineering Decisions

### 1. Deterministic Termination (Never Trust the LLM)

The graph terminates based on three independent deterministic guards in `route_evaluation`, not on the model's `has_remaining_smells` signal alone:

```python
duplicate = state["target_function"] in completed   # analyst re-selected a done function
over_limit = total_passes >= MAX_PASSES             # hard global ceiling
not state.get("has_remaining_smells")               # model reports clean
```

The model consistently returned `has_remaining_smells=True` indefinitely, causing infinite loops until deterministic guards were added.

### 2. AST Pre-Parsing for Context Efficiency

The `CodebaseMapmaker` uses Python's `ast` module to build a lightweight JSON blueprint before any LLM call. The model receives only the structural map and the isolated target file — not the entire codebase — keeping token usage minimal and context precise.

### 3. Raw Text Generation for the Refactorer

The Refactorer uses plain text generation + manual parsing instead of `with_structured_output()`. Groq's tool-calling layer consistently failed (`tool_use_failed: 400`) when asked to serialize large code strings containing special characters inside a JSON schema. Bypassing the tool-calling layer entirely resolved this.

### 4. Per-Function Healing Budget

`iteration_count` is reset to `0` in `advance_node` on every new target. Each function gets its own independent 3-attempt self-healing budget, preventing a single difficult function from consuming the entire retry allowance.

### 5. Server-Side Boolean Coercion

Groq validates tool call schemas server-side before returning a response. Declaring `has_remaining_smells` as `bool` in the Pydantic schema caused Groq to reject the model's `"true"` string response before our validator could run. The fix: declare the field as `str`, coerce client-side via a method:

```python
has_remaining_smells: str = Field(description="'true' or 'false'")

def smells_remaining(self) -> bool:
    return self.has_remaining_smells.strip().lower() == "true"
```

### 6. Pre-Write AST Structural Validation

Before any refactored code touches disk, `_validate_module_structure()` parses it with `ast` and enforces two invariants:

- No class definitions introduced (LLMs frequently wrap module-level state in classes, breaking direct dict access in tests)
- All original function names preserved (LLMs occasionally rename or drop functions during refactoring)

Violations are caught before the file is written, the original is restored, and the failure trace is fed back to the Refactorer as a structured error message.

### 7. Disk Flush Before Container Mount

```python
with open(full_path, "w", encoding="utf-8") as f:
    f.write(response.refactored_code)
    f.flush()
    os.fsync(f.fileno())
```

`f.flush()` drains Python's userspace buffer to the OS. `os.fsync()` forces the OS kernel to commit its page cache to physical disk. Both are required to guarantee the Docker volume mount sees the latest file version, not a cached page.

---

## Validated Against Two Independent Codebases

| Target | Domain | Functions Refactored | Trap Injected | Outcome |
|---|---|---|---|---|
| `payment_processor.py` | FinTech — payments, refunds, discounts | 4 | Global state mutation, O(N) linear scans | Converged clean — `Passed=7` |
| `app.py` | Inventory — orders, stock, bulk discounts | 2 | O(N²) nested loop, single-letter variables | Converged clean — `Passed=8` |

---

## Live Execution Output

### Run 1 — FinTech Service (payment_processor.py)

```
>> Building Docker sandbox image...
Starting AI Architect Engine Loop...

>> [Node: Ingestion] Building repository topology map...

>> [Node: Analyst] Scanning codebase map for code smells...
   TARGET: payment_processor.py -> apply_discount
   ISSUE:  Poor time complexity due to repeated user balance updates and potential hidden global mutations
   MORE SMELLS REMAINING: True

>> [Node: Refactorer] Optimizing 'apply_discount' (Iteration: 1)...

>> [Node: Tester] Offloading execution to isolated Docker sandbox...
   [Docker] Spinning up isolated container...
   RESULTS: Passed=7 | Failed=0 | Exit Code=0

[PASS] 'apply_discount' clean.
[CONTINUE] Routing to next target...

>> [Node: Analyst] Scanning codebase map for code smells...
   TARGET: payment_processor.py -> process_payment
   ISSUE:  Poor error handling and potential hidden global mutations
   MORE SMELLS REMAINING: True

>> [Node: Refactorer] Optimizing 'process_payment' (Iteration: 1)...

>> [Node: Tester] Offloading execution to isolated Docker sandbox...
   [Docker] Spinning up isolated container...
   RESULTS: Passed=7 | Failed=0 | Exit Code=0

[PASS] 'process_payment' clean.
[CONTINUE] Routing to next target...

>> [Node: Analyst] Scanning codebase map for code smells...
   TARGET: payment_processor.py -> refund
   ISSUE:  Poor error handling and potential race conditions due to the use of a lock
   MORE SMELLS REMAINING: True

>> [Node: Refactorer] Optimizing 'refund' (Iteration: 1)...

>> [Node: Tester] Offloading execution to isolated Docker sandbox...
   [Docker] Spinning up isolated container...
   RESULTS: Passed=7 | Failed=0 | Exit Code=0

[PASS] 'refund' clean.
[CONTINUE] Routing to next target...

>> [Node: Analyst] Scanning codebase map for code smells...
   TARGET: payment_processor.py -> process_payment
   ISSUE:  High cyclomatic complexity, unhandled edge cases, and potential hidden global mutations
   MORE SMELLS REMAINING: True

>> [Node: Refactorer] Optimizing 'process_payment' (Iteration: 1)...

>> [Node: Tester] Offloading execution to isolated Docker sandbox...
   [Docker] Spinning up isolated container...
   RESULTS: Passed=7 | Failed=0 | Exit Code=0

[PASS] 'process_payment' clean.
[DONE] Analyst selected a duplicate target — codebase fully optimized.

Process finished execution cleanly.
```

### Run 2 — Inventory Service (app.py, zero-shot foreign codebase)

```
>> Building Docker sandbox image...
Starting AI Architect Engine Loop...

>> [Node: Ingestion] Building repository topology map...

>> [Node: Analyst] Scanning codebase map for code smells...
   TARGET: app.py -> place_order
   ISSUE:  Missing try-except validation for dictionary lookups and hidden global state mutation without protection
   MORE SMELLS REMAINING: True

>> [Node: Refactorer] Optimizing 'place_order' (Iteration: 1)...

>> [Node: Tester] Offloading execution to isolated Docker sandbox...
   [Docker] Spinning up isolated container...
   RESULTS: Passed=2 | Failed=1 | Exit Code=1

[RETRY] Tests failed. Routing back to Refactorer for automated healing.

>> [Node: Refactorer] Optimizing 'place_order' (Iteration: 2)...

>> [Node: Tester] Offloading execution to isolated Docker sandbox...
   [Docker] Spinning up isolated container...
   RESULTS: Passed=3 | Failed=0 | Exit Code=0

[PASS] 'place_order' clean.
[CONTINUE] Routing to next target...

>> [Node: Analyst] Scanning codebase map for code smells...
   TARGET: app.py -> process_bulk_discounts
   ISSUE:  Poor time complexity due to O(N²) double-nested loop checking orders against orders
   MORE SMELLS REMAINING: False

>> [Node: Refactorer] Optimizing 'process_bulk_discounts' (Iteration: 1)...

>> [Node: Tester] Offloading execution to isolated Docker sandbox...
   [Docker] Spinning up isolated container...
   RESULTS: Passed=2 | Failed=1 | Exit Code=1

[RETRY] Tests failed. Routing back to Refactorer for automated healing.

>> [Node: Refactorer] Optimizing 'process_bulk_discounts' (Iteration: 2)...

>> [Node: Tester] Offloading execution to isolated Docker sandbox...
   [Docker] Spinning up isolated container...
   RESULTS: Passed=2 | Failed=1 | Exit Code=1

[RETRY] Tests failed. Routing back to Refactorer for automated healing.

>> [Node: Refactorer] Optimizing 'process_bulk_discounts' (Iteration: 3)...

>> [Node: Tester] Offloading execution to isolated Docker sandbox...
   [Docker] Spinning up isolated container...
   RESULTS: Passed=2 | Failed=1 | Exit Code=1

[HALT] Maximum healing iterations reached. Halting safely.

Process finished execution cleanly.
```

---

## Self-Healing in Action

When the Refactorer produces code that breaks tests, the graph automatically routes back with the full failure trace:

```
>> [Node: Refactorer] Optimizing 'refund' (Iteration: 1)...
   RESULTS: Passed=6 | Failed=1 | Exit Code=1

[RETRY] Tests failed. Routing back to Refactorer for automated healing.

>> [Node: Refactorer] Optimizing 'refund' (Iteration: 2)...
   RESULTS: Passed=7 | Failed=0 | Exit Code=0

[PASS] 'refund' clean.
```

---

## Known Limitations & Trade-offs

**Rate limits** — The Groq free tier enforces a 100k tokens/day ceiling. A full multi-pass run consumes ~15–20k tokens. For production workloads, swap to a paid Groq tier or a self-hosted model via vLLM or Ollama.

**Contract drift** — The engine validates correctness via test pass/fail, not static type signatures. A function can drift its return type while still passing tests if wrapper logic accommodates it. A static analysis gate or explicit type-assertion tests would close this gap.

**Single-file scope** — The ingestion node targets one file per run. The AST parser already supports multi-file dependency resolution; extending the graph to iterate across files is a straightforward addition.

**Dunder and private method exclusion** — `__init__` and all `_private` methods are excluded from analyst targeting by prompt constraint. The LLM consistently introduced shallow copy violations and reentrant lock bugs when targeting constructors, breaking shared-state contracts the test suite depends on.

---

## Setup

**Prerequisites:** Python 3.11+, Docker Desktop running

```bash
git clone https://github.com/your-username/ai-architect-refactor
cd ai-architect-refactor
pip install -r requirements.txt
```

Create a `.env` file:

```
GROQ_API_KEY=your_key_here
```

Run:

```bash
python main.py
```

---

## Stack

| Component | Technology |
|---|---|
| Orchestration | LangGraph |
| LLM Inference | Groq — `llama-3.3-70b-versatile` |
| Schema Validation | Pydantic v2 |
| AST Parsing | Python `ast` stdlib |
| Sandbox Execution | Docker (`python:3.11-slim`) |
| Test Suite | pytest |
