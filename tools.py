"""
tools.py

These are the actual "hands" of the agent. Each function wraps a real
command (git, gh CLI, file I/O, pytest) and returns plain text/booleans
that the LLM or the graph logic can use.

Nothing here calls the LLM. The LLM only ever sees the *output* of these
functions as text (inside the Diagnose node in graph.py).
"""

import subprocess
import os


def read_ci_log(run_id: str | None = None) -> str:
    """
    Fetch the log of the most recent failed GitHub Actions run
    (or a specific run_id if given).
    Requires: `gh auth login` already done.
    """
    if run_id is None:
        # Get the most recent failed run's ID
        result = subprocess.run(
            ["gh", "run", "list", "--status", "failure", "--limit", "1", "--json", "databaseId"],
            capture_output=True, text=True
        )
        import json
        runs = json.loads(result.stdout or "[]")
        if not runs:
            return "No failed runs found."
        run_id = str(runs[0]["databaseId"])

    log = subprocess.run(
        ["gh", "run", "view", run_id, "--log-failed"],
        capture_output=True, text=True
    )
    return log.stdout or log.stderr


def read_git_diff() -> str:
    """
    Fetch the diff of the last commit — the most likely cause of the failure.
    """
    result = subprocess.run(
        ["git", "log", "-p", "-1"],
        capture_output=True, text=True
    )
    return result.stdout


def read_file(file_path: str) -> str:
    """Read the current contents of a source file."""
    with open(file_path, "r") as f:
        return f.read()


def edit_file(file_path: str, new_content: str) -> str:
    """
    Overwrite the file with the LLM's proposed fix.
    (For a real product you'd apply a diff/patch instead of a full overwrite —
    full overwrite is simpler and fine for a small demo file.)
    """
    with open(file_path, "w") as f:
        f.write(new_content)
    return f"Updated {file_path}"


def run_tests(test_command: str = "pytest -q") -> tuple[bool, str]:
    """
    Run the test suite. Returns (passed: bool, output: str).
    """
    result = subprocess.run(
        test_command.split(),
        capture_output=True, text=True
    )
    passed = result.returncode == 0
    output = result.stdout + result.stderr
    return passed, output


def git_commit_push(branch_name: str, commit_message: str) -> str:
    """
    Create a new branch, commit the current changes, and push it.
    """
    subprocess.run(["git", "checkout", "-b", branch_name], capture_output=True, text=True)
    subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", commit_message], capture_output=True, text=True)
    push = subprocess.run(["git", "push", "-u", "origin", branch_name], capture_output=True, text=True)
    return push.stdout + push.stderr


def create_pr(title: str, body: str) -> str:
    """
    Open a pull request from the current branch using GitHub CLI.
    """
    result = subprocess.run(
        ["gh", "pr", "create", "--title", title, "--body", body],
        capture_output=True, text=True
    )
    return result.stdout or result.stderr