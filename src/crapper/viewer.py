import subprocess
from datetime import datetime
from itertools import islice
from pathlib import Path

LOG = "uml-viewer-log.txt"

_DEPS = (
    "{:deps {io.github.unclebob/uml-viewer"
    ' {:git/sha "650abbcde6fd3f5f25d3ba5fe59191036dd312b3"}'
    ' quil/quil {:mvn/version "4.3.1563"}}}'
)
_MAIN = "uml-viewer.main.uml-viewer"
_POLICY = ".policy.edn"


def restart_args(root: Path) -> tuple[str, ...]:
    examples = root / "examples"
    candidates = (examples / f"{root.name}.edn", *sorted(examples.glob("*.edn")))
    diagrams = (
        path.relative_to(root).as_posix()
        for path in candidates
        if path.is_file() and not path.name.endswith(_POLICY)
    )
    return ("--restart", *islice(diagrams, 1))


def launch(root: Path, args: tuple[str, ...]) -> int:
    with (root / LOG).open("a", encoding="utf-8") as log:
        header = " ".join(("starting uml-viewer", *args))
        log.write(f"----- {datetime.now():%Y-%m-%d %H:%M:%S} {header}\n")
        log.flush()
        return subprocess.Popen(
            ["clojure", "-Sdeps", _DEPS, "-M", "-m", _MAIN, *args],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        ).pid
