import re
from collections.abc import Callable
from itertools import chain
from pathlib import Path, PurePosixPath
from typing import Self
from urllib.parse import unquote
from xml.etree import ElementTree

from pydantic import NonNegativeInt, PositiveInt

from crapper.decode import decoded
from crapper.model import Model, Span, grouped

_LCOV_SOURCE = re.compile(r"^\s*SF:", re.MULTILINE)
_LCOV_LINE = re.compile(r"^\s*DA:(\d+),(\d+)", re.MULTILINE)
_LCOV_BRANCH = re.compile(r"^\s*BRDA:(\d+),[^,]*,[^,]*,(-|\d+)", re.MULTILINE)
_GO_BLOCK = re.compile(r"(.+):(\d+)\.\d+,(\d+)\.\d+ (\d+) (\d+)")
_CLOVERAGE_TITLE = re.compile(r"<title>\s*(.+?)\s*</title>")
_CLOVERAGE_FORMS = re.compile(
    r'<span[^>]*title="(\d+) out of (\d+) forms covered"[^>]*>\s*(\d+)&nbsp;'
)


class Segment(Model):
    span: Span
    covered: NonNegativeInt
    missed: NonNegativeInt
    branch: bool = False

    @classmethod
    def line(
        cls,
        line: PositiveInt,
        covered: NonNegativeInt,
        missed: NonNegativeInt,
        *,
        branch: bool = False,
    ) -> Self:
        return cls(
            span=Span(start=line, end=line),
            covered=covered,
            missed=missed,
            branch=branch,
        )


type Lines = dict[PurePosixPath, tuple[Segment, ...]]


class Format(Model):
    name: str
    parse: Callable[[str], Lines]

    def read(self, path: Path) -> Lines:
        files = [path] if path.is_file() else sorted(path.rglob(self.name))
        return {
            source: segments
            for file in files
            for source, segments in decoded(file, self.parse).items()
        }


class Report(Model):
    format: Format
    path: Path

    def read(self, directory: Path) -> Lines:
        return self.format.read(directory / self.path)


def source_path(raw: str) -> PurePosixPath:
    return PurePosixPath(unquote(raw).replace("\\", "/").removeprefix("file:"))


def _lcov(text: str) -> Lines:
    records = _LCOV_SOURCE.split(text)[1:]
    if text.strip() and not records:
        raise ValueError("no LCOV source records")
    return {
        source_path(source.strip()): tuple(
            chain(
                (
                    Segment.line(line, int(hits > 0), int(hits == 0))
                    for line, hits in (
                        map(int, found.groups()) for found in _LCOV_LINE.finditer(lines)
                    )
                ),
                (
                    Segment.line(int(line), taken, 1 - taken, branch=True)
                    for line, taken in (
                        (found[1], int(found[2] not in ("-", "0")))
                        for found in _LCOV_BRANCH.finditer(lines)
                    )
                ),
            )
        )
        for source, _, lines in (record.partition("\n") for record in records)
    }


def _jacoco(text: str) -> Lines:
    try:
        report = ElementTree.fromstring(text)
        return {
            PurePosixPath(package.attrib["name"], source.attrib["name"]): tuple(
                Segment.line(*(int(line.attrib[key]) for key in ("nr", "ci", "mi")))
                for line in source.iterfind("line")
            )
            for package in report.iterfind("package")
            for source in package.iterfind("sourcefile")
        }
    except (ElementTree.ParseError, KeyError) as invalid:
        raise ValueError(f"invalid JaCoCo XML: {invalid}") from invalid


def _go_block(line: str) -> re.Match[str]:
    if not (block := _GO_BLOCK.fullmatch(line)):
        raise ValueError(f"invalid Go coverage block: {line!r}")
    return block


def _go_segment(block: re.Match[str]) -> Segment:
    start, end, statements, hits = map(int, block.groups()[1:])
    covered = statements if hits else 0
    return Segment(
        span=Span(start=start, end=end), covered=covered, missed=statements - covered
    )


def _go_profile(text: str) -> Lines:
    blocks = (
        _go_block(line)
        for line in map(str.strip, text.splitlines())
        if line and not line.startswith("mode:")
    )
    by_source = grouped(blocks, lambda block: source_path(block[1]))
    return {
        source: tuple(map(_go_segment, group)) for source, group in by_source.items()
    }


def _cloverage(html: str) -> Lines:
    segments = tuple(
        Segment.line(line, covered, total - covered)
        for covered, total, line in (
            map(int, found.groups()) for found in _CLOVERAGE_FORMS.finditer(html)
        )
    )
    title = _CLOVERAGE_TITLE.search(html)
    return {source_path(title[1]): segments} if title and segments else {}


LCOV = Format(name="lcov.info", parse=_lcov)
JACOCO = Format(name="jacoco.xml", parse=_jacoco)
GO_PROFILE = Format(name="coverage.out", parse=_go_profile)
CLOVERAGE = Format(name="*.html", parse=_cloverage)

REPORT_DIR = Path("target", "coverage")
LCOV_REPORTS = (
    Report(format=LCOV, path=REPORT_DIR),
    Report(format=LCOV, path=Path("coverage")),
)
