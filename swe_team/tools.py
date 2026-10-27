"""Controlled tools. All work happens in a temp copy; the original repo is never touched."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from .schemas import RepoProfile, TestReport

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", ".ruff_cache"}
LANG_BY_EXT = {".py": "python", ".js": "javascript", ".ts": "typescript",
               ".java": "java", ".go": "go", ".rs": "rust"}
FRAMEWORKS = ("fastapi", "flask", "django", "pytest", "pydantic")


class Workspace:
    def __init__(self, source: str | Path | None = None):
        """source=None -> greenfield (empty workspace)."""
        self.root = Path(tempfile.mkdtemp(prefix="swe_team_"))
        if source:
            shutil.copytree(source, self.root, ignore=shutil.ignore_patterns(*SKIP_DIRS), dirs_exist_ok=True)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _safe(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if not p.is_relative_to(self.root.resolve()):
            raise ValueError(f"path escapes workspace: {rel}")
        return p

    def exists(self, rel: str) -> bool:
        return self._safe(rel).is_file()

    def files(self) -> list[str]:
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*")
                      if p.is_file() and not SKIP_DIRS & set(p.parts))

    def read_file(self, rel: str, max_chars: int = 20_000) -> str:
        return self._safe(rel).read_text(encoding="utf-8", errors="replace")[:max_chars]

    def write_file(self, rel: str, content: str):
        p = self._safe(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def search(self, pattern: str, max_hits: int = 50) -> list[str]:
        rx = re.compile(pattern)
        hits = (f"{rel}:{i}: {line.strip()}" for rel in self.files()
                for i, line in enumerate(self.read_file(rel).splitlines(), 1) if rx.search(line))
        return [h for _, h in zip(range(max_hits), hits)]

    def inspect(self) -> RepoProfile:
        files = self.files()
        langs = Counter(LANG_BY_EXT[Path(f).suffix] for f in files if Path(f).suffix in LANG_BY_EXT)
        deps = " ".join(self.read_file(f).lower() for f in files
                        if Path(f).name in ("requirements.txt", "pyproject.toml", "setup.py"))
        return RepoProfile(languages=dict(langs), frameworks=[f for f in FRAMEWORKS if f in deps],
                           has_tests=any(Path(f).name.startswith("test_") or f.startswith("tests/")
                                         for f in files),
                           tree=files[:200])

    def _run(self, args: list[str], timeout: int) -> tuple[int, str]:
        try:
            r = subprocess.run([sys.executable, "-m", *args], cwd=self.root, capture_output=True,
                               text=True, timeout=timeout)
            return r.returncode, r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            return 124, f"timed out after {timeout}s"

    def run_tests(self, path: str | None = None, timeout: int = 120, fail_fast: bool = True) -> TestReport:
        args = ["pytest", "-q", "--no-header", "-p", "no:cacheprovider"]
        args += (["-x"] if fail_fast else []) + ([path] if path else [])
        code, out = self._run(args, timeout)

        def count(word: str) -> int:
            m = re.search(rf"(\d+) {word}", out)
            return int(m.group(1)) if m else 0
        return TestReport(passed=count("passed"), failed=count("failed"), errors=count("error"),
                          ok=code == 0, output_tail=out[-2000:])

    def run_ruff(self, timeout: int = 60) -> str:
        code, out = self._run(["ruff", "check", "."], timeout)
        return "" if code == 0 else out[-2000:]
