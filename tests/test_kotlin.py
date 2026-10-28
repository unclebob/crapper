from crapper.coverage import CoverageBundle, parse_jacoco_index
from crapper.languages.kotlin import file_class, functions_in_source

SCORE = """
package demo

class Sample {
    fun score(a: Boolean, b: Boolean, values: List<Int>, name: String?): Int {
        for (value in values) {
        }
        while (a) {
        }
        do {
        } while (b)
        if (a && b || values.isEmpty()) {
        }
        val size = name?.length ?: 0
        return try {
            when (size) {
                0 -> 1
                1, 2 -> 2
                else -> 3
            }
        } catch (ex: RuntimeException) {
            4
        }
    }
}
"""

NESTED = """
package demo

class Sample {
    fun outer(a: Boolean): Int {
        val callback = { if (a) 1 else 2 }
        fun local(b: Boolean) = if (b) 1 else 0
        val runnable = object : Runnable {
            override fun run() {
                if (a) {
                }
            }
        }
        class Local {
            fun inner() = if (a) 1 else 0
        }
        return callback() + local(a)
    }
}
"""


def _rows(source: str, path: str = "src/demo/Sample.kt"):
    return [
        (function.namespace, function.name, function.complexity)
        for function in functions_in_source(source, path)
    ]


def test_counts_branches_when_entries_and_null_safe_operators():
    # for, while, do, if, &&, ||, ?., ?:, three when entries, catch.
    assert _rows(SCORE) == [("demo.Sample", "score", 13)]


def test_lambdas_and_local_functions_stay_in_the_enclosing_function():
    # The lambda's `if` and the local function's `if`; not the anonymous
    # object's or the local class's.
    assert _rows(NESTED) == [("demo.Sample", "outer", 3)]


def test_names_follow_the_classes_jacoco_reports():
    source = """
package demo.pkg

fun top(x: Int?) = x ?: 0

fun String.shout(): String = uppercase()

class Board {
    fun place(x: Int) {
        if (x > 0) return
    }

    inner class Inner {
        fun tick() {}
    }

    companion object {
        fun create() = Board()
    }

    object Named {
        fun get() = 1
    }

    abstract fun skipped()

    constructor(x: Int) {
        if (x > 0) {}
    }

    init {
        if (true) {}
    }
}

object Registry {
    fun lookup() = 1
}
"""
    functions = functions_in_source(source, "src/demo/pkg/board-utils.kt")
    assert [(f.namespace, f.name, f.jacoco_class) for f in functions] == [
        ("demo.pkg.Board_utilsKt", "top", "demo.pkg.Board_utilsKt"),
        ("demo.pkg.Board_utilsKt", "shout", "demo.pkg.Board_utilsKt"),
        ("demo.pkg.Board", "place", "demo.pkg.Board"),
        ("demo.pkg.Board.Inner", "tick", "demo.pkg.Board$Inner"),
        ("demo.pkg.Board.Companion", "create", "demo.pkg.Board$Companion"),
        ("demo.pkg.Board.Named", "get", "demo.pkg.Board$Named"),
        ("demo.pkg.Registry", "lookup", "demo.pkg.Registry"),
    ]
    assert [f.complexity for f in functions] == [2, 1, 2, 1, 1, 1, 1]
    assert functions[2].start_line == 9
    assert functions[2].end_line == 11
    assert functions[2].language == "kotlin"


def test_interface_defaults_named_companions_and_enum_entries():
    source = """
package demo

interface Shape {
    fun area(): Double = 0.0

    companion object Factory {
        fun unit() = 1
    }
}

enum class Mode {
    FAST {
        override fun speed() = 2
    },
    SLOW;

    open fun speed() = 1
}
"""
    functions = functions_in_source(source, "src/demo/Shape.kt")
    assert [(f.namespace, f.name, f.jacoco_class) for f in functions] == [
        ("demo.Shape", "area", "demo.Shape$DefaultImpls"),
        ("demo.Shape.Factory", "unit", "demo.Shape$Factory"),
        ("demo.Mode", "speed", "demo.Mode$FAST"),
        ("demo.Mode", "speed", "demo.Mode"),
    ]


def test_file_class_follows_jvm_name_and_multifile_parts():
    assert file_class("src/util.kt", "") == ("UtilKt", "UtilKt")
    assert file_class("src/9lives.kt", "") == ("_9livesKt", "_9livesKt")
    named = '@file:JvmName("Strings")\npackage demo\n'
    assert file_class("src/util.kt", named) == ("Strings", "Strings")
    multi = '@file:JvmName("Strings")\n@file:JvmMultifileClass\npackage demo\n'
    assert file_class("src/util.kt", multi) == ("Strings", "Strings__UtilKt")


def test_top_level_function_in_the_default_package():
    functions = functions_in_source("fun main() {}\n", "Main.kt")
    assert [(f.namespace, f.name, f.jacoco_class) for f in functions] == [
        ("MainKt", "main", "MainKt")
    ]


def test_a_file_with_parse_errors_warns(capsys):
    functions_in_source("package demo\n\nfun ok() {}\n", "src/Ok.kt")
    assert capsys.readouterr().err == ""
    functions_in_source("package demo\n\nclass Broken {\n    fun f( {\n}\n", "src/Broken.kt")
    assert capsys.readouterr().err == (
        "src/Broken.kt: Kotlin parse error; scores in this file may be wrong.\n"
    )


