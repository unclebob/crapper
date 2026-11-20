"""Turn source files and coverage into CRAP entries."""

import sys
from pathlib import Path

from crapper.coverage import CoverageBundle
from crapper.crap import make_entry, sort_entries
from crapper.discover import language_of
from crapper.languages import functions_in_file
from crapper.model import Entry, Function


def _coverage(bundle: CoverageBundle | None, function: Function, missing: set[str]) -> float | None:
    """Percentage for one function.

    None means coverage was not requested (`--no-coverage`). A function the
    report does not mention scores 0%, so it sorts with the other scores
    instead of sinking to the bottom as N/A.
    """

    if bundle is None:
        return None
    found = bundle.percent_for(function)
    if found is None:
        missing.add(function.path)
        return 0.0
    return found


def _warn_missing(missing: set[str]) -> None:
    if missing:
        print(f"{len(missing)} file(s) have no coverage data, so their functions score 0%:", file=sys.stderr)
        for path in sorted(missing):
            print(f"  {path}", file=sys.stderr)


def _source_path(file: Path, root: Path) -> str:
    try:
        return file.relative_to(root).as_posix()
    except ValueError:
        return file.as_posix()


def analyze_files(
    files: list[Path],
    project_root: Path,
    bundle: CoverageBundle | None,
) -> list[Entry]:
    root = project_root.resolve()
    if bundle is not None:
        bundle.bind_sources([_source_path(file.resolve(), root) for file in files])
    entries: list[Entry] = []
    missing: set[str] = set()
    for file in files:
        file = file.resolve()
        language = language_of(file)
        if language is None:
            continue
        source = file.read_text(encoding="utf-8", errors="replace")
        try:
            relative = file.relative_to(root).as_posix()
        except ValueError:
            relative = file.as_posix()
        for function in functions_in_file(language, source, relative, str(root)):
            entries.append(make_entry(function, _coverage(bundle, function, missing)))
    _warn_missing(missing)
    return sort_entries(entries)
