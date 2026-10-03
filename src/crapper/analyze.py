from collections.abc import Iterable, Sequence

from crapper.coverage.formats import Segment
from crapper.coverage.measure import Coverage
from crapper.language import Project
from crapper.model import Entry, Function, Scored, Source, Unmeasured


def _worst_first(entry: Entry) -> tuple[bool, float, str, str]:
    function = entry.function
    match entry:
        case Scored(crap=crap):
            return False, -crap, function.namespace, function.name
        case Unmeasured():
            return True, -function.complexity, function.namespace, function.name


def _entry(function: Function, segments: Iterable[Segment] | None) -> Entry:
    if segments is None:
        return Unmeasured(function=function)
    within = [segment for segment in segments if segment.span.overlaps(function.span)]
    counted = [segment for segment in within if segment.branch] or within
    covered = sum(segment.covered for segment in counted)
    total = covered + sum(segment.missed for segment in counted)
    return Scored(function=function, coverage=100 * covered / total if total else 0.0)


def analyze(projects: Sequence[Project], coverage: Coverage | None) -> list[Entry]:
    entries = (
        _entry(function, None if coverage is None else coverage.get(file, ()))
        for project in projects
        for file in project.files
        for function in project.language.functions(Source(home=project.home, path=file))
    )
    return sorted(entries, key=_worst_first)
