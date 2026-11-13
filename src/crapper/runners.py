"""Run each language's coverage tool, then leave the reports for the loader.

Failures are reported and do not stop analysis. A language with no coverage
tool, or a failed run, scores its functions at 0%.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from crapper.discover import DOTNET_BUILD_DIRS, SKIP_DIRS, is_test_file, language_of
from crapper.languages import swift_coverage

_MAVEN = [
    "mvn",
    "-q",
    "org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent",
    "test",
    "org.jacoco:jacoco-maven-plugin:0.8.12:report",
]


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def _show(command: str | list[str]) -> str:
    if isinstance(command, str):
        return command
    return " ".join(shlex.quote(part) for part in command)


def run_shell(command: str | list[str], cwd: Path) -> int:
    """Run a coverage command.

    A list is an argument vector and does not go through a shell, so a path
    with spaces or metacharacters stays one argument. A string is a command
    the user typed in `--coverage-command` and runs in a shell.
    """

    _warn(f"+ ({cwd}) {_show(command)}")
    try:
        if isinstance(command, str):
            completed = subprocess.run(command, cwd=cwd, shell=True)
        else:
            completed = subprocess.run(list(command), cwd=cwd)
    except OSError as exc:
        _warn(f"Coverage command failed to start: {exc}")
        return 127
    return completed.returncode


def nearest_marker(start: Path, marker: str, stop: Path) -> Path | None:
    current = start if start.is_dir() else start.parent
    stop = stop.resolve()
    while True:
        if (current / marker).is_file():
            return current
        if current == stop or current.parent == current:
            return None
        current = current.parent


def _clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


_COVERAGE_DIRS = {"typescript", "rust", "go", "python", "fsharp", "swift"}


def _walk_outside_language_dirs(coverage: Path):
    """Each folder under `coverage` with its file names, never entering a language folder.

    A language folder is skipped at any depth, and Swift's holds Xcode's
    derived data, so it is not walked at all.
    """

    for dirpath, dirnames, filenames in os.walk(coverage):
        dirnames[:] = [name for name in dirnames if name not in _COVERAGE_DIRS]
        yield Path(dirpath), filenames


def _remove_cloverage_html(coverage: Path) -> None:
    for folder, filenames in _walk_outside_language_dirs(coverage):
        for name in filenames:
            if name.endswith(".html"):
                (folder / name).unlink()


def _remove_empty_dirs(coverage: Path) -> None:
    directories = [
        folder for folder, _files in _walk_outside_language_dirs(coverage) if folder != coverage
    ]
    for path in sorted(directories, reverse=True):
        try:
            path.rmdir()
        except OSError:
            continue


def _clean_clojure(root: Path) -> None:
    """Remove Cloverage's HTML and top-level lcov without touching other reports.

    Other languages keep their directories. Files that are not Cloverage HTML
    stay, including anything a project keeps under target/coverage itself.
    """

    coverage = root / "target" / "coverage"
    if not coverage.is_dir():
        return
    lcov = coverage / "lcov.info"
    if lcov.is_file():
        lcov.unlink()
    _remove_cloverage_html(coverage)
    _remove_empty_dirs(coverage)


_VITEST_CONFIGS = (
    "vitest.config.ts",
    "vitest.config.mts",
    "vitest.config.cts",
    "vitest.config.js",
    "vitest.config.mjs",
    "vitest.config.cjs",
)


class PackageJsonError(Exception):
    """package.json is present and cannot be read as an object."""


def _package_json(package: Path) -> dict | None:
    path = package / "package.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PackageJsonError(f"{path}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise PackageJsonError(f"{path}: expected a JSON object")
    return data


def _uses_vitest(package: Path, scripts: dict) -> bool:
    if "vitest" in str(scripts.get("test", "")):
        return True
    return any((package / name).is_file() for name in _VITEST_CONFIGS)


def _vitest_version(package: Path) -> str | None:
    installed = package / "node_modules" / "vitest" / "package.json"
    if installed.is_file():
        try:
            data = json.loads(installed.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            _warn(f"{installed}: {exc.msg}")
            data = None
        if isinstance(data, dict) and isinstance(data.get("version"), str):
            return data["version"]
    return None


def _manifest_snapshot(package: Path) -> dict[Path, bytes | None]:
    snapshot: dict[Path, bytes | None] = {}
    for name in ("package.json", "package-lock.json", "npm-shrinkwrap.json"):
        path = package / name
        snapshot[path] = path.read_bytes() if path.is_file() else None
    return snapshot


def _restore_manifests(snapshot: dict[Path, bytes | None]) -> None:
    for path, content in snapshot.items():
        if content is None:
            if path.is_file():
                path.unlink()
        elif not path.is_file() or path.read_bytes() != content:
            path.write_bytes(content)


def _ensure_vitest_coverage(package: Path) -> bool:
    """Vitest collects coverage itself. c8 never sees its worker processes."""

    if (package / "node_modules" / "@vitest" / "coverage-v8").is_dir():
        return True
    version = _vitest_version(package)
    spec = f"@vitest/coverage-v8@{version}" if version else "@vitest/coverage-v8"
    _warn(
        f"Installing {spec} so Vitest can write LCOV. "
        "package.json and the lockfile are restored afterward."
    )
    snapshot = _manifest_snapshot(package)
    try:
        code = run_shell(
            ["npm", "install", "--no-save", "--no-package-lock", spec],
            package,
        )
    finally:
        _restore_manifests(snapshot)
    ready = code == 0 and (package / "node_modules" / "@vitest" / "coverage-v8").is_dir()
    if not ready:
        _warn("Vitest's coverage provider is missing. TypeScript coverage will score 0%.")
    return ready


def typescript_packages(root: Path, files: list[Path]) -> list[Path]:
    packages: set[Path] = set()
    root = root.resolve()
    for file in files:
        if language_of(file) != "typescript":
            continue
        package = nearest_marker(file, "package.json", root)
        if package is not None:
            packages.add(package.resolve())
    return sorted(packages)


def typescript_command(
    package: Path, files: list[Path], report_dir: Path
) -> list[str] | None:
    """Argument vector that writes LCOV into `report_dir`, or None when there is no test script."""

    data = _package_json(package)
    if data is None:
        return None
    scripts = data.get("scripts") or {}
    if not isinstance(scripts, dict):
        scripts = {}
    if "coverage" in scripts:
        return ["npm", "run", "coverage"]
    if _uses_vitest(package, scripts):
        return _vitest_coverage_command(package, files, report_dir)
    if "test" not in scripts:
        return None
    return [
        "npx",
        "--yes",
        "c8",
        "--reporter=lcov",
        "--reports-dir",
        str(report_dir),
        "npm",
        "test",
    ]


def _vitest_includes(package: Path, files: list[Path]) -> list[str]:
    includes: list[str] = []
    package = package.resolve()
    for file in files:
        if language_of(file) != "typescript":
            continue
        resolved = Path(file).resolve()
        try:
            relative = resolved.relative_to(package)
        except ValueError:
            continue
        if not is_test_file(resolved, package):
            includes.append(relative.as_posix())
    return includes


def _vitest_coverage_command(package: Path, files: list[Path], report_dir: Path) -> list[str]:
    binary = package / "node_modules" / ".bin" / "vitest"
    if binary.is_file():
        command = [str(binary)]
    else:
        command = ["npx", "vitest"]
    command.extend(
        [
            "run",
            "--coverage",
            "--coverage.reporter=lcov",
            f"--coverage.reportsDirectory={report_dir}",
            "--coverage.reportOnFailure=true",
        ]
    )
    for include in _vitest_includes(package, files):
        command.append(f"--coverage.include={include}")
    return command


def _coverage_report(root: Path, module: Path, language: str) -> Path:
    root = root.resolve()
    module = module.resolve()
    if module == root:
        return root / "target" / "coverage" / language / "lcov.info"
    slug = module.relative_to(root).as_posix().replace("/", "__")
    return root / "target" / "coverage" / language / slug / "lcov.info"


def rust_modules(root: Path, files: list[Path]) -> list[Path]:
    root = root.resolve()
    return [
        module.resolve()
        for module in _modules_with(files, ".rs", "Cargo.toml", root)
    ]


def _rust_kind() -> str | None:
    if shutil.which("cargo-llvm-cov"):
        return "llvm-cov"
    if shutil.which("cargo-tarpaulin"):
        return "tarpaulin"
    _warn("Neither cargo-llvm-cov nor cargo-tarpaulin is installed. Installing cargo-llvm-cov.")
    if shutil.which("rustup"):
        code = run_shell(["rustup", "component", "add", "llvm-tools-preview"], Path.home())
        if code != 0:
            _warn("rustup component add llvm-tools-preview failed.")
    code = run_shell(["cargo", "install", "cargo-llvm-cov", "--locked"], Path.home())
    if code == 0 and shutil.which("cargo-llvm-cov"):
        return "llvm-cov"
    _warn("Rust coverage will score 0%.")
    return None


_PYTHON_MARKERS = ("pyproject.toml", "setup.cfg", "setup.py", "pytest.ini", "tox.ini")


def python_roots(root: Path, files: list[Path]) -> list[Path]:
    found: set[Path] = set()
    root = root.resolve()
    for file in files:
        if Path(file).suffix != ".py":
            continue
        module = None
        for marker in _PYTHON_MARKERS:
            module = nearest_marker(Path(file), marker, root)
            if module is not None:
                break
        found.add((module or root).resolve())
    return sorted(found)


def _python_executable(package: Path) -> str:
    for relative in (".venv/bin/python", "venv/bin/python"):
        candidate = package / relative
        if candidate.is_file():
            return str(candidate)
    return "python3"


def uses_pytest(package: Path) -> bool:
    if (package / "pytest.ini").is_file() or (package / "conftest.py").is_file():
        return True
    for name in ("pyproject.toml", "setup.cfg", "tox.ini"):
        path = package / name
        if path.is_file() and "pytest" in path.read_text(encoding="utf-8", errors="replace"):
            return True
    return False


def python_sources(package: Path, files: list[Path]) -> str:
    """Directories coverage.py should report even when a file was never imported."""

    tops: set[str] = set()
    package = package.resolve()
    for file in files:
        path = Path(file)
        if path.suffix != ".py":
            continue
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(package)
        except ValueError:
            continue
        if not is_test_file(resolved, package):
            tops.add(_source_name(relative))
    return ",".join(sorted(tops))


def _source_name(relative: Path) -> str:
    """A top-level module is named without .py, which coverage.py --source requires."""

    if len(relative.parts) == 1:
        return relative.stem
    return relative.parts[0]


def python_coverage_commands(
    py: str, kind: str, data_file: Path, report: Path, source: str
) -> tuple[list[str], list[str]]:
    run = [py, "-m", "coverage", "run", f"--data-file={data_file}"]
    if source:
        run.append(f"--source={source}")
    if kind == "pytest":
        run.extend(["-m", "pytest"])
    else:
        run.extend(["-m", "unittest", "discover", "-s", "."])
    lcov = [py, "-m", "coverage", "lcov", f"--data-file={data_file}", "-o", str(report)]
    return run, lcov


def _ensure_python_module(py: str, package: Path, module: str) -> bool:
    if run_shell([py, "-c", f"import {module}"], package) == 0:
        return True
    _warn(
        f"Installing {module} for Python coverage. "
        "The project requirements are left unchanged."
    )
    code = run_shell(
        [py, "-m", "pip", "install", "--disable-pip-version-check", module],
        package,
    )
    return code == 0


def rust_coverage_command(kind: str, report: Path) -> list[str]:
    if kind == "llvm-cov":
        return ["cargo", "llvm-cov", "--lcov", "--output-path", str(report)]
    return ["cargo", "tarpaulin", "--out", "Lcov", "--output-dir", str(report.parent)]


def _languages_in(files: list[Path]) -> set[str]:
    found = set()
    for file in files:
        language = language_of(file)
        if language:
            found.add(language)
    return found


def _modules_with(files: list[Path], suffix: str, marker: str, root: Path) -> list[Path]:
    modules: set[Path] = set()
    for file in files:
        if Path(file).suffix != suffix:
            continue
        module = nearest_marker(file, marker, root)
        if module is not None:
            modules.add(module)
    return sorted(modules)


def _cover_clojure(root: Path) -> None:
    if not (root / "deps.edn").is_file() and not (root / "bb.edn").is_file():
        _warn("No deps.edn or bb.edn; skipping Clojure coverage.")
        return
    _clean_clojure(root)
    code = run_shell(["clj", "-M:cov", "--lcov"], root)
    if code != 0:
        _warn("clj -M:cov --lcov failed; retrying without --lcov.")
        code = run_shell(["clj", "-M:cov"], root)
    if code != 0:
        _warn(f"Clojure coverage exited {code}. Clojure coverage will score 0%.")


def _cover_java(root: Path, files: list[Path]) -> None:
    modules = _modules_with(files, ".java", "pom.xml", root)
    if not modules:
        _warn("No pom.xml; skipping Java coverage.")
        return
    for module in modules:
        _clean_dir(module / "target" / "site" / "jacoco")
        exec_file = module / "target" / "jacoco.exec"
        if exec_file.exists():
            exec_file.unlink()
        code = run_shell(_MAVEN, module)
        if code != 0:
            _warn(f"Java coverage exited {code} in {module}. Java coverage will score 0%.")


def _cover_go(root: Path, files: list[Path]) -> None:
    modules = _modules_with(files, ".go", "go.mod", root)
    if not modules:
        _warn("No go.mod; skipping Go coverage.")
        return
    for module in modules:
        profile = module / "target" / "coverage" / "go" / "coverage.out"
        profile.parent.mkdir(parents=True, exist_ok=True)
        if profile.exists():
            profile.unlink()
        code = run_shell(["go", "test", "./...", f"-coverprofile={profile}"], module)
        if code != 0:
            _warn(f"Go coverage exited {code} in {module}. Go coverage will score 0%.")


def _prepare_report(report: Path) -> None:
    if report.parent.exists():
        shutil.rmtree(report.parent)
    report.parent.mkdir(parents=True, exist_ok=True)


def _cover_typescript(root: Path, files: list[Path]) -> None:
    packages = typescript_packages(root, files)
    if not packages:
        _warn("No package.json; skipping TypeScript coverage.")
        return
    for package in packages:
        report = _coverage_report(root, package, "typescript")
        try:
            command = typescript_command(package, files, report.parent)
        except PackageJsonError as exc:
            _warn(str(exc))
            continue
        if command is None:
            _warn(f"No package.json test script in {package}; skipping TypeScript coverage.")
            continue
        if _needs_vitest_provider(command) and not _ensure_vitest_coverage(package):
            continue
        _prepare_report(report)
        code = run_shell(command, package)
        if code != 0:
            _warn(f"TypeScript coverage exited {code} in {package}. TypeScript coverage will score 0%.")


def _needs_vitest_provider(command: list[str]) -> bool:
    if command[:3] == ["npm", "run", "coverage"]:
        return False
    return any(Path(part).name == "vitest" for part in command)


def _python_kind(py: str, package: Path) -> str:
    if not uses_pytest(package):
        return "unittest"
    if _ensure_python_module(py, package, "pytest"):
        return "pytest"
    _warn(f"pytest is missing in {package}. Falling back to unittest.")
    return "unittest"


def _record_python_lcov(
    package: Path, code: int, data_file: Path, lcov_cmd: str | list[str]
) -> None:
    if not data_file.exists():
        if code != 0:
            _warn(f"Python coverage exited {code} in {package}. Python coverage will score 0%.")
        return
    lcov_code = run_shell(lcov_cmd, package)
    if lcov_code != 0:
        _warn(f"coverage lcov exited {lcov_code} in {package}. Python coverage will score 0%.")
    elif code != 0:
        _warn(f"Python tests exited {code} in {package}. Coverage was still recorded.")


def _cover_python(root: Path, files: list[Path]) -> None:
    for package in python_roots(root, files):
        report = _coverage_report(root, package, "python")
        py = _python_executable(package)
        if not _ensure_python_module(py, package, "coverage"):
            _warn(f"coverage is missing in {package}. Python coverage will score 0%.")
            continue
        report.parent.mkdir(parents=True, exist_ok=True)
        data_file = report.parent / ".coverage"
        report.unlink(missing_ok=True)
        data_file.unlink(missing_ok=True)
        run_cmd, lcov_cmd = python_coverage_commands(
            py, _python_kind(py, package), data_file, report, python_sources(package, files)
        )
        _record_python_lcov(package, run_shell(run_cmd, package), data_file, lcov_cmd)


def _cover_rust(root: Path, files: list[Path]) -> None:
    modules = rust_modules(root, files)
    if not modules:
        _warn("No Cargo.toml; skipping Rust coverage.")
        return
    kind = _rust_kind()
    if kind is None:
        return
    for module in modules:
        report = _coverage_report(root, module, "rust")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.unlink(missing_ok=True)
        code = run_shell(rust_coverage_command(kind, report), module)
        if code != 0:
            _warn(f"Rust coverage exited {code} in {module}. Rust coverage will score 0%.")


_DOTNET_PROJECTS = (".fsproj", ".csproj", ".vbproj")
_TEST_SDK = "Microsoft.NET.Test.Sdk"


def dotnet_test_projects(root: Path) -> list[Path]:
    """Project files that reference Microsoft.NET.Test.Sdk, which ships the coverage collector."""

    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name for name in dirnames if name not in SKIP_DIRS and name not in DOTNET_BUILD_DIRS
        ]
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix in _DOTNET_PROJECTS and _TEST_SDK in path.read_text(
                encoding="utf-8", errors="replace"
            ):
                found.append(path)
    return sorted(found)


def dotnet_coverage_command(project: Path, results: Path) -> list[str]:
    return [
        "dotnet",
        "test",
        str(project),
        "--collect:Code Coverage;Format=cobertura",
        "--results-directory",
        str(results),
    ]


def _dotnet_results_dir(coverage: Path, root: Path, project: Path) -> Path:
    slug = project.relative_to(root).with_suffix("").as_posix().replace("/", "__")
    return coverage / slug


def _cover_fsharp(root: Path) -> None:
    """Run each .NET test project; old reports go first, so a skipped run scores 0%."""

    coverage = root / "target" / "coverage" / "fsharp"
    _clean_dir(coverage)
    if not shutil.which("dotnet"):
        _warn("dotnet is not installed. F# coverage will score 0%.")
        return
    projects = dotnet_test_projects(root)
    if not projects:
        _warn("No .NET test project references Microsoft.NET.Test.Sdk; skipping F# coverage.")
        return
    for project in projects:
        results = _dotnet_results_dir(coverage, root, project)
        results.mkdir(parents=True, exist_ok=True)
        code = run_shell(dotnet_coverage_command(project, results), project.parent)
        if code == 0:
            continue
        if any(results.rglob("*.cobertura.xml")):
            _warn(f"F# tests exited {code} in {project}. Coverage was still recorded.")
        else:
            _warn(f"F# coverage exited {code} in {project}. F# coverage will score 0%.")


_GRADLE_SETTINGS = ("settings.gradle.kts", "settings.gradle")
_GRADLE_BUILDS = ("build.gradle.kts", "build.gradle")
_KOVER_NAMES = ("org.jetbrains.kotlinx.kover", "kotlinx.kover")
_KOVER_REPORTS = (  # must match the Kover globs coverage._merge_jacoco reads
    "build/reports/kover/report.xml",
    "*/build/reports/kover/report.xml",
    "*/*/build/reports/kover/report.xml",
)
_KOVER_LINES = """\
  root build file:  plugins { id("org.jetbrains.kotlinx.kover") version "0.9.10" }
                    dependencies { kover(project(":<module>")) }  (one per module)
  each module:      plugins { id("org.jetbrains.kotlinx.kover") }"""


def _gradle_roots(root: Path, files: list[Path]) -> list[Path]:
    """The Gradle builds that hold the Kotlin files, by their settings file."""

    found: set[Path] = set()
    root = root.resolve()
    for file in files:
        if Path(file).suffix != ".kt":
            continue
        for marker in _GRADLE_SETTINGS:
            build = nearest_marker(Path(file), marker, root)
            if build is not None:
                found.add(build.resolve())
                break
    return sorted(found)


def _applies_kover(build: Path) -> bool:
    for name in _GRADLE_BUILDS:
        path = build / name
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            return any(kover in text for kover in _KOVER_NAMES)
    return False


def _gradle_command(build: Path) -> list[str] | None:
    wrapper = build / "gradlew"
    if wrapper.is_file():
        return [str(wrapper), ":koverXmlReport"]
    if shutil.which("gradle"):
        return ["gradle", ":koverXmlReport"]
    return None


def _remove_kover_reports(root: Path) -> None:
    """The root and one and two levels down, where the loader reads them."""

    for pattern in _KOVER_REPORTS:
        for report in root.glob(pattern):
            report.unlink(missing_ok=True)


def _cover_kotlin(root: Path, files: list[Path]) -> None:
    """Run Kover's merged report in each Gradle root.

    Every Kover report the loader reads goes first, so a skipped or failed run
    scores 0% instead of scoring from a stale module report.
    """

    _remove_kover_reports(root)
    builds = _gradle_roots(root, files)
    if not builds:
        _warn("No settings.gradle.kts or settings.gradle; skipping Kotlin coverage.")
        return
    for build in builds:
        if not _applies_kover(build):
            _warn(
                f"The Kover plugin is not applied in {build}. Kotlin coverage will score 0%. "
                f"Add it to the root build file and to each module:\n{_KOVER_LINES}"
            )
            continue
        command = _gradle_command(build)
        if command is None:
            _warn(f"No gradlew in {build} and gradle is not installed. Kotlin coverage will score 0%.")
            continue
        code = run_shell(command, build)
        if code != 0:
            _warn(f"Kotlin coverage exited {code} in {build}. Kotlin coverage will score 0%.")


def _cover_swift(root: Path) -> None:
    """crapper never starts a Swift test run; without a command Swift scores 0%."""

    swift_coverage.remove_lcov(root)
    _warn(
        "Swift coverage needs --coverage-command with an Xcode or swift test command that "
        f"leaves its coverage in {root / swift_coverage.COVERAGE_DIR}. "
        "Swift coverage will score 0%. For example, for an Xcode project:\n"
        f"  crapper --coverage-command '{swift_coverage.XCODE_COMMAND}'\n"
        "or for a Swift package:\n"
        f"  crapper --coverage-command '{swift_coverage.PACKAGE_COMMAND}'"
    )


def _after_command(root: Path, files: list[Path], code: int) -> None:
    """Convert Swift coverage after the command; a failed one leaves no Swift LCOV."""

    if "swift" not in _languages_in(files):
        return
    if code == 0:
        swift_coverage.convert(root, files)
    else:
        swift_coverage.remove_lcov(root)


def run_coverage(root: Path, files: list[Path], command: str | None) -> int:
    """Generate coverage reports for the languages present in `files`.

    Returns the custom command's status. A non-zero status means the caller
    must not read reports already on disk. Per-language runs return 0; a
    failed tool is reported and that language scores 0% when it wrote nothing.
    """

    root = root.resolve()
    if command:
        code = run_shell(command, root)
        _after_command(root, files, code)
        if code != 0:
            _warn(
                f"Coverage command exited {code}. "
                "Reports already on disk will not be read."
            )
        return code

    languages = _languages_in(files)
    if "clojure" in languages:
        _cover_clojure(root)
    if "java" in languages:
        _cover_java(root, files)
    if "go" in languages:
        _cover_go(root, files)
    if "typescript" in languages:
        _cover_typescript(root, files)
    if "python" in languages:
        _cover_python(root, files)
    if "rust" in languages:
        _cover_rust(root, files)
    if "fsharp" in languages:
        _cover_fsharp(root)
    if "kotlin" in languages:
        _cover_kotlin(root, files)
    if "swift" in languages:
        _cover_swift(root)
    return 0
