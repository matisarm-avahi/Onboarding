"""Specialist agents: same interface, different instructions, inputs and typed outputs."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .agents import Agent
from .schemas import CodeChange, Design, Requirements, ReviewReport

STEPS = ("requirements", "architect", "engineer", "tester", "reviewer")


class Plan(BaseModel):
    steps: list[Literal["requirements", "architect", "engineer", "tester", "reviewer"]]
    complexity: Literal["trivial", "simple", "moderate", "complex"]
    rationale: str = Field(description="One or two sentences")


class RouterAgent(Agent):
    name = "router"
    output_model = Plan
    instructions = (
        "You are the coordinator of a software team. Choose the minimal set of specialists needed "
        "for the task. Available: requirements (acceptance criteria/edge cases; use when the task is "
        "ambiguous or has many rules), architect (design; use for multi-file or existing-repo changes), "
        "engineer (always required), tester (writes pytest tests; use whenever behaviour must be verified), "
        "reviewer (correctness/security review; use for complex or security-sensitive work). "
        "Skip specialists a small, clear task does not need.")


class RequirementsAgent(Agent):
    name = "requirements"
    output_model = Requirements
    instructions = ("You are a requirements analyst. Turn the task into a short summary, concrete, "
                    "testable acceptance criteria, and edge cases. Do not write code.")


class ArchitectAgent(Agent):
    name = "architect"
    output_model = Design
    instructions = ("You are a software architect. Given the task, requirements and repository profile, "
                    "choose an approach, list the files to create/change (repo-relative paths) and the exact "
                    "public interfaces (function/class signatures). Follow existing repo conventions. No code bodies.")


class CodeEngineerAgent(Agent):
    name = "engineer"
    output_model = CodeChange
    instructions = ("You are a code engineer. Implement the design/requirements. Return the COMPLETE "
                    "content of every file you create or modify. Do not write tests unless asked; when "
                    "given feedback (failing tests, review findings), fix exactly those issues.")


class TestEngineerAgent(Agent):
    name = "tester"
    output_model = CodeChange
    instructions = ("You are a test engineer. Write pytest tests (files named test_*.py) covering every "
                    "acceptance criterion and edge case, using only the specified interfaces. Do not "
                    "write implementation files.")


class CodeReviewerAgent(Agent):
    name = "reviewer"
    output_model = ReviewReport
    instructions = ("You are a strict code reviewer. Check correctness against the requirements, "
                    "maintainability and security. Report only real defects, each with severity. "
                    "approved=true only if there are no high or medium findings.")
