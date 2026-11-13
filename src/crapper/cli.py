"""Command line for the multi-language CRAP tool."""

from __future__ import annotations

import codecs
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from crapper.analyze import analyze_files
from crapper.coverage import CoverageBundle, load_bundle
from crapper.discover import (
    CLOJURE_TEST_SUFFIXES,
    DOTNET_TEST_DIR_SUFFIXES,
    GO_TEST_SUFFIX,
    JS_TEST_SUFFIXES,
    KOTLIN_TEST_SOURCE_SET_SUFFIX,
    SKIP_DIRS,
    SWIFT_MANIFEST,
    SWIFT_TEST_DIR_SUFFIX,
    TEST_DIRS,
    is_scored,
    iter_source_files,
    language_of,
)
from crapper.metrics import write_metrics
from crapper.model import Entry
from crapper.report import format_report
from crapper.runners import run_coverage

_SKIPPED_DIRS = ", ".join(sorted(SKIP_DIRS | TEST_DIRS))
_TEST_DIRS_DOTNET = " and ".join(f"*{suffix}" for suffix in DOTNET_TEST_DIR_SUFFIXES)
_TEST_PATTERNS = ", ".join(
    [
        f"*{GO_TEST_SUFFIX}",
        *[f"*{suffix}" for suffix in CLOJURE_TEST_SUFFIXES],
        *[f"*{suffix}" for suffix in JS_TEST_SUFFIXES],
        "test_*.py",
        "*_test.py",
        "conftest.py",
    ]
)

HELP = f"""\
Usage: crapper [options] [path-or-filter ...]

Detect the language of each source file and score it with the CRAP metric
CRAP = CC² × (1 − coverage)³ + CC. Writes .metrics/crap.edn for uml-viewer
and prints a report sorted worst first.

Languages: Clojure (.clj .cljc .cljs .bb), Java (.java), Go (.go),
TypeScript and JavaScript (.ts .tsx .mts .cts .js .jsx .mjs .cjs),
Rust (.rs), Python (.py), F# (.fs .fsx), Kotlin (.kt), Swift (.swift).

Options:
  -h, --help                    Print this help and exit.
  --root <path>                 Project root. Metrics are written here.
                                Default: the current directory.
  -s, --source-root <path>      Walk this tree instead of the project root.
                                May be repeated.
  --changed                     Analyze added and modified source files from
                                git status.
  --changed-functions           Analyze the same files as --changed, but report
                                only the functions that overlap a line of
                                `git diff HEAD` or an untracked file.
                                .metrics/crap.edn keeps every function of
                                those files.
  --no-coverage                 Score complexity only. Coverage and CRAP are N/A.
  --use-existing-coverage       Read coverage already on disk. Do not rerun tests.
  --coverage-command <cmd>      Run this command instead of the per-language
                                coverage tools, then read the reports it wrote.
  --threshold <number>          Exit 2 when the worst CRAP score is above this.

Arguments:
  path              File or directory to analyze. Test paths are included when
                    you name them explicitly.
  filter            When the argument is not a path, only source files whose
                    path contains this text are analyzed.

With no paths, source files under the project root are analyzed. Directories
named {_SKIPPED_DIRS} are skipped, as are {_TEST_PATTERNS}.
Folder names count only below the project root, so a project that itself
lives in a folder named tests or *Tests is still analyzed.

F# also skips .fsi files, bin, obj, and {_TEST_DIRS_DOTNET} folders.
Kotlin also skips .kts files and src/*{KOTLIN_TEST_SOURCE_SET_SUFFIX} source sets
such as src/androidTest.
Swift also skips {SWIFT_MANIFEST} and folders named {SWIFT_TEST_DIR_SUFFIX} or *{SWIFT_TEST_DIR_SUFFIX}
such as CoreTests.

Coverage, when it is produced:
  Clojure      clj -M:cov --lcov, then Cloverage form counts or LCOV
  Java         Maven JaCoCo instruction coverage, for each pom.xml module
  Go           go test ./... -coverprofile=...
  TypeScript   npm run coverage, Vitest's own LCOV, or c8 around npm test
  Rust         cargo llvm-cov, or cargo tarpaulin, in the nearest Cargo.toml
  Python       coverage.py LCOV, via pytest or unittest, per project
  F#           dotnet test Cobertura coverage, per .NET test project
  Kotlin       gradlew :koverXmlReport in the Gradle root, which must apply
               the Kover plugin; build/reports/kover/report.xml
  Swift        only with --coverage-command: an Xcode test run with coverage
               and its derived data in target/coverage/swift/, whose profile
               crapper converts with llvm-cov, or a swift test export copied
               there; both go to target/coverage/swift/lcov.info.
               Xcode example:
               --coverage-command 'rm -rf target/coverage/swift &&
                 xcodebuild test -workspace App.xcworkspace -scheme App \\
                 -destination "platform=iOS Simulator,name=iPhone 17" \\
                 -enableCodeCoverage YES \\
                 -derivedDataPath target/coverage/swift/DerivedData'
               Swift package example:
               --coverage-command 'rm -rf target/coverage/swift &&
                 mkdir -p target/coverage/swift &&
                 swift test --enable-code-coverage &&
                 cp "$(swift test --show-codecov-path)" target/coverage/swift/'
               Without the command, or when it exits non-zero, Swift scores 0%.

uml-viewer joins .metrics/crap.edn on :namespace and :name.
  Clojure      the ns, and the defn name
  Java         package.Class, and the method name
  Go           import path, or import.path.Receiver for methods
  TypeScript   dotted module path, or module.Class for methods
  Rust         crate::module, or crate::module::Type for methods
  Python       dotted module path, or module.Class for methods
  F#           namespace and module path, or path.Type for members
  Kotlin       the package, or package.Class for members
  Swift        the module after Sources/, then the type chain, or the file stem
"""


