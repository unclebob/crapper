import logging
import sys
from pathlib import Path
from subprocess import CalledProcessError
from textwrap import fill
from typing import Annotated

from cyclopts import App, CycloptsError, Group, Parameter
from cyclopts.types import ExistingDirectory, NonNegativeFloat
from cyclopts.validators import MutuallyExclusive
from rich.console import Console

from crapper import render, viewer
from crapper.analyze import analyze
from crapper.coverage.measure import Command, Mode, measure
from crapper.decode import Malformed
from crapper.languages import LANGUAGES
from crapper.model import Scored
from crapper.selection import SKIP_DIRS, Outside, select

_LANGUAGES = "\n".join(
    f"  {language.name:<12}{' '.join(language.extensions)}" for language in LANGUAGES
)
_SKIPPED = fill(
    ", ".join(sorted(SKIP_DIRS)), initial_indent="  ", subsequent_indent="  "
)
HELP = f"""\
Score each source file with CRAP = CC² × (1 − coverage)³ + CC, write
.metrics/crap.edn for uml-viewer and print a report sorted worst first.

Languages:
{_LANGUAGES}

With no targets, source files under the project root are analyzed. Each
language's test files are skipped, as are directories named:
{_SKIPPED}

Functions without coverage data score 0%. With --coverage none they score N/A.
"""


type Flag = Annotated[bool, Parameter(negative=())]

log = logging.getLogger(__name__)

_COVERAGE = Group("Coverage", validator=MutuallyExclusive())

app = App(name="crapper", help=HELP, help_format="plaintext")


@app.default
def crap(
    *targets: Annotated[
        str,
        Parameter(
            help="File or directory to analyze (test files included when named), "
            "or text a source path must contain."
        ),
    ],
    root: Annotated[
        ExistingDirectory, Parameter(help="Project root. Metrics are written here.")
    ] = Path(),
    source_root: Annotated[
        tuple[Path, ...],
        Parameter(
            name=["--source-root", "-s"],
            negative=(),
            consume_multiple=False,
            help="Walk this tree, relative to the root, instead of the root.",
        ),
    ] = (),
    changed: Annotated[
        Flag, Parameter(help="Analyze added and modified source files from git status.")
    ] = False,
    coverage: Annotated[
        Mode,
        Parameter(
            group=_COVERAGE,
            help="Run the per-language coverage tools, read existing reports, "
            "or skip coverage.",
        ),
    ] = "run",
    coverage_command: Annotated[
        str | None,
        Parameter(
            group=_COVERAGE,
            help="Run this shell command instead of the per-language coverage "
            "tools, then read the reports it wrote.",
        ),
    ] = None,
    threshold: Annotated[
        NonNegativeFloat | None,
        Parameter(help="Exit 2 when the worst CRAP score is above this."),
    ] = None,
) -> int:
    project = root.resolve()
    projects = select(project, targets, source_root, changed=changed)
    if not projects:
        print("No source files to analyze.")
        return 0
    plan = Command(shell=coverage_command) if coverage_command else coverage
    entries = analyze(projects, measure(project, projects, plan))
    snapshot = project / render.SNAPSHOT
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(render.snapshot(entries), encoding="utf-8")
    languages = dict.fromkeys(owned.language.name for owned in projects)
    Console(width=None if sys.stdout.isatty() else render.UNBOUNDED).print(
        render.table(entries, languages)
    )
    log.info("Wrote %s", snapshot)
    scores = (entry.crap for entry in entries if isinstance(entry, Scored))
    worst = max(scores, default=0.0)
    if threshold is None or worst <= threshold:
        return 0
    log.warning("CRAP threshold exceeded: %.1f > %.1f", worst, threshold)
    return 2


@app.command(help="Open uml-viewer on the project in a detached JVM.")
def uml(
    root: Annotated[ExistingDirectory, Parameter(help="Project root.")] = Path(),
    restart: Annotated[
        Flag,
        Parameter(
            help="Companion only: start a new JVM that restores the last view "
            "instead of opening a fresh window."
        ),
    ] = False,
) -> None:
    project = root.resolve()
    pid = viewer.launch(project, viewer.restart_args(project) if restart else ())
    print(f"UML viewer started (pid {pid}). Log: {project / viewer.LOG}")


def main() -> None:
    logging.basicConfig(
        format="%(message)s", level=logging.INFO, stream=sys.stderr, force=True
    )
    try:
        app(exit_on_error=False)
    except CycloptsError:
        raise SystemExit(1) from None
    except CalledProcessError as failed:
        log.error("%s", failed)
        raise SystemExit(failed.returncode) from None
    except (Malformed, Outside) as invalid:
        log.error("%s", invalid)
        raise SystemExit(1) from None
