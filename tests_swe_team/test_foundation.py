import json

import pytest

from swe_team.agents import Budget
from swe_team.coordinator import Coordinator
from swe_team.llm import FakeClient
from swe_team.tools import Workspace

BAD = {"rationale": "v1", "files": [
    {"path": "calc.py", "content": "def add(a, b):\n    return a - b\n"},
    {"path": "test_calc.py", "content": "from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"}]}
GOOD = {"rationale": "fix", "files": [
    {"path": "calc.py", "content": "def add(a, b):\n    return a + b\n"}]}


def test_baseline_revises_until_real_tests_pass():
    llm = FakeClient(["not json at all", json.dumps(BAD), json.dumps(GOOD)])
    res = Coordinator(llm, "baseline").run("add numbers")  # greenfield; first reply invalid -> schema retry
    assert res.report.ok and res.revisions == 1 and res.budget.calls == 3
    res.workspace.cleanup()


def test_budget_limit_enforced():
    llm = FakeClient([json.dumps(BAD)] * 5)
    res = Coordinator(llm, "baseline", budget=Budget(max_calls=1)).run("add numbers")
    assert res.error.startswith("budget exceeded")


def test_workspace_blocks_escape_and_preserves_original(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    ws = Workspace(tmp_path)
    with pytest.raises(ValueError):
        ws.write_file("../evil.py", "")
    ws.write_file("a.py", "x = 2\n")
    assert (tmp_path / "a.py").read_text() == "x = 1\n"
    assert ws.inspect().languages == {"python": 1}
    ws.cleanup()
