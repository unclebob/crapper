from crapper.languages.kotlin import functions_in_source


def entries(source, path="src/main/kotlin/demo/Board.kt"):
    return [
        (fn.namespace, fn.name, fn.jacoco_class)
        for fn in functions_in_source(source, path, "/proj")
    ]


def complexity_of(body, name="choose"):
    source = f"package demo\n\n{body}"
    found = {fn.name: fn.complexity for fn in functions_in_source(source, "Demo.kt", "/proj")}
    return found[name]


def test_top_level_type_and_companion_functions_are_entries():
    source = """
package com.demo.app

fun place(x: Int): Int = x + 1

fun String.shout(): String {
    return uppercase()
}

class Board {
    fun open() {}

    class Cell {
        fun mark() {}
    }

    object Rules {
        fun check() {}
    }

    companion object {
        fun create(): Board = Board()
    }
}

class Widget {
    companion object Factory {
        fun make() {}
    }
}

object Registry {
    fun lookup() {}
}
"""
    assert entries(source) == [
        ("com.demo.app", "place", "com.demo.app.BoardKt"),
        ("com.demo.app", "shout", "com.demo.app.BoardKt"),
        ("com.demo.app.Board", "open", "com.demo.app.Board"),
        ("com.demo.app.Board.Cell", "mark", "com.demo.app.Board$Cell"),
        ("com.demo.app.Board.Rules", "check", "com.demo.app.Board$Rules"),
        ("com.demo.app.Board.Companion", "create", "com.demo.app.Board$Companion"),
        ("com.demo.app.Widget.Factory", "make", "com.demo.app.Widget$Factory"),
        ("com.demo.app.Registry", "lookup", "com.demo.app.Registry"),
    ]


def test_file_jvm_name_and_a_lower_case_stem_name_the_top_level_class():
    named = '@file:JvmName("Utilities")\npackage demo\n\nfun run() = 1\n'
    assert entries(named) == [("demo", "run", "demo.Utilities")]
    lower = "package demo\n\nfun run() = 1\n"
    assert entries(lower, "src/main/kotlin/demo/poolFromLayout.kt") == [
        ("demo", "run", "demo.PoolFromLayoutKt")
    ]


def test_a_file_without_a_package_uses_the_file_stem():
    source = "fun run() = 1\n\nclass Board {\n    fun open() {}\n}\n"
    assert entries(source, "scripts/tools.kt") == [
        ("tools", "run", "ToolsKt"),
        ("Board", "open", "Board"),
    ]


def test_an_enum_value_with_its_own_body_is_one_more_type_level():
    source = """
package demo

enum class Shape {
    CIRCLE { override fun area() = 3.14 },
    SQUARE { override fun area(): Double { return 1.0 } },
    PLAIN;

    open fun area(): Double = 0.0
}
"""
    assert entries(source) == [
        ("demo.Shape.CIRCLE", "area", "demo.Shape$CIRCLE"),
        ("demo.Shape.SQUARE", "area", "demo.Shape$SQUARE"),
        ("demo.Shape", "area", "demo.Shape"),
    ]


def test_nested_functions_constructors_accessors_and_abstract_functions_are_not_entries():
    source = """
package demo

abstract class Shape(val size: Int) {
    constructor() : this(1)

    init {
        println(size)
    }

    val area: Int
        get() = size * size

    abstract fun draw()

    fun render() {
        fun local() {}
        val handler = { x: Int -> x }
        val runner = object : Runnable {
            override fun run() {}
        }
        listOf(1).forEach(fun(item) { println(item) })
    }
}

interface Drawable {
    fun paint()
}
"""
    assert entries(source) == [("demo.Shape", "render", "demo.Shape")]


def test_entries_carry_their_lines_and_language():
    source = "package demo\n\nfun run(): Int {\n    return 1\n}\n"
    (found,) = functions_in_source(source, "Board.kt", "/proj")
    assert (found.start_line, found.end_line, found.language) == (3, 5, "kotlin")


def test_a_function_without_decisions_is_one():
    assert complexity_of("fun choose() = 1\n") == 1


def test_each_decision_kind_adds_one():
    body = """
fun choose(a: Int?, items: List<Int>): Int {
    if (a == null) return 0
    for (item in items) {}
    while (false) {}
    do {} while (false)
    try {
        println(a)
    } catch (e: IllegalStateException) {
    }
    val b = a > 1 && a < 5
    val c = a > 9 || a < 0
    val d = items.firstOrNull() ?: 0
    val e = items.firstOrNull()?.plus(1)
    return d
}
"""
    assert complexity_of(body) == 10


def test_each_when_arm_adds_one_and_else_adds_nothing():
    body = """
fun choose(x: Int): Int = when (x) {
    1 -> 10
    2, 3 -> 20
    in 4..9 -> 30
    else -> 0
}
"""
    assert complexity_of(body) == 4


def test_local_function_lambda_and_anonymous_object_decisions_count_in_the_outer_entry():
    body = """
fun choose(items: List<Int>): Int {
    fun pick(x: Int) = if (x > 1) x else 0
    val kept = items.filter { it > 0 && it < 9 }
    val runner = object : Runnable {
        override fun run() {
            if (kept.isEmpty()) println("none")
        }
    }
    return kept.size
}
"""
    assert complexity_of(body) == 4


def test_an_annotated_function_type_does_not_hide_the_functions_after_it():
    source = """
package demo

@Composable
fun Frame(content: @Composable () -> Unit, slot: @Composable (() -> Unit)? = null) {
    if (slot != null) slot()
    content()
}

@Preview
@Composable
private fun FramePreview() {
    Frame {}
}
"""
    found = functions_in_source(source, "Frame.kt", "/proj")
    assert [(fn.name, fn.start_line, fn.complexity) for fn in found] == [
        ("Frame", 4, 2),
        ("FramePreview", 10, 1),
    ]
