import os
import re
import time
from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from groq import RateLimitError
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("GROQ_API_KEY"):
    raise ValueError("GROQ_API_KEY is not set in your environment or .env file.")

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.1)

# ==========================================
# 1. THE ANALYST
# ==========================================
class AnalysisOutput(BaseModel):
    target_file: str = Field(description="The exact relative path of the file containing the messy code (e.g., 'payment_processor.py')")
    target_function: str = Field(description="The specific function name that needs refactoring (e.g., 'process_payment')")
    issue_identified: str = Field(description="Explanation of the code smell found (e.g., 'High cyclomatic complexity, unhandled edge cases')")
    refactor_goal: str = Field(description="Clear architectural instructions for the Refactorer agent.")
    has_remaining_smells: str = Field(description="'true' if there are still other functions with code smells after this one. 'false' if the codebase is clean.")

    def smells_remaining(self) -> bool:
        return self.has_remaining_smells.strip().lower() == "true"

analyst_prompt = ChatPromptTemplate.from_messages([
    ("system", (
        "You are an expert System Architect analyzing a small codebase topology.\n\n"
        "Your input will be a structural repository JSON map, the actual source code, and a list of "
        "functions that have already been refactored in previous passes.\n"
        "Your task is to identify the SINGLE most problematic, unoptimized, or messy function that has NOT "
        "yet been refactored, and mark it for refactoring.\n\n"
        "Focus on: single-letter variables, hidden global mutations, poor time complexity, and unhandled exceptions.\n"
        "NEVER select `__init__`, dunder/magic methods, or private methods (names starting with `_`) as a target — only select public methods."

        "Set has_remaining_smells=True if there will still be other smelly functions after this one, False if the codebase will be clean."
    )),
    ("user", "Repository structure:\n{repo_map}\n\nSource code:\n{source_code}\n\nAlready refactored (do not select these):\n{completed_functions}")
])

def _invoke_with_retry(chain, inputs, max_retries=5):
    for attempt in range(max_retries):
        try:
            return chain.invoke(inputs)
        except RateLimitError as e:
            # Parse wait time from error message (e.g. "try again in 13m29.568s")
            wait = None
            try:
                msg = str(e)
                m = re.search(r"try again in (?:(\d+)m)?(?:([\d.]+)s)?", msg)
                if m:
                    minutes = int(m.group(1) or 0)
                    seconds = float(m.group(2) or 0)
                    wait = int(minutes * 60 + seconds) + 5  # +5s buffer
            except (AttributeError, ValueError) as parse_err:
                print(f"   [Rate Limit] Could not parse wait time: {parse_err}")
            if wait and wait > 300:
                print(f"   [Rate Limit] Daily token limit hit. Reset in ~{wait}s ({wait//60}m). Waiting...")
            elif wait:
                print(f"   [Rate Limit] Waiting {wait}s before retry {attempt + 1}/{max_retries}...")
            else:
                wait = min(30 * (2 ** attempt), 300)
                print(f"   [Rate Limit] Waiting {wait}s before retry {attempt + 1}/{max_retries}...")
            time.sleep(wait)
    raise RuntimeError("Exceeded max retries due to rate limiting.")

analyst_agent = analyst_prompt | llm.with_structured_output(AnalysisOutput)


# ==========================================
# 2. THE REFACTORER
# ==========================================
class RefactorOutput:
    def __init__(self, refactored_code: str):
        self.refactored_code = refactored_code

def _parse_refactor_response(message) -> RefactorOutput:
    text = message.content
    # Strip markdown code fences if present
    match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    code = match.group(1).strip() if match else text.strip()
    return RefactorOutput(refactored_code=code)

refactor_prompt = ChatPromptTemplate.from_messages([
    ("system", (
        "You are an elite Software Engineer specialized in clean code, robust error handling, and performance optimization.\n\n"
        "Your job is to rewrite the target function according to the Analyst's goal. You MUST respect the following boundaries:\n"
        "1. Maintain backwards compatibility: Do NOT alter function signatures or return types that break the existing test contract.\n"
        "2. Fix code smells: Use descriptive naming, eliminate silent failures, fix O(N) loops where O(1) maps apply, and remove global mutations.\n"
        "3. Preserve the rest of the file: Keep all other functions and imports in the file intact.\n\n"
        "Return ONLY the complete updated Python source code. Do not include any explanation or markdown fences.\n"
        "CRITICAL CONSTRAINTS — violating any of these will break the test suite:\n"
        "- Preserve the module's top-level structure exactly: keep all module-level variables (dicts, lists, etc.) "
        "as plain module-level variables. Do NOT wrap them in a class or object.\n"
        "- Keep all existing module-level function names and signatures identical. The tests import and call them directly.\n"
        "- Only improve the logic INSIDE the target function. Do not restructure the module.\n\n"
        "If you are reviewing feedback from a failed test execution loop, use the error trace logs to debug your implementation."
    )),
    ("user", (
        "Target File to Update: {target_file}\n"
        "Target Function to Fix: {target_function}\n"
        "Analyst's Objective: {refactor_goal}\n"
        "Current File Content:\n{current_code}\n\n"
        "Previous Test Failures (if any):\n{test_failures}"
    ))
])

refactorer_agent = refactor_prompt | llm | RunnableLambda(_parse_refactor_response)
