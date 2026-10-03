import logging
import shlex
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from shutil import which

type Argv = Sequence[str]

log = logging.getLogger(__name__)


def attempt(argv: Argv, cwd: Path) -> bool:
    log.info("+ (%s) %s", cwd, shlex.join(argv))
    if which(argv[0]) is None:
        log.warning("%s is not installed.", argv[0])
        return False
    return subprocess.run(argv, cwd=cwd, stdout=sys.stderr).returncode == 0


def run(argv: Argv, cwd: Path) -> bool:
    if not (succeeded := attempt(argv, cwd)):
        log.warning("%s failed in %s. Coverage it did not write is 0%%.", argv[0], cwd)
    return succeeded
