import json

from swe_team.coordinator import Coordinator
from swe_team.evaluate import TASKS, run_one
from swe_team.llm import FakeClient

PLAN = {"steps": ["reviewer", "tester", "engineer"], "complexity": "simple", "rationale": "small"}
BUG = {"rationale": "v1", "files": [{"path": "calc.py", "content": "def add(a, b):\n    return a - b\n"}]}
TESTS = {"rationale": "t", "files": [{"path": "test_calc.py",
         "content": "from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"}]}
FIX = {"rationale": "fix", "files": [{"path": "calc.py", "content": "def add(a, b):\n    return a + b\n"}]}
REVIEW = {"approved": True, "findings": []}


def test_routed_runs_only_planned_agents_and_revises_on_real_failure():
    llm = FakeClient([json.dumps(x) for x in (PLAN, BUG, TESTS, FIX, REVIEW)])
    res = Coordinator(llm, "routed").run("add numbers")
    assert res.error is None and res.report.ok and res.revisions == 1
    assert res.steps == ["engineer", "tester", "reviewer"]  # canonical order, no requirements/architect
    assert res.review.approved and res.budget.calls == 5
    res.workspace.cleanup()


def test_benchmark_scores_with_hidden_tests():
    slug = {"rationale": "x", "files": [{"path": "slugify.py", "content":
            "import re\n\ndef slugify(text):\n    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')\n"}]}
    llm = FakeClient([json.dumps(slug)] * 3)
    row = run_one("baseline", TASKS[0], llm)
    assert row["hidden_pass"] and row["hidden_total"] == 5 and row["calls"] == 3 and row["revisions"] == 2  # no own tests -> not ok -> revises
