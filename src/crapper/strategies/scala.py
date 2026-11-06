"""Scala: methods and complexity from tree-sitter, coverage from scoverage.

Complexity uses the decision points crapper counts for Java: `if`, `while`,
`do`/`while`, `for`, each `for` or `case` guard, each `case` clause (in a
match, a partial function, or a `catch`), and each `&&` and `||`. Function
literals count toward the method around them. Nested methods, classes,
objects, and traits are scored on their own; a method local to another is
named `outer.inner`. Secondary constructors (`def this`) are ignored, as Java
constructors are.

Coverage is scoverage statement coverage. scoverage records each statement's
source file and character offsets; a statement belongs to the innermost method
whose span contains its start, so a local method's statements do not count for
the method around it.
"""

import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from crapper.languages.treesitter import (
    child_of_type,
    complexity,
    end_line,
    node_text,
    parse,
    start_line,
)
from crapper.model import Function

_TYPES = {"class_definition", "object_definition", "trait_definition", "enum_definition"}
_SCOPES = _TYPES | {"function_definition"}
_DECISIONS = {
    "if_expression",
    "while_expression",
    "do_while_expression",
    "for_expression",
    "guard",
    "case_clause",
}
_LOGIC = {"&&", "||"}
_TEST_SUFFIXES = ("Suite.scala", "Spec.scala", "Test.scala", "Tests.scala")


def _package_name(data: bytes, clause) -> str:
    ident = child_of_type(clause, "package_identifier")
    return node_text(data, ident) if ident is not None else ""


def _name(data: bytes, node) -> str | None:
    # operator methods such as `def +` are named by an operator_identifier
    ident = child_of_type(node, "identifier", "operator_identifier")
    return node_text(data, ident) if ident is not None else None


def _complexity(data: bytes, method) -> int:
    def is_decision(node) -> bool:
        if node.type in _DECISIONS:
            return True
        if node.type == "infix_expression":
            op = child_of_type(node, "operator_identifier")
            return op is not None and node_text(data, op) in _LOGIC
        return False

    def skip(node) -> bool:
        return node != method and node.type in _SCOPES

    return complexity(method, is_decision, skip)


@dataclass(frozen=True)
class _Scope:
    """Where a node sits: its packages, enclosing types, and enclosing method."""

    packages: tuple[str, ...] = ()
    types: tuple[str, ...] = ()
    outer: str | None = None

    def namespace(self, path: str) -> str:
        parts = [p for p in self.packages + self.types if p]
        return ".".join(parts) if parts else Path(path).stem

    def qualify(self, name: str) -> str:
        return f"{self.outer}.{name}" if self.outer else name


class _Extractor:
    def __init__(self, data: bytes, path: str):
        self.data = data
        self.path = path
        self.found: list[Function] = []

    def visit(self, node, scope: _Scope) -> None:
        for child in node.children:
            scope = self._visit_child(child, scope)

    def _visit_child(self, child, scope: _Scope) -> _Scope:
        """Visits one child; returns the scope for the siblings after it."""

        if child.type == "package_clause":
            # `package a.b` without a body applies to everything after it
            inner = _Scope(scope.packages + (_package_name(self.data, child),), scope.types, scope.outer)
            body = child_of_type(child, "template_body")
            if body is not None:
                # `package a { ... }` scopes only its own body
                self.visit(body, inner)
                return scope
            return inner
        if child.type in _TYPES:
            self.visit(child, _Scope(scope.packages, scope.types + (_name(self.data, child) or "",)))
        elif child.type == "function_definition":
            self._method(child, scope)
        else:
            self.visit(child, scope)
        return scope

    def _method(self, node, scope: _Scope) -> None:
        name = _name(self.data, node)
        if name is None or name == "this":
            return
        qualified = scope.qualify(name)
        self.found.append(
            Function(
                name=qualified,
                namespace=scope.namespace(self.path),
                complexity=_complexity(self.data, node),
                start_line=start_line(node),
                end_line=end_line(node),
                path=self.path,
                language="scala",
                start_byte=node.start_byte,
                end_byte=node.end_byte,
            )
        )
        self.visit(node, _Scope(scope.packages, scope.types, qualified))


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    del project_root
    data, tree = parse(source, "scala")
    extractor = _Extractor(data, path)
    extractor.visit(tree.root_node, _Scope())
    return extractor.found


# ---- coverage --------------------------------------------------------------


@dataclass
class ScoverageIndex:
    """Statements from scoverage reports: source path -> {(start, end): (statements, invoked)}.

    scoverage can record several statements with the same span (a call and its
    receiver, say) and counts each one, so a span keeps its statement count.
    """

    root: Path
    statements: dict[str, dict[tuple[int, int], tuple[int, int]]] = field(default_factory=dict)
    #: (total, invoked) per method byte span, per source file; filled on first lookup
    counts: dict[str, dict[tuple[int, int], tuple[int, int]]] = field(default_factory=dict)


def parse_scoverage(text: str) -> dict[str, dict[tuple[int, int], tuple[int, int]]]:
    found: dict[str, dict[tuple[int, int], tuple[int, int]]] = {}
    for element in ET.fromstring(text).iter("statement"):
        if element.get("ignored") == "true":
            continue
        source = element.get("source")
        start, end = element.get("start"), element.get("end")
        if not source or start is None or end is None:
            continue
        span = (int(start), int(end))
        invoked = int(element.get("invocation-count") or 0) > 0
        statements = found.setdefault(source, {})
        total, hit = statements.get(span, (0, 0))
        statements[span] = (total + 1, hit + (1 if invoked else 0))
    return found


