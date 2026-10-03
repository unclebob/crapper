import json
from collections.abc import Iterable, Sequence
from pathlib import Path

from pydantic import PositiveInt
from rich import box
from rich.table import Column, Table

from crapper.model import Entry, Model, Name, Namespace, Percent, Scored

SNAPSHOT = Path(".metrics", "crap.edn")
UNBOUNDED = 10_000


class Row(Model):
    name: Name
    namespace: Namespace
    complexity: PositiveInt
    coverage: Percent | None = None
    crap: float | None = None


def _row(entry: Entry) -> Row:
    function = entry.function
    return Row(
        name=function.name,
        namespace=function.namespace,
        complexity=function.complexity,
        coverage=entry.coverage if isinstance(entry, Scored) else None,
        crap=entry.crap if isinstance(entry, Scored) else None,
    )


def _score(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1f}"


def _edn(value: str | float | None) -> str:
    return "nil" if value is None else json.dumps(value, ensure_ascii=False)


def table(entries: Iterable[Entry], languages: Iterable[str]) -> Table:
    rendered = Table(
        *(Column(header, overflow="fold") for header in ("Function", "Namespace")),
        *(Column(header, justify="right") for header in ("CC", "Cov%", "CRAP")),
        title="CRAP Report",
        caption=", ".join(languages),
        box=box.SIMPLE_HEAD,
    )
    for row in map(_row, entries):
        rendered.add_row(
            row.name,
            row.namespace,
            f"{row.complexity}",
            _score(row.coverage),
            _score(row.crap),
        )
    return rendered


def snapshot(entries: Sequence[Entry]) -> str:
    rows = (
        " ".join(
            f":{key} {_edn(value)}" for key, value in _row(entry).model_dump().items()
        )
        for entry in entries
    )
    return "{:entries [\n" + "".join(f" {{{row}}}\n" for row in rows) + "]}\n"
