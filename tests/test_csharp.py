import pytest

from crapper.discover import iter_source_files, language_of
from crapper.languages import functions_in_file
from crapper.languages.csharp import functions_in_source


def summary(source):
    return [(f.namespace, f.name, f.complexity) for f in functions_in_source(source, "src/Box.cs")]


def test_discovery_and_dispatch(tmp_path):
    source = tmp_path / "Box.cs"
    source.write_text("class Box { int Read() => 1; }", encoding="utf-8")
    assert language_of(source) == "csharp"
    assert functions_in_file("csharp", source.read_text(), "Box.cs", str(tmp_path))[0].name == "Read"
    assert iter_source_files([tmp_path]) == [source.resolve()]


def test_generated_build_trees_are_not_product_source(tmp_path):
    for name in ("src/Box.cs", "obj/Release/Generated.cs", "bin/Release/Copy.cs"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("class Box { int Read() => 1; }", encoding="utf-8")
    assert iter_source_files([tmp_path]) == [(tmp_path / "src/Box.cs").resolve()]


def test_file_scoped_namespace_nested_records_and_expression_bodies():
    assert summary("""
    namespace Demo.Tools;
    record Box(int X) {
        public int Read() => X > 0 ? X : 0;
        class Inner { public int Read() { return 1; } }
    }
    """) == [("Demo.Tools.Box", "Read", 2), ("Demo.Tools.Box.Inner", "Read", 1)]


def test_block_namespaces_compose_and_abstract_members_are_omitted():
    assert summary("""
    namespace A { namespace B { interface I { int Read(); }
    abstract class Box { public abstract int Read(); public int Tick() => 1; } } }
    """) == [("A.B.Box", "Tick", 1)]


def test_loops_boolean_operators_catches_and_ternaries():
    assert summary("""
    class Box { int Score(bool a, bool b, int[] values) {
        for (int i=0; i<values.Length; i++) { }
        foreach (int n in values) { }
        while(a) { break; }
        do { } while(b);
        if (a && b || values.Length > 0) { }
        try { return a ? 1 : 0; } catch (System.Exception) { return 2; }
    } }
    """) == [("Box", "Score", 10)]


def test_switch_arms_patterns_null_decisions_and_exception_filters():
    assert summary("""
    class Box { int Score(object input, int? x) {
        x ??= 1;
        int value = x ?? 0;
        string text = input?.ToString();
        try { return input switch { int n when n > 0 => 1, null => 2, _ => 0 }; }
        catch (System.Exception e) when (e.Message.Length > 0) { return 0; }
    } }
    """) == [("Box", "Score", 9)]


def test_switch_default_is_not_an_extra_path():
    assert summary("class Box { int Score(int n) { switch(n) { case 1: case 2: return 1; default: return 0; } } }") == [("Box", "Score", 3)]


def test_properties_accessors_constructors_and_operators():
    found = summary("""
    struct Box {
        Box(int x) { if(x > 0) {} }
        int Read => true ? 1 : 0;
        int Value { get { return 1; } set { if(value > 0) {} } }
        int Auto { get; set; }
        public static Box operator +(Box a, Box b) => a;
        public static explicit operator int(Box a) => 0;
    }
    """)
    assert found == [("Box", ".ctor", 2), ("Box", "get_Read", 2), ("Box", "get_Value", 1),
                     ("Box", "set_Value", 2), ("Box", "operator +", 1), ("Box", "operator int", 1)]


def test_local_functions_and_lambdas_own_their_decisions():
    found = functions_in_source("""
    class Box { int Read(int n) {
        int Local(int x) { if(x > 0) return x; return 0; }
        System.Func<int,int> map = x => x > 0 ? x : 0;
        return Local(n);
    } }
    """, "src/Box.cs")
    assert [(f.name, f.complexity) for f in found[:2]] == [("Read", 1), ("Read.Local", 2)]
    assert len(found) == 3 and found[2].name.startswith("Read.lambda@") and found[2].complexity == 2
    assert all(f.start_byte >= 0 and f.end_byte > f.start_byte for f in found)


def test_comments_raw_strings_and_attributes_do_not_add_decisions():
    assert summary('''
    class Box {
        [System.Obsolete("if && || ?")]
        string Read() {
            // if && || ?? switch
            return """if && || ?? switch""";
        }
    }
    ''') == [("Box", "Read", 1)]


def test_overloads_retain_distinct_source_spans():
    found = functions_in_source("class Box { int Read() => 1; int Read(int n) => n; }", "Box.cs")
    assert len(found) == 2 and found[0].start_byte != found[1].start_byte


def test_malformed_source_is_not_silently_scored():
    with pytest.raises(ValueError, match="C# syntax"):
        functions_in_source("class {", "Box.cs")


def test_top_level_statements_and_local_functions_have_distinct_owners():
    found = summary("int Read(int n) => n > 0 ? n : 0; var n = Read(1); if(n > 0) System.Console.WriteLine(n);")
    assert found == [("Program", "<Main>$", 2), ("Program", "Read", 2)]


def test_pattern_combinators_are_decisions():
    assert summary("class Box { bool Read(int n) => n is > 0 and < 10 or 42; }") == [("Box", "Read", 3)]


def test_static_constructor_destructor_indexer_and_anonymous_method():
    found = summary("""
    class Box {
        static Box() { }
        ~Box() { }
        int this[int n] => n > 0 ? n : 0;
        System.Func<int> Read() => delegate { return 1; };
    }
    """)
    assert found[:4] == [("Box", ".cctor", 1), ("Box", ".dtor", 1), ("Box", "get_this[]", 2), ("Box", "Read", 1)]
    assert found[4] == ("Box", "Read.lambda@6:35", 1)


def test_utf8_byte_spans_and_one_based_lines_are_exact():
    source = '// \u03c0\nnamespace Demo;\nclass Box {\n    int Read() => 1;\n}\n'
    found = functions_in_source(source, "Box.cs")[0]
    encoded = source.encode("utf-8")
    assert (found.start_line, found.end_line) == (4, 4)
    assert (found.start_byte, found.end_byte) == (encoded.index(b"int Read"), encoded.index(b"1;") + 2)


def test_top_level_entry_covers_first_through_last_statement_only():
    source = 'using System;\nint Read(int n) => n;\nvar n = Read(1);\nConsole.WriteLine(n);\nclass Box {}\n'
    entry = functions_in_source(source, "Program.cs")[0]
    assert entry.name == "<Main>$" and (entry.start_line, entry.end_line) == (2, 4)
    assert entry.start_byte == source.index("int Read")
    assert entry.end_byte == source.index("Console.WriteLine(n);") + len("Console.WriteLine(n);")


def test_lambda_identity_retains_its_line_and_column():
    found = functions_in_source('class Box { System.Func<int,int> Read() => x => x; }', 'Box.cs')
    assert found[1].name == "Read.lambda@1:43"


def test_constructor_initializer_is_executable_code():
    assert summary("class Box { Box(int n) : this(n > 0 ? n : 0, true) {} }") == [("Box", ".ctor", 2)]


def test_checked_operators_keep_their_identity():
    assert summary("class Box { public static Box operator checked +(Box a, Box b) => a; public static explicit operator checked int(Box a) => 0; }") == [("Box", "operator checked +", 1), ("Box", "operator checked int", 1)]