def scoverage_reports(root: Path) -> list[Path]:
    """Mill (per module and aggregate) and sbt (sbt 1 and sbt 2 layouts) scoverage XML."""

    paths = list(root.glob("out/**/scoverage.xml"))
    paths.extend(root.glob("target/**/scoverage-report/scoverage.xml"))
    paths.extend(root.glob("*/target/**/scoverage-report/scoverage.xml"))
    return sorted(set(paths))


def _char_to_byte(text: str):
    """Maps a character offset to a UTF-8 byte offset (identity for ASCII sources)."""

    if text.isascii():
        return lambda offset: offset
    offsets = [0]
    for char in text:
        offsets.append(offsets[-1] + len(char.encode("utf-8")))
    return lambda offset: offsets[min(offset, len(offsets) - 1)]


def _method_counts(
    source_file: Path, path: str, statements: dict[tuple[int, int], tuple[int, int]]
) -> dict[tuple[int, int], tuple[int, int]]:
    """(total, invoked) statements per method byte span, each statement in its innermost method."""

    text = source_file.read_text(encoding="utf-8", errors="replace")
    spans = [(f.start_byte, f.end_byte) for f in functions_in_source(text, path)]
    to_byte = _char_to_byte(text)
    counts: dict[tuple[int, int], tuple[int, int]] = {}
    for (start, _end), (statement_count, invoked) in statements.items():
        offset = to_byte(start)
        enclosing = [s for s in spans if s[0] <= offset < s[1]]
        if not enclosing:
            continue
        span = min(enclosing, key=lambda s: s[1] - s[0])
        total, hit = counts.get(span, (0, 0))
        counts[span] = (total + statement_count, hit + invoked)
    return counts


class ScalaStrategy:
    name = "scala"
    extensions = (".scala",)

    def is_test_file(self, path: Path) -> bool:
        return Path(path).name.endswith(_TEST_SUFFIXES)

    def functions_in_source(
        self, source: str, path: str, project_root: str | None
    ) -> list[Function]:
        return functions_in_source(source, path, project_root)

    def load_coverage(self, root: Path) -> ScoverageIndex | None:
        index = ScoverageIndex(root=root.resolve())
        for report in scoverage_reports(root):
            text = report.read_text(encoding="utf-8", errors="replace")
            for source, statements in parse_scoverage(text).items():
                # a per-module report and the aggregate list the same statements;
                # keep the larger count, not the sum
                merged = index.statements.setdefault(source, {})
                for span, (total, hit) in statements.items():
                    seen_total, seen_hit = merged.get(span, (0, 0))
                    merged[span] = (max(total, seen_total), max(hit, seen_hit))
        return index if index.statements else None

    def percent_for(
        self,
        coverage: ScoverageIndex | None,
        function: Function,
        source_parts: list[tuple[str, ...]],
    ) -> float | None:
        if coverage is None:
            return None
        from crapper.coverage import _lookup, coverage_percent

        statements = _lookup(coverage.statements, function.path, source_parts)
        if statements is None:
            return None
        source_file = coverage.root / function.path
        if not source_file.is_file():
            return None
        key = str(source_file)
        if key not in coverage.counts:
            coverage.counts[key] = _method_counts(source_file, function.path, statements)
        counts = coverage.counts[key]
        total, hit = counts.get((function.start_byte, function.end_byte), (0, 0))
        if total == 0:
            return None
        return coverage_percent(hit, total)

    def run_coverage(self, root: Path, files: list[Path]) -> None:
        del files
        for build, cover in ((_is_mill, _cover_mill), (_is_sbt, _cover_sbt)):
            if build(root):
                code = cover(root)
                if code != 0:
                    print(f"Scala coverage exited {code}. Scala coverage will score 0%.", file=sys.stderr)
                return
        print("No build.mill, build.sc or build.sbt; skipping Scala coverage.", file=sys.stderr)


def _is_mill(root: Path) -> bool:
    return (root / "build.mill").is_file() or (root / "build.sc").is_file()


def _is_sbt(root: Path) -> bool:
    return (root / "build.sbt").is_file()


def _cover_mill(root: Path) -> int:
    from crapper.runners import run_shell

    mill = "./mill" if (root / "mill").is_file() else "mill"
    # measurements from earlier runs would count as coverage
    for stale in root.glob("out/**/scoverage/data.dest/scoverage.measurements.*"):
        stale.unlink()
    code = run_shell([mill, "--ticker", "false", "__.test"], root)
    if code != 0:
        return code
    return run_shell([mill, "--ticker", "false", "__.scoverage.xmlReport"], root)


def _is_sbt2(root: Path) -> bool:
    properties = root / "project" / "build.properties"
    return properties.is_file() and "sbt.version=2" in properties.read_text().replace(" ", "")


def _cover_sbt(root: Path) -> int:
    from crapper.runners import run_shell

    # sbt 2 runs `test` incrementally; testFull runs every suite
    test = "testFull" if _is_sbt2(root) else "test"
    return run_shell(["sbt", f"coverage; {test}; coverageReport"], root)
