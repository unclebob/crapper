import re
from pathlib import Path
from typing import Protocol

from crapper.model import Model
from crapper.render import SNAPSHOT

ROW = re.compile(
    r'{:name "(.+)" :namespace "(.+)" :complexity (.+) :coverage (.+) :crap (.+)}'
)
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SOURCES = FIXTURES / "sources"
REPORTS = FIXTURES / "reports"
PLANS = FIXTURES / "plans"
POLYGLOT = FIXTURES / "polyglot"
POLYGLOT_SOURCES = [
    "board.go",
    "src/demo/Board.java",
    "src/demo/core.clj",
    "src/demo/tool.py",
    "src/lib.rs",
    "src/ui/view.ts",
]


def scores(root: Path) -> list[str]:
    rows = ROW.findall((root / SNAPSHOT).read_text(encoding="utf-8"))
    return [
        " ".join((namespace, name, *rest)).replace("nil", "None")
        for name, namespace, *rest in rows
    ]


class Outcome(Model):
    code: int
    out: str
    err: str


class Crapper(Protocol):
    def __call__(self, *argv: str | Path) -> Outcome: ...


class Project(Protocol):
    def __call__(self, name: str) -> Path: ...