@dataclass
class Options:
    action: str
    message: str = ""
    exit_code: int = 0
    project_root: Path = field(default_factory=lambda: Path("."))
    source_roots: list[str] = field(default_factory=list)
    positionals: list[str] = field(default_factory=list)
    no_coverage: bool = False
    use_existing_coverage: bool = False
    coverage_command: str | None = None
    threshold: float | None = None
    changed: bool = False
    changed_functions: bool = False


def _take(args: list[str], index: int, option: str) -> str:
    if index + 1 >= len(args) or not args[index + 1] or args[index + 1].startswith("-"):
        raise ValueError(f"{option} requires a value")
    return args[index + 1]


def _number(kind, noun: str):
    def convert(raw: str, option: str):
        try:
            return kind(raw)
        except ValueError as exc:
            raise ValueError(f"{option} requires {noun}") from exc

    return convert


_FLAGS = {
    "--no-coverage": "no_coverage",
    "--use-existing-coverage": "use_existing_coverage",
    "--changed": "changed",
    "--changed-functions": "changed_functions",
}

_VALUES = {
    "--root": ("project_root", lambda raw, _option: Path(raw)),
    "--coverage-command": ("coverage_command", lambda raw, _option: raw),
    "--threshold": ("threshold", _number(float, "a number")),
}

def _read_option(options: Options, args: list[str], index: int) -> int:
    """Apply the option at `index` to `options` and return the next index."""

    arg = args[index]
    if arg in _FLAGS:
        setattr(options, _FLAGS[arg], True)
        return index + 1
    if arg in {"-s", "--source-root"}:
        options.source_roots.append(_take(args, index, arg))
        return index + 2
    if arg in _VALUES:
        name, convert = _VALUES[arg]
        setattr(options, name, convert(_take(args, index, arg), arg))
        return index + 2
    if arg.startswith("-"):
        raise ValueError(f"Unknown option: {arg}")
    options.positionals.append(arg)
    return index + 1


def _conflict(options: Options) -> str | None:
    if options.no_coverage and options.coverage_command:
        return "--no-coverage cannot be combined with --coverage-command"
    return None


