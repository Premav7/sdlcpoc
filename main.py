"""
main.py

Run this after you've pushed a broken commit and confirmed the CI pipeline
has actually failed on GitHub Actions.

Usage:
    python main.py path/to/buggy_file.py
"""

import sys
from graph import build_graph, AgentState


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <path_to_buggy_file>")
        sys.exit(1)

    file_path = sys.argv[1]

    initial_state: AgentState = {
        "file_path": file_path,
        "ci_log": "",
        "git_diff": "",
        "proposed_fix": "",
        "test_passed": False,
        "test_output": "",
        "attempts": 0,
        "escalated": False,
    }

    app = build_graph()
    final_state = app.invoke(initial_state)

    if final_state["test_passed"]:
        print(f"\n✅ Fix succeeded after {final_state['attempts']} attempt(s). PR opened.")
    elif final_state["escalated"]:
        print(f"\n⚠️ Could not fix after {final_state['attempts']} attempt(s). Escalated for human review.")


if __name__ == "__main__":
    main()