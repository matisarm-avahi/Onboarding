"""Benchmark harness: runs the same tasks under three configurations and scores them with
HIDDEN acceptance tests (never shown to the agents), so correctness is independent of agent-written tests."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .agents import Budget
from .baseline import run_baseline
from .coordinator import Coordinator
from .llm import LLMClient

FIXTURES = Path(__file__).resolve().parent.parent / "benchmarks" / "fixtures"


@dataclass
class BenchTask:
    name: str
    prompt: str
    hidden_test: str
    repo: str | None = None


TASKS = [
    BenchTask(
        "slugify",
        "Create slugify.py with function slugify(text: str) -> str that lowercases text, replaces every run "
        "of non-alphanumeric characters with a single hyphen, and strips leading/trailing hyphens.",
        "from slugify import slugify\n"
        "def test_basic(): assert slugify('Hello, World!') == 'hello-world'\n"
        "def test_collapse(): assert slugify('a  --  b') == 'a-b'\n"
        "def test_strip(): assert slugify('  --x--  ') == 'x'\n"
        "def test_empty(): assert slugify('!!!') == ''\n"
        "def test_digits(): assert slugify('Python 3.12') == 'python-3-12'\n"),
    BenchTask(
        "lru_cache",
        "Create lru.py with class LRUCache(capacity: int) with get(key) returning -1 when missing and "
        "put(key, value) that evicts the least recently used entry when over capacity. Both get and put "
        "count as a use. Capacity <= 0 must raise ValueError.",
        "import pytest\nfrom lru import LRUCache\n"
        "def test_basic():\n    c=LRUCache(2); c.put(1,1); c.put(2,2); assert c.get(1)==1\n"
        "    c.put(3,3); assert c.get(2)==-1 and c.get(3)==3\n"
        "def test_update_counts_as_use():\n    c=LRUCache(2); c.put(1,1); c.put(2,2); c.put(1,10); c.put(3,3)\n"
        "    assert c.get(1)==10 and c.get(2)==-1\n"
        "def test_missing(): assert LRUCache(1).get('x')==-1\n"
        "def test_bad_capacity():\n    with pytest.raises(ValueError): LRUCache(0)\n"),
    BenchTask(
        "parse_duration",
        "Create durations.py with parse_duration(s: str) -> int returning total seconds for strings like "
        "'1h30m', '45s', '2d', '1d2h3m4s' (units d,h,m,s; any subset, in that order, no spaces). "
        "Raise ValueError for empty strings, unknown units, a number without a unit, or wrong order.",
        "import pytest\nfrom durations import parse_duration as p\n"
        "def test_ok(): assert p('1h30m')==5400 and p('45s')==45 and p('2d')==172800 and p('1d2h3m4s')==93784\n"
        "@pytest.mark.parametrize('bad',['','5','5x','30m1h','h','1h 30m'])\n"
        "def test_bad(bad):\n    with pytest.raises(ValueError): p(bad)\n"),
    BenchTask(
        "shop_coupon",
        "In the existing cart.py add apply_coupon(total: float, code: str) -> float. 'SAVE10' takes 10% "
        "off, 'SAVE20' takes 20% off; the result is rounded to 2 decimals. Unknown codes raise ValueError. "
        "Keep total() working and follow the repo's existing test style.",
        "import pytest\nfrom cart import apply_coupon, total\n"
        "def test_codes(): assert apply_coupon(100.0,'SAVE10')==90.0 and apply_coupon(19.99,'SAVE20')==15.99\n"
        "def test_unknown():\n    with pytest.raises(ValueError): apply_coupon(10,'NOPE')\n"
        "def test_total_intact(): assert total([('a',2.5,2),('b',1.0,1)])==6.0\n",
        repo=str(FIXTURES / "shop_repo")),
]

CONFIGS = ("baseline", "fixed", "routed")


def run_one(config: str, task: BenchTask, llm: LLMClient, max_revisions: int = 2,
            budget_kwargs: dict | None = None) -> dict:
    budget = Budget(**(budget_kwargs or {}))
    t0 = time.perf_counter()
    if config == "baseline":
        try:
            res = run_baseline(task.prompt, llm, task.repo, max_revisions, budget)
            steps, err = ["solo"], None
        except Exception as e:
            res, steps, err = None, ["solo"], f"{type(e).__name__}: {e}"
    else:
        res = Coordinator(llm, config, max_revisions, budget).run(task.prompt, task.repo)
        steps, err = res.steps, res.error
    wall = time.perf_counter() - t0
    if err and ("ExpiredToken" in err or "UnrecognizedClient" in err or "NoCredentials" in err):
        raise RuntimeError(f"AWS credentials problem, aborting benchmark (not a task failure): {err}")

    hidden_ok, hp, ht = False, 0, 0
    if res is not None and err is None:
        res.workspace.write_file("hidden_acceptance_test.py", task.hidden_test)
        rep = res.workspace.run_tests("hidden_acceptance_test.py", fail_fast=False)
        hp, ht = rep.passed, rep.passed + rep.failed + rep.errors
        hidden_ok = rep.ok
    review = getattr(res, "review", None)
    row = dict(task=task.name, config=config, hidden_pass=hidden_ok, hidden_passed=hp, hidden_total=ht,
               own_tests_pass=bool(res and res.report and res.report.ok),
               calls=budget.calls, input_tokens=budget.input_tokens, output_tokens=budget.output_tokens,
               cost_usd=round(budget.cost_usd, 4), wall_s=round(wall, 1),
               revisions=res.revisions if res else 0, steps="+".join(steps),
               review_findings=len(review.findings) if review else 0, failed=err is not None or not hidden_ok,
               error=err)
    if res is not None:
        res.workspace.cleanup()
    return row


def run_benchmark(llm: LLMClient, tasks=TASKS, configs=CONFIGS, **kw):
    """Returns a pandas DataFrame with one row per (task, config)."""
    import pandas as pd
    return pd.DataFrame([run_one(c, t, llm, **kw) for t in tasks for c in configs])


def summarize(df):
    g = df.groupby("config")
    return g.agg(pass_rate=("hidden_pass", "mean"),
                 hidden_test_pass=("hidden_passed", "sum"), hidden_test_total=("hidden_total", "sum"),
                 failure_rate=("failed", "mean"), avg_cost_usd=("cost_usd", "mean"),
                 avg_tokens=("input_tokens", lambda s: s.mean() + df.loc[s.index, "output_tokens"].mean()),
                 avg_wall_s=("wall_s", "mean"), avg_calls=("calls", "mean"),
                 avg_revisions=("revisions", "mean")).round(3).loc[list(CONFIGS)]
