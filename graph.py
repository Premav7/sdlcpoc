"""
graph.py

This is where the agent's flow is wired together using LangGraph.
Each function below is one NODE. `build_graph()` connects them with EDGES,
including the conditional edge that decides: PR vs retry vs escalate.
"""

from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama

import tools

MAX_RETRIES = 3


# ---- 1. Define the shared state that flows through every node ----
class AgentState(TypedDict):
    file_path: str          # the buggy file we're fixing
    ci_log: str
    git_diff: str
    proposed_fix: str
    test_passed: bool
    test_output: str
    attempts: int
    escalated: bool


# ---- 2. The LLM (local, free, via Ollama) ----
llm = ChatOllama(model="qwen2.5-coder:7b", temperature=0)


# ---- 3. Nodes ----

def investigate_node(state: AgentState) -> AgentState:
    """Pulls real evidence: the CI failure log + the commit diff."""
    state["ci_log"] = tools.read_ci_log()
    state["git_diff"] = tools.read_git_diff()
    return state

def clean_code_fences(text: str) -> str:
    """Strip markdown code fences if the model wraps its answer in them."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # remove opening ``` or ```python line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # remove closing ```
        text = "\n".join(lines)
    return text.strip()


def diagnose_node(state: AgentState) -> AgentState:
    """LLM reasons over the evidence and proposes a fixed version of the file."""
    current_code = tools.read_file(state["file_path"])

    prompt = f"""You are debugging a CI/CD pipeline failure.

FAILURE LOG:
{state['ci_log']}

LAST COMMIT DIFF:
{state['git_diff']}

CURRENT FILE CONTENTS ({state['file_path']}):
{current_code}

Identify the root cause and return ONLY the corrected full file contents.
Do not include explanations, markdown fences, or anything except the fixed code."""

    response = llm.invoke(prompt)
    state["proposed_fix"] = clean_code_fences(response.content)
    state["attempts"] += 1
    return state


def apply_fix_node(state: AgentState) -> AgentState:
    """Writes the LLM's proposed fix to the actual file."""
    tools.edit_file(state["file_path"], state["proposed_fix"])
    return state


def test_node(state: AgentState) -> AgentState:
    """Re-runs the test suite to verify the fix."""
    passed, output = tools.run_tests()
    state["test_passed"] = passed
    state["test_output"] = output
    return state


def pr_node(state: AgentState) -> AgentState:
    """On success: commit to a new branch and open a PR."""
    branch = "agent-fix-attempt"
    tools.git_commit_push(branch, "Agent: auto-fix for CI pipeline failure")
    tools.create_pr(
        title="Automated fix for CI failure",
        body=f"Root cause diagnosed from CI log + commit diff.\n\nAttempts taken: {state['attempts']}"
    )
    return state


def escalate_node(state: AgentState) -> AgentState:
    """Retries exhausted — flag for human review instead of looping forever."""
    state["escalated"] = True
    print(f"[ESCALATE] Could not fix after {state['attempts']} attempts. Needs human review.")
    print("Last test output:\n", state["test_output"])
    return state


# ---- 4. Conditional edge logic ----

def decide_next_step(state: AgentState) -> str:
    if state["test_passed"]:
        return "pr"
    if state["attempts"] >= MAX_RETRIES:
        return "escalate"
    return "retry"


# ---- 5. Build the graph ----

def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("investigate", investigate_node)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("apply_fix", apply_fix_node)
    graph.add_node("test", test_node)
    graph.add_node("pr", pr_node)
    graph.add_node("escalate", escalate_node)

    graph.set_entry_point("investigate")
    graph.add_edge("investigate", "diagnose")
    graph.add_edge("diagnose", "apply_fix")
    graph.add_edge("apply_fix", "test")

    graph.add_conditional_edges(
        "test",
        decide_next_step,
        {
            "pr": "pr",
            "retry": "diagnose",   # loop back to diagnosis with new context
            "escalate": "escalate",
        },
    )

    graph.add_edge("pr", END)
    graph.add_edge("escalate", END)

    return graph.compile()