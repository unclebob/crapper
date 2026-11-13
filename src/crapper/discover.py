"""Find source files and decide which language each one is written in."""

import os
from pathlib import Path

EXTENSIONS = {
    ".clj": "clojure",
    ".cljc": "clojure",
    ".cljs": "clojure",
    ".bb": "clojure",
    ".java": "java",
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".js": "typescript",
    ".jsx": "typescript",
    ".mjs": "typescript",
    ".cjs": "typescript",
    ".rs": "rust",
    ".py": "python",
    ".fs": "fsharp",
    ".fsx": "fsharp",
    ".kt": "kotlin",
    ".swift": "swift",
}

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".venv",
    "venv",
    "node_modules",
    "vendor",
    "target",
    "dist",
    "build",
    "out",
    "coverage",
    ".metrics",
    "testdata",
    "__pycache__",
    ".clj-kondo",
}

TEST_DIRS = {"test", "tests", "spec", "specs", "__tests__"}
DOTNET_TEST_DIR_SUFFIXES = (".Test", ".Tests")
DOTNET_BUILD_DIRS = {"bin", "obj"}
KOTLIN_TEST_SOURCE_SET_SUFFIX = "Test"
SWIFT_TEST_DIR_SUFFIX = "Tests"
SWIFT_MANIFEST = "Package.swift"
SWIFT_BUILD_DIRS = {".build", "Pods", "Carthage", "DerivedData"}

GO_TEST_SUFFIX = "_test.go"
CLOJURE_TEST_SUFFIXES = ("_test.clj", "_test.cljc", "_test.cljs", "_test.bb")
JS_TEST_SUFFIXES = (
    ".test.ts",
    ".spec.ts",
    ".test.tsx",
    ".spec.tsx",
    ".test.mts",
    ".spec.mts",
    ".test.cts",
    ".spec.cts",
    ".test.js",
    ".spec.js",
    ".test.jsx",
    ".spec.jsx",
    ".test.mjs",
    ".spec.mjs",
    ".test.cjs",
    ".spec.cjs",
)


def language_of(path: str | Path) -> str | None:
    file_path = Path(path)
    name = file_path.name
    if name.endswith(".d.ts"):
        return None
    language = EXTENSIONS.get(file_path.suffix)
    if language == "swift" and name == SWIFT_MANIFEST:
        return None
    return language


def is_swift_build_output(path: Path, root: Path) -> bool:
    """A Swift file under `.build`, `Pods`, `Carthage`, or `DerivedData` below `root`.

    Only the folders below the project root count, so a project that itself
    lives inside a folder with one of those names keeps its files.
    """

    return language_of(path) == "swift" and any(
        part in SWIFT_BUILD_DIRS for part in path.relative_to(root).parts[:-1]
    )


def is_test_file(path: str | Path) -> bool:
    file_path = Path(path)
    name = file_path.name
    if name.endswith(GO_TEST_SUFFIX):
        return True
    if name.endswith(CLOJURE_TEST_SUFFIXES):
        return True
    if name.endswith(JS_TEST_SUFFIXES):
        return True
    if name == "conftest.py":
        return True
    if name.endswith("_test.py") or (name.startswith("test_") and name.endswith(".py")):
        return True
    if any(part in TEST_DIRS for part in file_path.parts):
        return True
    return (
        _in_dotnet_test_project(file_path)
        or _in_kotlin_test_source_set(file_path)
        or _in_swift_test_folder(file_path)
    )


def _fsharp_path_has(path: Path, matches) -> bool:
    return language_of(path) == "fsharp" and any(matches(part) for part in path.parts)


def _in_dotnet_test_project(path: Path) -> bool:
    return _fsharp_path_has(path, lambda part: part.endswith(DOTNET_TEST_DIR_SUFFIXES))


def _in_kotlin_test_source_set(path: Path) -> bool:
    """`src/androidTest`, `src/commonTest`, and other Gradle test source sets."""

    if language_of(path) != "kotlin":
        return False
    parts = path.parts
    return any(
        parent == "src" and child.endswith(KOTLIN_TEST_SOURCE_SET_SUFFIX)
        for parent, child in zip(parts, parts[1:])
    )


def _in_swift_test_folder(path: Path) -> bool:
    """`Tests`, and Xcode test targets such as `CoreTests` and `AppUITests`."""

    return language_of(path) == "swift" and any(
        part.endswith(SWIFT_TEST_DIR_SUFFIX) for part in path.parts[:-1]
    )


def _is_build_output(path: Path) -> bool:
    return _fsharp_path_has(path, lambda part: part in DOTNET_BUILD_DIRS)


def _is_scored(path: Path, root: Path) -> bool:
    if language_of(path) is None or is_test_file(path):
        return False
    return not _is_build_output(path.relative_to(root)) and not is_swift_build_output(path, root)


def _walk(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name for name in dirnames if name not in SKIP_DIRS and name not in TEST_DIRS
        ]
        for name in filenames:
            path = Path(dirpath) / name
            if _is_scored(path, root):
                found.append(path)
    return found


def iter_source_files(roots: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for root in roots:
        for path in _walk(root):
            files.add(path.resolve())
    return sorted(files, key=lambda path: path.as_posix())
