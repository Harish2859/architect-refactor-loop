import os
import ast
from pathlib import Path
from typing import Dict, Any, TypedDict
from langgraph.graph import StateGraph, END

from core.parser import CodebaseMapmaker
from core.agents import analyst_agent, refactorer_agent, _invoke_with_retry
from sandbox.executor import run_tests, build_image

def _safe_path(base_dir: str, *parts: str) -> str:
    base = Path(base_dir).resolve()
    target = Path(os.path.join(base_dir, *parts)).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError(f"Path traversal detected: {target} escapes {base}")
    return str(target)

class CodebaseState(TypedDict):
    base_dir: str
    target_dir: str       # absolute path to the folder containing the target file and tests
    entry_file: str
    test_file: str        # filename of the pytest suite inside target_dir
    repo_structure: dict
    target_file: str
    target_function: str
    current_code: str
    analysis_report: str
    refactor_goal: str
    test_results: dict
    iteration_count: int
    completed_functions: list
    has_remaining_smells: bool
    total_passes: int

# ==========================================
# NODES
# ==========================================

def ingestion_node(state: CodebaseState) -> Dict[str, Any]:
    print("\n>> [Node: Ingestion] Building repository topology map...")
    target_dir = state["target_dir"]
    mapmaker = CodebaseMapmaker(base_dir=target_dir)
    repo_map = mapmaker.build_map(state["entry_file"])

    # target_file is the first .py file that isn't the test file
    target_file = state.get("target_file") or next(
        f for f in os.listdir(target_dir)
        if f.endswith(".py") and f != state["test_file"] and f != "__init__.py"
    )
    full_path = _safe_path(target_dir, target_file)
    with open(full_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    return {
        "repo_structure": repo_map,
        "target_file": target_file,
        "current_code": source_code,
        "iteration_count": 0,
        "completed_functions": [],
        "has_remaining_smells": True,
        "total_passes": 0
    }

def analyst_node(state: CodebaseState) -> Dict[str, Any]:
    print("\n>> [Node: Analyst] Scanning codebase map for code smells...")
    completed = state.get("completed_functions", [])
    response = _invoke_with_retry(analyst_agent, {
        "repo_map": state["repo_structure"],
        "source_code": state["current_code"],
        "completed_functions": completed if completed else "None"
    })
    print(f"   TARGET: {response.target_file} -> {response.target_function}")
    print(f"   ISSUE:  {response.issue_identified}")
    print(f"   MORE SMELLS REMAINING: {response.smells_remaining()}")
    return {
        "target_function": response.target_function,
        "analysis_report": response.issue_identified,
        "refactor_goal": response.refactor_goal,
        "has_remaining_smells": response.smells_remaining()
    }

def _validate_module_structure(code: str, original_code: str) -> str | None:
    """Returns an error message if the refactored code breaks module-level structure, else None."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError in refactored code: {e}"

    # Reject any class definitions — tests access module-level names directly
    classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    if classes:
        return (
            f"STRUCTURAL VIOLATION: Refactored code introduced class(es): {classes}. "
            "The test suite accesses _inventory and _orders as module-level variables directly "
            "(e.g. app._inventory.clear()). Wrapping them in a class breaks all tests. "
            "Keep _inventory and _orders as plain module-level dicts/lists and keep all "
            "functions as plain module-level functions."
        )

    # Ensure all original top-level function names are preserved
    orig_tree = ast.parse(original_code)
    orig_funcs = {n.name for n in ast.walk(orig_tree) if isinstance(n, ast.FunctionDef)}
    new_funcs  = {n.name for n in ast.walk(tree)      if isinstance(n, ast.FunctionDef)}
    missing = orig_funcs - new_funcs
    if missing:
        return (
            f"STRUCTURAL VIOLATION: Refactored code removed function(s): {missing}. "
            "All original function names must be preserved."
        )

    return None

def refactorer_node(state: CodebaseState) -> Dict[str, Any]:
    print(f"\n>> [Node: Refactorer] Optimizing '{state['target_function']}' (Iteration: {state['iteration_count'] + 1})...")
    failures = state.get("test_results", {}).get("output", "None") if state.get("test_results") else "None"

    response = _invoke_with_retry(refactorer_agent, {
        "target_file": state["target_file"],
        "target_function": state["target_function"],
        "refactor_goal": state["refactor_goal"],
        "current_code": state["current_code"],
        "test_failures": failures
    })

    original_code = state["current_code"]
    violation = _validate_module_structure(response.refactored_code, original_code)
    if violation:
        print(f"   [Validator] Structure violation detected — restoring original and retrying.")
        full_path = _safe_path(state["target_dir"], state["target_file"])
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(original_code)
            f.flush()
            os.fsync(f.fileno())
        return {
            "current_code": original_code,
            "iteration_count": state["iteration_count"] + 1,
            "test_results": {"exit_code": 1, "passed": 0, "failed": 1, "output": violation}
        }

    full_path = _safe_path(state["target_dir"], state["target_file"])
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(response.refactored_code)
        f.flush()
        os.fsync(f.fileno())

    return {
        "current_code": response.refactored_code,
        "iteration_count": state["iteration_count"] + 1
    }

def tester_node(state: CodebaseState) -> Dict[str, Any]:
    print("\n>> [Node: Tester] Offloading execution to isolated Docker sandbox...")
    results = run_tests(state["target_dir"], state["test_file"])
    print(f"   RESULTS: Passed={results.get('passed')} | Failed={results.get('failed')} | Exit Code={results.get('exit_code')}")
    return {"test_results": results}

def advance_node(state: CodebaseState) -> Dict[str, Any]:
    completed = list(set(state.get("completed_functions", []) + [state["target_function"]]))
    return {
        "completed_functions": completed,
        "iteration_count": 0,
        "total_passes": state.get("total_passes", 0) + 1,
    }

# ==========================================
# ROUTING
# ==========================================

MAX_PASSES = 6

def route_evaluation(state: CodebaseState) -> str:
    results = state["test_results"]
    if results.get("exit_code") != 0:
        if state["iteration_count"] >= 3:
            print("\n[HALT] Maximum healing iterations reached. Halting safely.")
            return END
        print("\n[RETRY] Tests failed. Routing back to Refactorer for automated healing.")
        return "refactorer"

    print(f"\n[PASS] '{state['target_function']}' clean.")

    completed = state.get("completed_functions", [])
    total_passes = state.get("total_passes", 0)
    duplicate = state["target_function"] in completed
    over_limit = total_passes >= MAX_PASSES

    if duplicate:
        print("[DONE] Analyst selected a duplicate target — codebase fully optimized.")
        return END
    if over_limit:
        print(f"[DONE] Reached {MAX_PASSES} pass limit. Halting.")
        return END
    if not state.get("has_remaining_smells"):
        print("[DONE] Analyst reports no remaining smells. Execution graph complete.")
        return END

    print("[CONTINUE] Routing to next target...")
    return "advance"

# ==========================================
# GRAPH COMPILATION
# ==========================================

workflow = StateGraph(CodebaseState)
workflow.add_node("ingestion", ingestion_node)
workflow.add_node("analyst", analyst_node)
workflow.add_node("refactorer", refactorer_node)
workflow.add_node("tester", tester_node)
workflow.add_node("advance", advance_node)

workflow.set_entry_point("ingestion")
workflow.add_edge("ingestion", "analyst")
workflow.add_edge("analyst", "refactorer")
workflow.add_edge("refactorer", "tester")
workflow.add_edge("advance", "analyst")
workflow.add_conditional_edges("tester", route_evaluation, {END: END, "refactorer": "refactorer", "advance": "advance"})

app = workflow.compile()
