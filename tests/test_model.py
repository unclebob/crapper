import pytest

from crapper.model import Function, Scored, Span
from crapper.render import snapshot


def entry(complexity: int, coverage: float) -> Scored:
    function = Function(
        name="layout",
        namespace="uml-viewer.layout",
        complexity=complexity,
        span=Span(start=1, end=1),
    )
    return Scored(function=function, coverage=coverage)


@pytest.mark.parametrize(
    ("complexity", "coverage", "crap"),
    [(5, 100.0, 5.0), (5, 0.0, 30.0), (1, 100.0, 1.0), (8, 45.0, 18.648)],
)
def test_crap_is_complexity_squared_times_uncovered_cubed_plus_complexity(
    complexity: int, coverage: float, crap: float
) -> None:
    assert entry(complexity, coverage).crap == pytest.approx(crap)


def test_a_span_cannot_end_before_it_starts() -> None:
    with pytest.raises(ValueError, match="is before start"):
        Span(start=2, end=1)


def test_the_snapshot_uses_the_keys_uml_viewer_reads() -> None:
    assert snapshot([entry(8, 100.0)]).splitlines() == [
        "{:entries [",
        ' {:name "layout" :namespace "uml-viewer.layout" :complexity 8 :coverage 100.0 :crap 8.0}',
        "]}",
    ]


def test_the_snapshot_of_no_entries_is_an_empty_vector() -> None:
    assert "".join(snapshot([]).split()) == "{:entries[]}"
