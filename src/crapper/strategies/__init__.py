"""Language strategies: one object per language, holding everything crapper
needs to know about that language.

A strategy answers which files are its sources and tests, finds the functions
in a source file with their complexity, reads its coverage reports, and runs
its coverage tool. Discovery, extraction, coverage lookup, and the coverage
runner ask the registry first, so adding a language means adding one
strategy, not editing each of those modules.
"""

from pathlib import Path
from typing import Any, Protocol

from crapper.model import Function


class LanguageStrategy(Protocol):
    #: The language name, as it appears in `Function.language` and the report.
    name: str
    #: File suffixes, with the dot, that belong to this language.
    extensions: tuple[str, ...]

    def is_test_file(self, path: Path) -> bool:
        """True for a test source outside a test directory, e.g. `BoardSuite.scala`."""

    def functions_in_source(
        self, source: str, path: str, project_root: str | None
    ) -> list[Function]:
        """The scored functions in one file, with their cyclomatic complexity."""

    def load_coverage(self, root: Path) -> Any | None:
        """Read the coverage reports already on disk, or None when there are none."""

    def percent_for(
        self,
        coverage: Any | None,
        function: Function,
        source_parts: list[tuple[str, ...]],
    ) -> float | None:
        """Coverage percentage for one function, or None when the report does not mention it."""

    def run_coverage(self, root: Path, files: list[Path]) -> None:
        """Run the coverage tool so `load_coverage` finds fresh reports."""


def _strategies() -> list[LanguageStrategy]:
    from crapper.strategies.scala import ScalaStrategy

    return [ScalaStrategy()]


STRATEGIES: dict[str, LanguageStrategy] = {s.name: s for s in _strategies()}

BY_EXTENSION: dict[str, LanguageStrategy] = {
    extension: strategy
    for strategy in STRATEGIES.values()
    for extension in strategy.extensions
}


def strategy_for(language: str | None) -> LanguageStrategy | None:
    if language is None:
        return None
    return STRATEGIES.get(language)