GUARDS = """
package demo

sealed interface Shape {
    data class Circle(val r: Double) : Shape
    data class Rect(val w: Double, val h: Double) : Shape
    data object Empty : Shape
}

fun label(s: Shape): String = when (s) {
    is Shape.Circle if s.r > 10.0 -> "big circle"
    is Shape.Circle -> "circle"
    is Shape.Rect if s.w == s.h -> "square"
    is Shape.Rect -> "rect"
    Shape.Empty -> "empty"
}
"""


def _complexity(source: str) -> int:
    [function] = functions_in_source(source, "src/main/kotlin/demo/Guards.kt")
    return function.complexity


def test_a_when_guard_is_a_second_decision_on_its_branch():
    [function] = functions_in_source(GUARDS, "src/main/kotlin/demo/Shapes.kt")
    assert (function.name, function.complexity) == ("label", 8)
    plain = "fun pick(x: Int) = when (x) { 1 -> 1; 2 -> 2; else -> 3 }\n"
    guarded = "fun pick(x: Int) = when (x) { 1 if x > 0 -> 1; 2 -> 2; else -> 3 }\n"
    assert _complexity(guarded) == _complexity(plain) + 1


def test_a_guard_with_and_counts_the_guard_and_the_and():
    plain = "fun pick(v: Any, a: Boolean, b: Boolean) = when (v) { is String -> 1; else -> 0 }\n"
    guarded = "fun pick(v: Any, a: Boolean, b: Boolean) = when (v) { is String if a && b -> 1; else -> 0 }\n"
    assert _complexity(guarded) == _complexity(plain) + 2


BACKTICKS = """
package okio

object `-DeprecatedOkio` {
    fun buffer(x: Int) = x + 1
}

class Plain {
    class `with space` {
        fun inside() = 2
    }
}

internal class `Outer$WithDate$DefaultImpls` {
    companion object {
        fun date() = 3
    }
}
"""


def test_backticked_type_names_follow_the_classes_jacoco_reports():
    functions = functions_in_source(BACKTICKS, "src/okio/-DeprecatedOkio.kt")
    assert [(f.namespace, f.name, f.jacoco_class) for f in functions] == [
        ("okio.-DeprecatedOkio", "buffer", "okio.-DeprecatedOkio"),
        ("okio.Plain.with space", "inside", "okio.Plain$with space"),
        (
            "okio.Outer$WithDate$DefaultImpls.Companion",
            "date",
            "okio.Outer$WithDate$DefaultImpls$Companion",
        ),
    ]


def test_a_backticked_object_joins_its_jacoco_class():
    xml = """<?xml version="1.0"?>
<report>
  <package name="okio">
    <class name="okio/-DeprecatedOkio">
      <method name="buffer" desc="(I)I" line="5">
        <counter type="INSTRUCTION" missed="1" covered="3"/>
      </method>
    </class>
  </package>
</report>
"""
    buffer = functions_in_source(BACKTICKS, "src/okio/-DeprecatedOkio.kt")[0]
    bundle = CoverageBundle(jacoco=parse_jacoco_index(xml))
    assert bundle.percent_for(buffer) == 75.0


INLINE = """
package demo

annotation class InlineOnly

inline fun bare(x: Int) = if (x > 0) 1 else 0
public inline fun visible(x: Int) = x
internal inline fun hidden(x: Int) = x
private inline fun secret(x: Int) = x
@InlineOnly inline fun annotated(x: Int) = x
inline fun <reified T> Any.isA(): Boolean = this is T
inline fun String.shout(block: (String) -> String) = block(uppercase())
inline fun outer(x: Int): Int {
    fun local(y: Int) = if (y > 0) y else 0
    return local(x)
}
fun plain(x: Int) = x

open class Base {
    open fun run(block: () -> Unit) = block()
}

class Child : Base() {
    override inline fun run(block: () -> Unit) = block()
    fun kept() = 1
}

object Holder {
    inline fun held(x: Int) = x
}

class WithCompanion {
    companion object {
        inline fun made(x: Int) = x
    }
}

@JvmInline
value class Meters(val value: Int) {
    fun double() = Meters(value * 2)
}

inline class Legacy(val value: Int) {
    fun half() = value / 2
}
"""


def test_inline_functions_are_not_scored_wherever_they_are_declared():
    assert _rows(INLINE, "src/demo/Inline.kt") == [
        ("demo.InlineKt", "plain", 1),
        ("demo.Base", "run", 1),
        ("demo.Child", "kept", 1),
        ("demo.Meters", "double", 1),
        ("demo.Legacy", "half", 1),
    ]


def test_an_inline_function_drops_out_and_its_neighbor_still_joins_jacoco():
    source = """
package demo

inline fun pick(x: Int, f: (Int) -> Int): Int { if (x > 0) return f(x); return 0 }
fun plainPick(x: Int, f: (Int) -> Int): Int { if (x > 0) return f(x); return 0 }
"""
    xml = """<report><package name="demo"><class name="demo/InlineKt">
<method name="pick" desc="(ILkotlin/jvm/functions/Function1;)I" line="4">
<counter type="INSTRUCTION" missed="9" covered="0"/><counter type="LINE" missed="2" covered="0"/></method>
<method name="plainPick" desc="(ILkotlin/jvm/functions/Function1;)I" line="5">
<counter type="INSTRUCTION" missed="0" covered="9"/><counter type="LINE" missed="0" covered="2"/></method>
</class></package></report>"""
    functions = functions_in_source(source, "src/main/kotlin/demo/Inline.kt")
    bundle = CoverageBundle(jacoco=parse_jacoco_index(xml))
    assert [(f.name, bundle.percent_for(f)) for f in functions] == [("plainPick", 100.0)]
