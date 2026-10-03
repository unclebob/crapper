from pathlib import Path

import pytest

from crapper.viewer import restart_args


@pytest.mark.parametrize(
    ("diagrams", "expected"),
    [
        ([], ("--restart",)),
        (["demo.policy.edn"], ("--restart",)),
        (["other.edn", "demo.edn"], ("--restart", "examples/demo.edn")),
        (["b.edn", "a.edn", "a.policy.edn"], ("--restart", "examples/a.edn")),
    ],
)
def test_a_restart_reopens_the_diagram_named_after_the_project_before_any_other(
    tmp_path: Path, diagrams: list[str], expected: tuple[str, ...]
) -> None:
    root = tmp_path / "demo"
    (root / "examples").mkdir(parents=True)
    for diagram in diagrams:
        (root / "examples" / diagram).touch()
    assert restart_args(root) == expected
