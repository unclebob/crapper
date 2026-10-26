"""Cobertura line/branch coverage from Coverlet and dotnet-coverage.

Only class-level line tables count. Method tables repeat those lines and must
not inflate coverage. Across classes/runs, line hits are unioned; aggregated
branch counts use the best observed coverage, because Cobertura does not name
individual outcomes well enough to infer a union of complementary runs.
"""

import posixpath
import re
import xml.etree.ElementTree as ET
from pathlib import PureWindowsPath

from crapper.coverage import FileCoverage, normalize_path

_COUNTS = re.compile(r"^\s*[\d.]+%\s*\((\d+)/(\d+)\)\s*$")


def _number(value, name, minimum=0):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Cobertura {name}: {value!r}") from exc
    if number < minimum:
        raise ValueError(f"Invalid Cobertura {name}: {value!r}")
    return number


def merge_record(target, incoming):
    for line, (covered, total) in incoming.items():
        previous = target.get(line, (covered, total))
        target[line] = (max(previous[0], covered), 1)
    for line, (covered, total) in incoming.branches.items():
        previous = target.branches.get(line, (covered, total))
        target.branches[line] = (max(previous[0], covered), max(previous[1], total))


def _filename(class_node, sources):
    name = class_node.get("filename")
    if not name:
        raise ValueError("Cobertura class has no filename")
    name = normalize_path(name)
    if len(sources) == 1 and not name.startswith("/") and not PureWindowsPath(name).is_absolute():
        name = posixpath.normpath(normalize_path(sources[0]) + "/" + name)
    return name


def _line(record, row):
    line = _number(row.get("number"), "line number", 1)
    hits = _number(row.get("hits"), "hit count")
    previous = record.get(line)
    record[line] = (int(hits > 0 or previous is not None and previous[0] > 0), 1)
    text = row.get("condition-coverage")
    if text is not None:
        match = _COUNTS.fullmatch(text)
        if not match:
            raise ValueError(f"Invalid Cobertura branch counts: {text!r}")
        covered, total = map(int, match.groups())
        if total < 1 or covered > total:
            raise ValueError(f"Invalid Cobertura branch counts: {text!r}")
        previous = record.branches.get(line, (covered, total))
        record.branches[line] = (max(previous[0], covered), max(previous[1], total))


def parse_cobertura(text):
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.IGNORECASE):
        raise ValueError("Cobertura XML declarations/entities are not supported")
    root = ET.fromstring(text)
    if root.tag != "coverage":
        raise ValueError("Expected Cobertura coverage XML")
    sources = [source.text.strip() for source in root.findall("./sources/source") if source.text and source.text.strip()]
    found = {}
    for class_node in root.findall("./packages/package/classes/class"):
        record = found.setdefault(_filename(class_node, sources), FileCoverage())
        for row in class_node.findall("./lines/line"):
            _line(record, row)
    return found
