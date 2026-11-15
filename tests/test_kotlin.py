from pathlib import Path

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
