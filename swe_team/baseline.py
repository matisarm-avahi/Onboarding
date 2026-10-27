"""Milestone 1: single-agent baseline. One agent, same tools, bounded fix loop driven by real test results."""
from __future__ import annotations

from dataclasses import dataclass

from .agents import Agent, Budget
from .llm import LLMClient
from .schemas import CodeChange, TestReport
from .tools import Workspace


class SoloEngineer(Agent):
    name = "solo"
    output_model = CodeChange
    instructions = ("You are a software engineer. Implement the task, including pytest tests. "
                    "Return complete contents of every file you create or change.")


@dataclass
class RunResult:
    workspace: Workspace
    report: TestReport | None
    budget: Budget
    revisions: int


def _repo_context(ws: Workspace, max_files: int = 12) -> str:
    profile = ws.inspect()
    parts = [f"Repo profile: {profile.model_dump_json()}"]
    for f in profile.tree[:max_files]:
        if f.endswith((".py", ".txt", ".toml", ".md")):
            parts.append(f"--- {f}\n{ws.read_file(f, 4000)}")
    return "\n".join(parts)


def run_baseline(task: str, llm: LLMClient, repo: str | None = None,
                 max_revisions: int = 2, budget: Budget | None = None) -> RunResult:
    budget, ws = budget or Budget(), Workspace(repo)
    agent = SoloEngineer(llm, budget)
    context = f"Task: {task}\n\n{_repo_context(ws)}"
    report, revisions = None, 0
    for attempt in range(max_revisions + 1):
        change = agent.run(context)
        for f in change.files:
            ws.write_file(f.path, f.content)
        report = ws.run_tests()  # ground truth, not an LLM claim
        if report.ok or attempt == max_revisions:
            break
        revisions += 1
        context = (f"Task: {task}\n\n{_repo_context(ws)}\n\nTests failed:\n{report.output_tail}\n"
                   "Fix the code and return the updated files.")
    return RunResult(ws, report, budget, revisions)
