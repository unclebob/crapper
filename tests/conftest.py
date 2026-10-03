import runpy
import shutil
import sys
from pathlib import Path

import pytest

from support import FIXTURES, Crapper, Outcome, Project

collect_ignore = ["fixtures"]


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return lambda name: shutil.copytree(FIXTURES / name, tmp_path / name)


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    return tmp_path / "scratch"


@pytest.fixture
def crapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> Crapper:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FORCE_COLOR", raising=False)

    def run(*argv: str | Path) -> Outcome:
        monkeypatch.setattr(sys, "argv", ["crapper", *map(str, argv)])
        with pytest.raises(SystemExit) as exit:
            runpy.run_module("crapper", run_name="__main__")
        code = exit.value.code
        assert isinstance(code, int)
        captured = capfd.readouterr()
        return Outcome(code=code, out=captured.out, err=captured.err)

    return run
