"""Turn source files and coverage into CRAP entries."""

from pathlib import Path

from crapper.coverage import CoverageBundle
from crapper.crap import make_entry, sort_entries
from crapper.discover import language_of
from crapper.languages import functions_in_file
from crapper.model import Entry, Function


def _coverage(bundle: CoverageBundle | None, function: Function) -> float | None:
    """Percentage for one function.

    None means coverage was not requested (`--no-coverage`). A function the
    report does not mention scores 0%, so it sorts with the other scores
    instead of sinking to the bottom as N/A.
    """

    if bundle is None:
        return None
    found = bundle.percent_for(function)
    if found is None:
        return 0.0
    return found


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
    resolved = [
        (resolved_path, _source_path(resolved_path, root))
        for resolved_path in (file.resolve() for file in files)
    ]
    if bundle is not None:
        bundle.bind_sources([relative for _path, relative in resolved])
    root_text = str(root)
    entries: list[Entry] = []
    for file, relative in resolved:
        language = language_of(file)
        if language is None:
            continue
        source = file.read_text(encoding="utf-8", errors="replace")
        for function in functions_in_file(language, source, relative, root_text):
            entries.append(make_entry(function, _coverage(bundle, function)))
    return sort_entries(entries)
