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
    ".build",
    "Pods",
    "Carthage",
    "DerivedData",
}

TEST_DIRS = {"test", "tests", "spec", "specs", "__tests__"}
DOTNET_TEST_DIR_SUFFIXES = (".Test", ".Tests")
DOTNET_BUILD_DIRS = {"bin", "obj"}
KOTLIN_TEST_SOURCE_SET_SUFFIX = "Test"
SWIFT_TEST_DIR_SUFFIX = "Tests"
SWIFT_MANIFEST = "Package.swift"

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


def _folders_below(path: Path, root: Path | None) -> tuple[str, ...]:
    """The folders between `root` and the file; all of them without a root."""

    return (path if root is None else path.relative_to(root)).parts[:-1]


def is_test_file(path: str | Path, root: Path | None = None) -> bool:
    """A test file, by its name or by a test folder it sits in.

    Only the folders below `root` count, so a project that itself lives
    inside a folder named like a test folder keeps its files. Without a root,
    `path` is taken as relative to the project and all its folders count.
    """

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
    folders = _folders_below(file_path, root)
    if any(part in TEST_DIRS for part in folders):
        return True
    language = language_of(file_path)
    if language == "fsharp":
        return any(part.endswith(DOTNET_TEST_DIR_SUFFIXES) for part in folders)
    if language == "kotlin":
        return _in_kotlin_test_source_set(folders)
    if language == "swift":
        return any(part.endswith(SWIFT_TEST_DIR_SUFFIX) for part in folders)
    return False


def _in_kotlin_test_source_set(folders: tuple[str, ...]) -> bool:
    """`src/androidTest`, `src/commonTest`, and other Gradle test source sets."""

    return any(
        parent == "src" and child.endswith(KOTLIN_TEST_SOURCE_SET_SUFFIX)
        for parent, child in zip(folders, folders[1:])
    )


def _is_build_output(path: Path, root: Path) -> bool:
    """An F# file under `bin` or `obj` below `root`."""

    return language_of(path) == "fsharp" and any(
        part in DOTNET_BUILD_DIRS for part in _folders_below(path, root)
    )


def is_scored(path: Path, base: Path, walked: Path | None = None) -> bool:
    """A source file to score: in a known language, not a test, not in a skipped
    folder, and not build output.

    Test and build-output folders count only below `base`, the project root.
    Skipped folders such as `vendor` or `build` count only below `walked`, the
    folder being searched (the project root by default), so a folder named on
    the command line is still searched.
    """

    if language_of(path) is None or is_test_file(path, base):
        return False
    if any(part in SKIP_DIRS for part in _folders_below(path, walked or base)):
        return False
    return not _is_build_output(path, base)


def _walk(root: Path, base: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Pruning only saves time: is_scored applies the same folder rules,
        # with skipped folders measured from `root`, as os.walk prunes them.
        dirnames[:] = [
            name for name in dirnames if name not in SKIP_DIRS and name not in TEST_DIRS
        ]
        for name in filenames:
            path = Path(dirpath) / name
            if is_scored(path, base, root):
                found.append(path)
    return found


def iter_source_files(roots: list[Path], base: Path | None = None) -> list[Path]:
    """Source files under each root.

    Folder rules look at the folders below `base`, the project root, when a
    root is inside it, and below the root itself otherwise.
    """

    files: set[Path] = set()
    for root in roots:
        inside = base is not None and root.is_relative_to(base)
        for path in _walk(root, base if inside else root):
            files.add(path.resolve())
    return sorted(files, key=lambda path: path.as_posix())
