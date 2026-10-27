"""Structured artifacts exchanged between agents (validated with Pydantic)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Requirements(BaseModel):
    summary: str
    acceptance_criteria: list[str]
    edge_cases: list[str] = Field(default_factory=list)


class Design(BaseModel):
    approach: str
    files_to_change: list[str]
    interfaces: list[str] = Field(default_factory=list)


class FileWrite(BaseModel):
    path: str = Field(description="Path relative to the repo root")
    content: str = Field(description="Full new file content")


class CodeChange(BaseModel):
    rationale: str
    files: list[FileWrite]


class TestReport(BaseModel):
    """Produced by actually running pytest, never by an LLM."""
    passed: int
    failed: int
    errors: int
    ok: bool
    output_tail: str = ""


class ReviewFinding(BaseModel):
    severity: Literal["low", "medium", "high"]
    category: Literal["correctness", "maintainability", "security"]
    file: str
    description: str


class ReviewReport(BaseModel):
    approved: bool
    findings: list[ReviewFinding] = Field(default_factory=list)


class RepoProfile(BaseModel):
    languages: dict[str, int]
    frameworks: list[str]
    has_tests: bool
    tree: list[str]
