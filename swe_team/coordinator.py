"""Coordinator: plans, routes to specialists, runs independent work in parallel,
drives bounded revision loops from real test results and review findings, aggregates.

Modes: "routed" (router picks specialists), "fixed" (all five), "baseline" (one agent)."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal

from .agents import Budget, BudgetExceeded
from .llm import FAST_MODEL, SMART_MODEL, LLMClient
from .schemas import CodeChange, Design, Requirements, ReviewReport, TestReport
from .specialists import (
    STEPS,
    ArchitectAgent,
    CodeEngineerAgent,
    CodeReviewerAgent,
    Plan,
    RequirementsAgent,
    RouterAgent,
    SoloEngineer,
    TestEngineerAgent,
)
from .tools import Workspace

# Cost optimisation under routing: cheap model for analysis/review, strong model for code.
ROUTED_MODELS = {"router": FAST_MODEL, "requirements": FAST_MODEL, "architect": SMART_MODEL,
                 "engineer": SMART_MODEL, "tester": FAST_MODEL, "reviewer": FAST_MODEL}


@dataclass
class TeamResult:
    workspace: Workspace
    budget: Budget
    steps: list[str]
    report: TestReport | None = None
    plan: Plan | None = None
    requirements: Requirements | None = None
    design: Design | None = None
    review: ReviewReport | None = None
    revisions: int = 0
    error: str | None = None
    wall_s: float = 0.0


def _files_block(ws: Workspace, paths: list[str], limit: int = 6000) -> str:
    return "\n".join(f"--- {p}\n{ws.read_file(p, limit)}" for p in paths if ws.exists(p))


def _apply(ws: Workspace, change: CodeChange) -> list[str]:
    for f in change.files:
        ws.write_file(f.path, f.content)
    return [f.path for f in change.files]


class Coordinator:
    def __init__(self, llm: LLMClient, mode: Literal["routed", "fixed", "baseline"] = "routed",
                 max_revisions: int = 2, budget: Budget | None = None, on_event=None):
        self.llm, self.mode, self.max_revisions = llm, mode, max_revisions
        self.budget = budget or Budget()
        self.emit = on_event or (lambda msg: None)

    def _agent(self, cls):
        if self.mode == "baseline" and cls is CodeEngineerAgent:
            cls = SoloEngineer
        agent = cls(self.llm, self.budget)
        if self.mode == "routed":
            agent.model = ROUTED_MODELS[agent.name]
        return agent

    def plan(self, task: str, ws: Workspace) -> Plan:
        if self.mode == "baseline":
            return Plan(steps=["engineer"], complexity="simple", rationale="single-agent baseline")
        if self.mode == "fixed":
            return Plan(steps=list(STEPS), complexity="moderate", rationale="fixed pipeline")
        prof = ws.inspect()
        ctx = (f"Task: {task}\nRepository: {'existing' if prof.tree else 'empty (greenfield)'}; "
               f"languages={prof.languages} frameworks={prof.frameworks} has_tests={prof.has_tests} "
               f"files={len(prof.tree)}")
        p = self._agent(RouterAgent).run(ctx)
        steps = [s for s in STEPS if s in set(p.steps) | {"engineer"}]  # canonical order, engineer mandatory
        return p.model_copy(update={"steps": steps})

    def run(self, task: str, repo: str | None = None) -> TeamResult:
        t0, ws = time.perf_counter(), Workspace(repo)
        res = TeamResult(ws, self.budget, [])
        try:
            self._run(task, ws, res)
        except BudgetExceeded as e:
            res.error = f"budget exceeded: {e}"
        except Exception as e:  # a failed task is a data point, not a crash
            res.error = f"{type(e).__name__}: {e}"
        res.wall_s = time.perf_counter() - t0
        return res

    def _run(self, task: str, ws: Workspace, res: TeamResult):
        res.plan = plan = self.plan(task, ws)
        res.steps = ["solo"] if self.mode == "baseline" else list(plan.steps)
        self.emit(f"plan: {res.steps} ({plan.complexity}) - {plan.rationale}")
        profile = ws.inspect()
        base = f"Task: {task}\nRepo profile: {profile.model_dump_json()}"

        if "requirements" in plan.steps:
            res.requirements = self._agent(RequirementsAgent).run(base)
            self.emit("requirements done")
        reqs = f"\nRequirements: {res.requirements.model_dump_json()}" if res.requirements else ""

        if "architect" in plan.steps:
            res.design = self._agent(ArchitectAgent).run(base + reqs + "\n" + _files_block(ws, profile.tree[:8], 3000))
            self.emit("design done")
        design = f"\nDesign: {res.design.model_dump_json()}" if res.design else ""
        existing = _files_block(ws, res.design.files_to_change if res.design else profile.tree[:8], 6000)

        eng_ctx = f"{base}{reqs}{design}\nExisting files:\n{existing}"
        test_ctx = f"{base}{reqs}{design}\nWrite tests only."
        if "tester" in plan.steps and res.design:  # interfaces fixed by the design -> run in parallel
            with ThreadPoolExecutor(2) as pool:
                f_code = pool.submit(self._agent(CodeEngineerAgent).run, eng_ctx)
                f_test = pool.submit(self._agent(TestEngineerAgent).run, test_ctx)
                code, tests = f_code.result(), f_test.result()
            _apply(ws, code)
            _apply(ws, tests)
            self.emit("engineer + tester ran in parallel")
        else:
            code = self._agent(CodeEngineerAgent).run(eng_ctx)
            changed = _apply(ws, code)
            self.emit("engineer done")
            if "tester" in plan.steps:
                tests = self._agent(TestEngineerAgent).run(
                    test_ctx + "\nImplementation:\n" + _files_block(ws, changed))
                _apply(ws, tests)
                self.emit("tester done")
        changed = sorted(f.path for f in code.files)

        for it in range(self.max_revisions + 1):
            res.report = ws.run_tests()  # ground truth: actual pytest execution
            self.emit(f"iteration {it}: tests ok={res.report.ok} passed={res.report.passed} "
                      f"failed={res.report.failed}")
            res.review = None
            if "reviewer" in plan.steps and res.report.ok:
                res.review = self._agent(CodeReviewerAgent).run(
                    f"{base}{reqs}\nCode:\n{_files_block(ws, changed)}\nLint output: {ws.run_ruff() or 'clean'}")
                self.emit(f"review approved={res.review.approved} findings={len(res.review.findings)}")
            blocking = [f for f in (res.review.findings if res.review else []) if f.severity != "low"]
            if (res.report.ok and not blocking) or it == self.max_revisions:
                return
            res.revisions += 1
            feedback = "" if res.report.ok else f"\nFailing tests (real pytest output):\n{res.report.output_tail}"
            if blocking:
                feedback += "\nReview findings:\n" + "\n".join(
                    f"- [{f.severity}/{f.category}] {f.file}: {f.description}" for f in blocking)
            fix = self._agent(CodeEngineerAgent).run(
                f"{base}{reqs}{design}\nCurrent files:\n{_files_block(ws, ws.files())}{feedback}\n"
                "Fix exactly these issues.")
            changed = sorted(set(changed) | set(_apply(ws, fix)))
