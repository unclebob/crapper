from collections import ChainMap
from collections.abc import Iterable, Sequence
from functools import cache
from pathlib import Path, PurePath, PurePosixPath
from tempfile import TemporaryDirectory, mkdtemp
from typing import Literal

from crapper.coverage.formats import Lines, Report, Segment
from crapper.coverage.tool import run
from crapper.language import Project
from crapper.model import Model, grouped

type Coverage = dict[Path, tuple[Segment, ...]]
type Mode = Literal["run", "existing", "none"]


class Command(Model):
    shell: str


type Plan = Mode | Command


def _first(layers: Iterable[Coverage]) -> Coverage:
    return dict(ChainMap(*layers))


def _agree(key: PurePath, name: PurePath) -> bool:
    shared = min(len(key.parts), len(name.parts))
    return key.parts[-shared:] == name.parts[-shared:]


def _closest(keys: Iterable[PurePosixPath], name: PurePath) -> PurePosixPath | None:
    agreeing = [key for key in keys if _agree(key, name)]
    distance = len(name.parts)
    return (
        min(agreeing, key=lambda key: abs(len(key.parts) - distance))
        if agreeing
        else None
    )


def _named(key: PurePosixPath, root: Path) -> Path | None:
    tails = (root.joinpath(*key.parts[start:]) for start in range(len(key.parts)))
    return next((tail for tail in tails if tail.is_file()), None)


def _key(
    keys: Sequence[PurePosixPath], file: Path, project: Project
) -> PurePosixPath | None:
    home = project.home
    own = [key for key in keys if _named(key, home.root) in (None, file)]
    names = filter(None, (file, home.qualified(file), file.relative_to(home.root)))
    return next(filter(None, (_closest(own, name) for name in names)), None)


def _owned(lines: Lines, project: Project) -> Coverage:
    by_name = grouped(lines, lambda key: key.name)
    return {
        file: lines[key]
        for file in project.files
        if (key := _key(by_name.get(file.name, ()), file, project)) and lines[key]
    }


def resolve(reports: Iterable[Lines], project: Project) -> Coverage:
    return _first(_owned(lines, project) for lines in reports)


def existing(root: Path, projects: Sequence[Project]) -> Coverage:
    read = cache(Report.read)
    return _first(
        resolve(
            (read(report, directory) for report in project.language.reports), project
        )
        for project in projects
        for directory in dict.fromkeys((project.home.directory, root))
    )


def fresh(root: Path, projects: Sequence[Project]) -> Coverage:
    languages = {project.language.name: project.language for project in projects}
    ready = {name: language.ready(root) for name, language in languages.items()}
    prepared = [project for project in projects if ready[project.language.name]]
    with TemporaryDirectory() as scratch:
        return _first(
            resolve(
                project.language.measure(
                    project.measurable(), Path(mkdtemp(dir=scratch))
                ),
                project,
            )
            for project in prepared
        )


def measure(root: Path, projects: Sequence[Project], plan: Plan) -> Coverage | None:
    match plan:
        case "none":
            return None
        case "existing":
            return existing(root, projects)
        case "run":
            return fresh(root, projects)
        case Command(shell=shell):
            return existing(root, projects) if run(["sh", "-c", shell], root) else {}
