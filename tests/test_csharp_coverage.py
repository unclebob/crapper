import pytest

from crapper.coverage import CoverageBundle, load_bundle
from crapper.cobertura import parse_cobertura
from crapper.model import Function


def function(path="src/Box.cs"):
    return Function("Read", "Demo.Box", 3, 10, 13, path, "csharp")


def report(lines, filename="src/Box.cs", sources=""):
    return f'<coverage>{sources}<packages><package><classes><class filename="{filename}"><lines>{lines}</lines></class></classes></package></packages></coverage>'


def test_reads_coverlet_lines_and_prefers_branch_counts():
    parsed = parse_cobertura(report('<line number="10" hits="1"/><line number="11" hits="1" branch="true" condition-coverage="50% (1/2)"/><line number="12" hits="0"/>'))
    assert parsed["src/Box.cs"][10] == (1, 1)
    assert parsed["src/Box.cs"].branches[11] == (1, 2)
    assert CoverageBundle(cobertura=parsed).percent_for(function()) == 50.0


def test_line_fallback_missing_source_and_uncovered_method():
    parsed = parse_cobertura(report('<line number="10" hits="1"/><line number="11" hits="0"/>'))
    bundle = CoverageBundle(cobertura=parsed)
    assert bundle.percent_for(function()) == 50.0
    assert bundle.percent_for(function("missing.cs")) is None
    assert bundle.percent_for(Function("Other", "Demo.Box", 1, 20, 23, "src/Box.cs", "csharp")) == 0.0


def test_windows_paths_and_source_roots_map_to_the_right_source():
    parsed = parse_cobertura(report('<line number="10" hits="1"/>', "Box.cs", '<sources><source>C:\\project\\src</source></sources>'))
    bundle = CoverageBundle(cobertura=parsed)
    bundle.bind_sources(["src/Box.cs", "other/Box.cs"])
    assert bundle.percent_for(function()) == 100.0
    assert bundle.percent_for(function("other/Box.cs")) is None


def test_does_not_double_count_method_and_class_line_tables():
    text = report('<line number="10" hits="0"/>').replace('<lines>', '<methods><method><lines><line number="10" hits="1"/></lines></method></methods><lines>', 1)
    assert parse_cobertura(text)["src/Box.cs"][10] == (0, 1)


def test_unions_hits_from_multiple_classes_in_one_source_file():
    text = report('<line number="10" hits="0"/>').replace('</classes>', '<class filename="src/Box.cs"><lines><line number="10" hits="1"/></lines></class></classes>')
    assert parse_cobertura(text)["src/Box.cs"][10] == (1, 1)


def test_loads_dotnet_coverage_and_coverlet_results(tmp_path):
    for name, hit in (("target/coverage/csharp/unit/coverage.cobertura.xml", 1), ("TestResults/run/coverage.cobertura.xml", 0)):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report(f'<line number="10" hits="{hit}"/>'), encoding="utf-8")
    assert load_bundle(tmp_path).percent_for(function()) == 100.0


@pytest.mark.parametrize("line", ['<line number="-1" hits="1"/>', '<line number="0" hits="1"/>', '<line number="10" hits="-1"/>', '<line number="10" hits="bad"/>', '<line number="10" hits="1" condition-coverage="invalid"/>', '<line number="10" hits="1" condition-coverage="50% (3/2)"/>', '<line number="10" hits="0" condition-coverage="0% (0/0)"/>'])
def test_invalid_counts_do_not_turn_into_green_coverage(line):
    with pytest.raises(ValueError):
        parse_cobertura(report(line))


def test_rejects_non_cobertura_and_xml_entities():
    for xml in ('<not-coverage/>', '<!DOCTYPE coverage [<!ENTITY x "value">]><coverage/>'):
        with pytest.raises(ValueError):
            parse_cobertura(xml)


@pytest.mark.parametrize("name", ["/project/src/Box.cs", "C:\\project\\src\\Box.cs"])
def test_absolute_filename_is_not_prefixed_with_sources(name):
    parsed = parse_cobertura(report('<line number="10" hits="0"/>', name, '<sources><source>/other</source></sources>'))
    assert list(parsed) == [name.replace('\\', '/')]


def test_empty_sources_are_ignored_and_missing_filename_is_rejected():
    parsed = parse_cobertura(report('<line number="10" hits="0"/>', sources='<sources><source/><source> </source></sources>'))
    assert list(parsed) == ["src/Box.cs"]
    with pytest.raises(ValueError, match="filename"):
        parse_cobertura(report('', filename=''))


@pytest.mark.parametrize("counts, expected", [("0% (0/1)", (0, 1)), ("100% (1/1)", (1, 1))])
def test_single_branch_boundaries_are_valid(counts, expected):
    parsed = parse_cobertura(report(f'<line number="10" hits="0" condition-coverage="{counts}"/>'))
    assert parsed["src/Box.cs"].branches[10] == expected


def test_merging_does_not_invent_line_or_branch_hits():
    from crapper.cobertura import merge_record
    from crapper.coverage import FileCoverage

    incoming = parse_cobertura(report('<line number="10" hits="0" condition-coverage="0% (0/2)"/>'))["src/Box.cs"]
    target = FileCoverage()
    merge_record(target, incoming)
    assert dict(target) == {10: (0, 1)} and target.branches == {10: (0, 2)}
    incoming = parse_cobertura(report('<line number="10" hits="1" condition-coverage="50% (1/2)"/>'))["src/Box.cs"]
    merge_record(target, incoming)
    merge_record(target, incoming)
    assert dict(target) == {10: (1, 1)} and target.branches == {10: (1, 2)}


@pytest.mark.parametrize("first,second,expected", [(0, 0, 0), (1, 0, 1), (0, 1, 1)])
def test_repeated_class_lines_union_hits_in_either_order(first, second, expected):
    def row(hits):
        return f'<class filename="src/Box.cs"><lines><line number="10" hits="{hits}"/></lines></class>'
    text = '<coverage><packages><package><classes>' + row(first) + row(second) + '</classes></package></packages></coverage>'
    assert parse_cobertura(text)["src/Box.cs"][10] == (expected, 1)


def test_a_later_run_cannot_erase_a_larger_branch_denominator():
    from crapper.cobertura import merge_record

    first = parse_cobertura(report('<line number="10" hits="0" condition-coverage="0% (0/4)"/>'))["src/Box.cs"]
    second = parse_cobertura(report('<line number="10" hits="0" condition-coverage="0% (0/2)"/>'))["src/Box.cs"]
    merge_record(first, second)
    assert first.branches == {10: (0, 4)}
    text = report('<line number="10" hits="0" condition-coverage="0% (0/4)"/><line number="10" hits="0" condition-coverage="0% (0/2)"/>')
    assert parse_cobertura(text)["src/Box.cs"].branches == {10: (0, 4)}
