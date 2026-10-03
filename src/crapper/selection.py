import logging
import subprocess
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from crapper.language import TEST_DIRS, Project
from crapper.languages import LANGUAGES, language_of

SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".idea",
        "target",
        "dist",
        "build",
        "out",
        "coverage",
        ".metrics",
        *TEST_DIRS,
    }
).union(*(language.skip for language in LANGUAGES))
_STATUS_PREFIX = len("XY ")

log = logging.getLogger(__name__)


class Outside(ValueError):
    pass


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", f"{root}", *args], stdout=subprocess.PIPE, text=True, check=True
    ).stdout


def _sources(paths: Iterable[Path], base: Path) -> Iterator[Path]:
    return (
        path
        for path in paths
        if (language := language_of(path))
        and not language.is_test(path.relative_to(base))
    )


def _changed(root: Path) -> Iterator[Path]:
    top = Path(_git(root, "rev-parse", "--show-toplevel").strip())
    status = _git(
        root,
        "status",
        "--porcelain",
        "-z",
        "--no-renames",
        "--untracked-files=all",
        "--",
        ".",
    )
    paths = (top / entry[_STATUS_PREFIX:] for entry in status.split("\0") if entry)
    present = (
        path
        for path in paths
        if path.is_file() and SKIP_DIRS.isdisjoint(path.relative_to(root).parts)
    )
    return _sources(present, root)


def _walk(start: Path) -> Iterator[Path]:
    for directory, dirnames, filenames in start.walk():
        dirnames[:] = set(dirnames) - SKIP_DIRS
        yield from _sources((directory / name for name in filenames), start)


def _candidates(root: Path, starts: Sequence[Path], *, changed: bool) -> Iterator[Path]:
    if changed:
        return (
            file
            for file in _changed(root)
            if any(file.is_relative_to(start) for start in starts)
        )
    return (
        file
        for start in starts
        for file in ([start] if start.is_file() else _walk(start))
    )


def select(
    root: Path,
    targets: tuple[str, ...],
    source_roots: tuple[Path, ...],
    *,
    changed: bool,
) -> list[Project]:
    paths = [target for target in targets if (root / target).exists()]
    filters = [target for target in targets if target not in paths]
    starts = [root / start for start in (*source_roots, *paths)] or [root]
    candidates = _candidates(root, starts, changed=changed)
    files = sorted(
        {
            file.resolve()
            for file in candidates
            if not filters or any(text in file.as_posix() for text in filters)
        }
    )
    if outside := [file for file in files if not file.is_relative_to(root)]:
        raise Outside(f"{outside[0]} is outside {root}")
    for text in filters:
        if not any(text in file.as_posix() for file in files):
            log.warning("No source path contains %r.", text)
    for file in files:
        if language_of(file) is None:
            log.warning("%s is not a supported source file.", file)
    return [
        project
        for language in LANGUAGES
        for project in language.projects(root, filter(language.owns, files))
    ]
