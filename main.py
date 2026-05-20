import os
from core.graph import app
from sandbox.executor import build_image

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # ── Target Configuration ──────────────────────────────────────────
    # To run against a different repo, update these three values only.
    TARGET_DIR  = os.path.join(current_dir, "sandbox", "test_ecommerce_repo")
    TARGET_FILE = "app.py"                 # file to refactor
    TEST_FILE   = "test_app.py"            # pytest suite inside TARGET_DIR
    ENTRY_FILE  = "app.py"                 # AST ingestion entry point
    # ─────────────────────────────────────────────────────────────────

    print(">> Building Docker sandbox image...")
    build_image()

    initial_state = {
        "base_dir": current_dir,
        "target_dir": TARGET_DIR,
        "entry_file": ENTRY_FILE,
        "test_file": TEST_FILE,
        "repo_structure": {},
        "target_file": TARGET_FILE,
        "target_function": "",
        "current_code": "",
        "analysis_report": "",
        "refactor_goal": "",
        "test_results": {},
        "iteration_count": 0,
        "completed_functions": [],
        "has_remaining_smells": True,
        "total_passes": 0
    }

    print("Starting AI Architect Engine Loop...")
    final_output = app.invoke(initial_state)
    print("\nProcess finished execution cleanly.")