def parse_args(argv: list[str] | None = None) -> Options:
    args = list(sys.argv[1:] if argv is None else argv)
    if any(arg in {"-h", "--help"} for arg in args):
        return Options(action="help", message=HELP, exit_code=0)
    options = Options(action="analyze")
    index = 0
    try:
        while index < len(args):
            index = _read_option(options, args, index)
    except ValueError as exc:
        return Options(action="help", message=f"{exc}\n\n{HELP}", exit_code=1)
    conflict = _conflict(options)
    if conflict:
        return Options(action="help", message=f"{conflict}\n\n{HELP}", exit_code=1)
    return options


class GitError(Exception):
    """git could not describe the working tree. `code` is git's status."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _changed_files(root: Path) -> list[Path]:
    """Added and modified files from git, including files in new directories."""

    _top, found = _status(root)
    return [path for _code, path in found]


def _status(root: Path) -> tuple[Path, list[tuple[str, Path]]]:
    """The repository top, and each changed file under `root` with its status code.

    Paths come from `git status -z`, which does not quote non-ASCII names.
    They are resolved from the repository root, then limited to `root`, so
    `--root` can be a subdirectory. Deleted files are left out.
    """

    top_result = _git(root, ["rev-parse", "--show-toplevel"])
    if top_result.returncode != 0:
        raise GitError(top_result.returncode, top_result.stderr.strip() or "git status failed")
    status = _git(
        root,
        [
            "status",
            "--porcelain",
            "-z",
            "--no-renames",
            "--untracked-files=all",
            "--",
            ".",
        ],
    )
    if status.returncode != 0:
        raise GitError(status.returncode, status.stderr.strip() or "git status failed")
    top = Path(top_result.stdout.strip())
    limit = root.resolve()
    found: list[tuple[str, Path]] = []
    for entry in status.stdout.split("\0"):
        if len(entry) < 4:
            continue
        path = (top / entry[3:]).resolve()
        if path.is_file() and path.is_relative_to(limit):
            found.append((entry[:2], path))
    return top, found


_HUNK = re.compile(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@")

# A changed file's touched lines. None means every line: an untracked file.
ChangedLines = dict[Path, set[int] | None]


def _diff_path(header: str) -> str | None:
    """The new-side path of a `+++ ` header, or None for a deleted file.

    git ends the header with a tab when the name holds a space.
    """

    name = header[4:].rstrip("\t")
    if name == "/dev/null":
        return None
    if name.startswith('"') and name.endswith('"'):
        name = codecs.escape_decode(name[1:-1].encode("utf-8"))[0].decode("utf-8")
    return name[2:] if name.startswith("b/") else name


def _hunk_lines(line: str) -> range:
    """New-side lines of one `-U0` hunk. A pure deletion touches the line above it."""

    match = _HUNK.match(line)
    if match is None:
        return range(0)
    start = int(match.group(1))
    count = 1 if match.group(2) is None else int(match.group(2))
    if count == 0:
        return range(max(start, 1), max(start, 1) + 1)
    return range(start, start + count)


def _parse_diff(top: Path, text: str, changes: ChangedLines) -> None:
    current: Path | None = None
    in_header = False
    for line in text.splitlines():
        if line.startswith("diff --git "):
            in_header, current = True, None
        elif in_header and line.startswith("+++ "):
            name = _diff_path(line)
            current = None if name is None else (top / name).resolve()
        elif line.startswith("@@"):
            in_header = False
            if current is not None and changes.get(current, set()) is not None:
                changes.setdefault(current, set()).update(_hunk_lines(line))


def _changed_lines(root: Path) -> ChangedLines:
    """Lines changed since HEAD, from `git diff -U0 HEAD`, plus whole untracked files.

    Before the first commit every changed file counts as wholly changed.
    """

    top, found = _status(root)
    if _git(root, ["rev-parse", "--verify", "--quiet", "HEAD"]).returncode != 0:
        return {path: None for _code, path in found}
    changes: ChangedLines = {path: None for code, path in found if code == "??"}
    diff = _git(
        root,
        [
            "-c",
            "core.quotePath=false",
            "diff",
            "-U0",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            "--no-relative",
            "HEAD",
            "--",
            ".",
        ],
    )
    if diff.returncode != 0:
        raise GitError(diff.returncode, diff.stderr.strip() or "git diff failed")
    _parse_diff(top, diff.stdout, changes)
    return changes


def touched_entries(entries: list[Entry], root: Path, changes: ChangedLines) -> list[Entry]:
    """Entries whose line range overlaps a changed line, in their original order."""

    kept: list[Entry] = []
    for entry in entries:
        path = (root / entry.path).resolve()
        if path not in changes:
            continue
        lines = changes[path]
        if lines is None or any(entry.start_line <= line <= entry.end_line for line in lines):
            kept.append(entry)
    return kept


def _positionals(root: Path, args: list[str]) -> tuple[list[Path], list[str]]:
    existing: list[Path] = []
    filters: list[str] = []
    for arg in args:
        candidate = Path(arg)
        if not candidate.is_absolute():
            candidate = root / arg
        if candidate.exists():
            existing.append(candidate.resolve())
        else:
            filters.append(arg)
    return existing, filters


def _changed_source(root: Path) -> list[Path]:
    return [path for path in _changed_files(root) if is_scored(path, root)]


def _explicit_files(root: Path, existing: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in existing:
        if path.is_dir():
            files.extend(iter_source_files([path], root))
        elif language_of(path) is not None:
            files.append(path)
    return files


def _selected(options: Options, root: Path, existing: list[Path]) -> list[Path]:
    if options.changed or options.changed_functions:
        return _changed_source(root)
    if options.source_roots:
        return iter_source_files([(root / path).resolve() for path in options.source_roots], root)
    if existing:
        return _explicit_files(root, existing)
    return iter_source_files([root], root)


def _apply_filters(files: list[Path], filters: list[str]) -> list[Path]:
    if not filters:
        return files
    return [path for path in files if any(item in path.as_posix() for item in filters)]


def select_files(options: Options) -> list[Path]:
    root = options.project_root.resolve()
    existing, filters = _positionals(root, options.positionals)
    files = _apply_filters(_selected(options, root, existing), filters)
    return sorted({path.resolve() for path in files}, key=lambda path: path.as_posix())


def _show_help(options: Options) -> int:
    stream = sys.stdout if options.exit_code == 0 else sys.stderr
    print(options.message, file=stream, end="" if options.message.endswith("\n") else "\n")
    return options.exit_code


def _coverage_bundle(options: Options, root: Path, files: list[Path]):
    if options.no_coverage:
        return None
    if options.use_existing_coverage:
        return load_bundle(root)
    status = run_coverage(root, files, options.coverage_command)
    if options.coverage_command and status not in (0, None):
        return CoverageBundle()
    return load_bundle(root)


def _threshold_status(options: Options, entries) -> int:
    if options.threshold is None:
        return 0
    scored = [entry.crap for entry in entries if entry.crap is not None]
    if scored and max(scored) > options.threshold:
        print(
            f"CRAP threshold exceeded: {max(scored):.1f} > {options.threshold:.1f}",
            file=sys.stderr,
        )
        return 2
    return 0


def run(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    if options.action == "help":
        return _show_help(options)

    root = options.project_root.resolve()
    try:
        files = select_files(options)
        changes = _changed_lines(root) if options.changed_functions and files else None
    except GitError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    if not files:
        print("No source files to analyze.")
        return 0

    entries = analyze_files(files, root, _coverage_bundle(options, root, files))
    metrics = write_metrics(entries, root)
    shown = entries if changes is None else touched_entries(entries, root, changes)
    print(format_report(shown), end="", flush=True)
    print(f"Wrote {metrics}", file=sys.stderr)
    return _threshold_status(options, shown)


def main(argv: list[str] | None = None) -> None:
    sys.exit(run(argv))
