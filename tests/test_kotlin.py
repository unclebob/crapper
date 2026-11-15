from pathlib import Path

import pytest

from crapper.discover import iter_source_files, language_of


def test_kt_files_are_kotlin_and_gradle_scripts_are_not():
    assert language_of("src/main/kotlin/app/Main.kt") == "kotlin"
    assert language_of("build.gradle.kts") is None
    assert language_of("settings.gradle.kts") is None


def test_kotlin_test_sources_are_not_scored(tmp_path: Path):
    main = tmp_path / "src" / "main" / "kotlin" / "App.kt"
    test = tmp_path / "src" / "test" / "kotlin" / "AppTest.kt"
    for file in (main, test):
        file.parent.mkdir(parents=True)
        file.write_text("fun f() {}\n")
    (tmp_path / "build.gradle.kts").write_text("plugins {}\n")
    assert iter_source_files([tmp_path]) == [main.resolve()]

from crapper.languages import functions_in_file


def entries(source: str, path: str = "src/main/kotlin/Sample.kt"):
    return functions_in_file("kotlin", source, path, ".")


def where(source: str, path: str = "src/main/kotlin/Sample.kt"):
    return [(f.namespace, f.name) for f in entries(source, path)]


def test_top_level_function_belongs_to_the_file_class():
    source = "package demo.core\n\nfun add(a: Int, b: Int): Int {\n    return a + b\n}\n"
    [found] = entries(source, "src/main/kotlin/demo/core/Maths.kt")
    assert (found.name, found.namespace) == ("add", "demo.core.MathsKt")
    assert (found.start_line, found.end_line) == (3, 5)
    assert (found.complexity, found.language) == (1, "kotlin")
    assert found.path == "src/main/kotlin/demo/core/Maths.kt"


def test_top_level_function_without_package_is_just_the_file_class():
    assert where("fun f() = 1\n", "Main.kt") == [("MainKt", "f")]


def test_jvm_name_annotation_renames_the_file_class():
    source = '@file:JvmName("Util")\npackage a\n\nfun f() = 1\n'
    assert where(source) == [("a.Util", "f")]


def test_file_class_capitalises_the_file_name_and_cleans_odd_characters():
    assert where("package a\nfun f() = 1\n", "x/my-file.kt") == [("a.My_fileKt", "f")]


def test_member_function_belongs_to_its_class_and_nested_classes_chain():
    source = """package a
class Outer {
    fun one() = 1
    class Inner {
        fun two() = 2
    }
}
object Single { fun three() = 3 }
interface Port {
    fun open()
    fun shut() = 4
}
"""
    assert where(source) == [
        ("a.Outer", "one"),
        ("a.Outer.Inner", "two"),
        ("a.Single", "three"),
        ("a.Port", "shut"),
    ]


def test_companion_members_belong_to_the_enclosing_class():
    source = "package a\nclass Box {\n    companion object {\n        fun make() = Box()\n    }\n}\n"
    assert where(source) == [("a.Box", "make")]


def test_extension_function_is_named_by_its_function_name():
    assert where("package a\nfun String.shout() = this\n") == [("a.SampleKt", "shout")]


def test_abstract_and_interface_functions_without_a_body_are_not_entries():
    source = "abstract class A {\n    abstract fun f()\n}\n"
    assert where(source) == []


def test_secondary_constructor_is_an_entry_named_after_the_class():
    source = "package a\nclass A() {\n    constructor(x: Int) : this() {\n        println(x)\n    }\n}\n"
    assert where(source) == [("a.A", "A")]


def test_accessors_with_bodies_are_entries_on_the_same_line_or_below():
    source = """package a
class A {
    var x: Int = 0
        get() = field + 1
        set(value) {
            field = value
        }
    val y: Int get() = 2
    val z: Int = 3
}
"""
    assert where(source) == [("a.A", "x.get"), ("a.A", "x.set"), ("a.A", "y.get")]


def test_local_functions_lambdas_and_anonymous_objects_are_not_entries():
    source = """package a
fun outer() {
    fun local() {}
    val f = { fun inner() {} }
    val o = object { fun m() = 1 }
    class Local { fun n() = 1 }
}
class A {
    val g = { fun hidden() {} }
    val p = object : Runnable { override fun run() {} }
    init { fun inInit() {} }
}
"""
    assert where(source) == [("a.SampleKt", "outer")]


def cc(body: str, params: str = "a: Boolean, b: Boolean, n: Int, x: Int?") -> int:
    source = f"fun f({params}): Int {{\n{body}\n    return 0\n}}\n"
    [found] = entries(source)
    return found.complexity


def test_straight_line_code_has_complexity_one():
    assert cc("val y = 1") == 1


DECISIONS = {
    "if": ("if (a) { println() }", 2),
    "else if counts once more, plain else adds nothing": (
        "if (a) { println() } else if (b) { println() } else { println() }",
        3,
    ),
    "for": ("for (i in 1..n) { println(i) }", 2),
    "while": ("while (a) { println() }", 2),
    "do-while": ("do { println() } while (a)", 2),
    "catch": ("try { println() } catch (e: Exception) { println(e) }", 2),
    "elvis": ("val y = x ?: 0", 2),
    "and": ("val y = a && b", 2),
    "or": ("val y = a || b", 2),
    "when branch with a condition": ("when (n) { 1 -> println() }", 2),
    "if expression": ("val y = if (a) 1 else 2", 2),
}


@pytest.mark.parametrize(("body", "expected"), DECISIONS.values(), ids=DECISIONS.keys())
def test_each_decision_adds_to_complexity(body: str, expected: int):
    assert cc(body) == expected


def test_each_conditioned_when_branch_counts_and_else_does_not():
    assert cc("when (n) { 1, 2 -> println(); in 3..4 -> println(); else -> println() }") == 3


def test_when_without_subject_counts_each_conditioned_branch():
    assert cc("when { a -> println(); b -> println(); else -> println() }") == 3


def test_safe_call_is_not_a_decision():
    assert cc("val y = x?.toString()") == 1


def test_finally_and_try_alone_add_nothing():
    assert cc("try { println() } finally { println() }") == 1


def test_decisions_nest_and_chain_in_one_expression():
    assert cc("if (a && b || a) { for (i in 1..n) { if (b) { println() } } }") == 6


def test_lambda_and_local_function_decisions_count_toward_the_function():
    body = "val g = { v: Int -> if (v > 0) 1 else 2 }\nfun local() { if (a) println() }"
    assert cc(body) == 3


def test_anonymous_object_and_local_class_add_nothing():
    body = (
        "val o = object { fun m() { if (a) println() } }\n"
        "class Local { fun n() { if (b) println() } }"
    )
    assert cc(body) == 1


def test_decisions_in_a_member_function_do_not_leak_to_its_neighbours():
    source = "class A {\n    fun one(a: Boolean) { if (a) {} }\n    fun two() {}\n}\n"
    assert [(f.name, f.complexity) for f in entries(source)] == [("one", 2), ("two", 1)]


def test_accessor_and_constructor_complexity_are_their_own():
    source = """class A() {
    val p: Int get() { return if (true) 1 else 2 }
    constructor(x: Int) : this() { if (x > 0 && x < 9) {} }
}
"""
    assert [(f.name, f.complexity) for f in entries(source)] == [("p.get", 2), ("A", 3)]
