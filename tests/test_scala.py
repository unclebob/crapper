import pytest

from crapper.languages.scala import functions_in_source

SCORE = """
object Sample {
  def score(a: Boolean, b: Boolean, xs: List[Int]): Int = {
    for (x <- xs if x > 0) println(x)
    while (a) {}
    do {} while (b)
    if (a && b || xs.nonEmpty) 1 else if (b) 2 else 0
    xs match {
      case Nil => 0
      case h :: _ if h > 1 => 1
      case _ => 2
    }
    try 1 catch { case e: RuntimeException => 2 }
  }
}
"""

NESTED = """
object Sample {
  def outer(a: Boolean, xs: List[Int]): Int = {
    val f = (y: Int) => if (y > 0) y else 0
    def local(z: Int) = if (z > 0) 1 else 0
    val r = new Runnable { def run(): Unit = if (a) () }
    class L(x: Int = if (a) 1 else 2) extends Base(if (a) 3 else 4)
    xs.map(x => if (x > 0) x else 0).sum
  }
}
"""

NAMES = """
package a.b

object Board {
  def place(x: Int): Int = if (x > 0 && ready) 1 else 0
  class Inner { def tick(): Int = 1 }
  object Companion { def tack: Int = 2 }
}
class Outer(x: Int) {
  def this() = this(0)
}
trait T { def abstractOne: Int; def concrete = 1 }
enum Color { case Red, Green; def hue = this match { case Red => 1; case Green => 2 } }
extension (s: String) def shout = s.toUpperCase
def topLevel(x: Int) = x + 1
package object c { def inPkgObj = 1 }
package d { class In { def m = 1 } }
given Ordering[Int] = new Ordering[Int] { def compare(a: Int, b: Int) = a - b }
"""


def _scored(source):
    return [(f.name, f.complexity) for f in functions_in_source(source, "Sample.scala")]


def test_counts_each_decision_once():
    # 1, for, its guard, while, do while, if, &&, ||, else if, three cases, a case guard, a catch case.
    assert _scored(SCORE) == [("score", 14)]


def test_lambdas_and_local_defs_stay_inside_the_method_and_anonymous_and_local_classes_are_skipped():
    assert _scored(NESTED) == [("outer", 4)]


def test_names_the_enclosing_type_for_uml_viewer_and_skips_what_has_no_body_of_its_own():
    found = functions_in_source(NAMES, "src/main/scala/a/b/Board.scala")
    assert [(f.namespace, f.name, f.complexity) for f in found] == [
        ("a.b.Board", "place", 3),
        ("a.b.Board.Inner", "tick", 1),
        ("a.b.Board.Companion", "tack", 1),
        ("a.b.T", "concrete", 1),
        ("a.b.Color", "hue", 3),
        ("a.b", "shout", 1),
        ("a.b", "topLevel", 1),
        ("a.b.c", "inPkgObj", 1),
        ("a.b.d.In", "m", 1),
    ]
    assert found[0].language == "scala"
    assert found[0].path == "src/main/scala/a/b/Board.scala"
    assert found[0].jacoco_class is None
    assert (found[0].start_line, found[0].end_line) == (5, 5)


def test_chained_package_clauses_join_and_no_package_leaves_the_type_alone():
    chained = "package a\npackage b\nobject O { def f = 1 }\n"
    assert [f.namespace for f in functions_in_source(chained, "O.scala")] == ["a.b.O"]
    bare = "object O { def f = 1 }\ndef g = 2\n"
    assert [f.namespace for f in functions_in_source(bare, "O.scala")] == ["O", ""]


def test_a_brace_less_catch_case_is_a_decision():
    assert _scored("object O { def f = try 1 catch case e: E => 2 }\n") == [("f", 2)]


def test_a_def_in_a_given_body_belongs_to_the_class_scalac_names_for_that_given():
    source = """package p
object O {
  given Ordering[Int] with { def compare(a: Int, b: Int) = 0 }
  given named: Ordering[Long] with { def compare(a: Long, b: Long) = 0 }
  given Map[String, List[Int]] with
    def size = 0
  given Ordering[Char] = Ordering.Char
  given scala.math.Ordering[Short] with { def compare(a: Short, b: Short) = 0 }
}
"""
    assert [(f.namespace, f.name) for f in functions_in_source(source, "O.scala")] == [
        ("p.O.given_Ordering_Int", "compare"),
        ("p.O.named", "compare"),
        ("p.O.given_Map_String_List", "size"),
        ("p.O.given_Ordering_Short", "compare"),
    ]


def test_keywords_in_comments_and_strings_are_not_decisions():
    source = '''
    object Sample {
      def stable: Int = {
        val text = "if && || case catch while for"
        // if && || case catch while for
        /* if && || case catch while for */
        1
      }
    }
    '''
    assert _scored(source) == [("stable", 1)]


def _ranges(source):
    return [(f.name, f.start_line, f.end_line) for f in functions_in_source(source, "O.scala")]


def test_a_def_ends_on_its_last_body_line_not_in_the_next_lines_indentation():
    indented = "object O:\n  def w =\n    while i < 3 do i += 1\n  def m = 1\n"
    assert _ranges(indented) == [("w", 2, 3), ("m", 4, 4)]
    braced = "object O {\n  def w = {\n    1\n  }\n  def m = 1\n}\n"
    assert _ranges(braced) == [("w", 2, 4), ("m", 5, 5)]
    commented = "object O:\n  def w =\n    1 // note\n  // about m\n  /* and\n  more */\n  def m = 1\n"
    assert _ranges(commented) == [("w", 2, 3), ("m", 7, 7)]
    marked = "object O:\n  def w =\n    1\n  end w\n  def m = 1\n"
    assert _ranges(marked) == [("w", 2, 4), ("m", 5, 5)]
    top_level = "def w =\n  1\n\ndef m = 1\n"
    assert _ranges(top_level) == [("w", 1, 2), ("m", 4, 4)]


def test_operator_defs_are_entries_named_by_their_symbol():
    source = "object O {\n  def ++(o: O): O = o\n  def :=(v: Int) = v\n  def unary_! : Int = 1\n}\n"
    assert _scored(source) == [("++", 1), (":=", 1), ("unary_!", 1)]


def test_a_def_whose_name_is_missing_is_not_an_entry():
    assert _scored("object O {\n  def = 1\n}\n") == []


def test_a_def_with_only_type_parameters_or_a_type_is_not_an_entry():
    assert _scored("object O {\n  def [T] = 1\n  def : Int = 1\n}\n") == []


def test_a_def_in_a_lambda_outside_any_method_is_not_an_entry():
    source = "object O {\n  val h = (x: Int) => { def inner = 1; inner }\n}\n"
    assert _scored(source) == []


def test_an_infix_with_an_alphanumeric_operator_is_not_a_decision():
    source = "object O {\n  def span(a: Int, b: Int) = (1 to (a max b)).sum\n}\n"
    assert _scored(source) == [("span", 1)]


def test_each_case_of_a_partial_function_literal_is_a_decision():
    # 1, one case, its guard, the wildcard case.
    source = "object O {\n  def pick(xs: List[Option[Int]]) = xs.collect { case Some(x) if x > 0 => x; case _ => 0 }\n}\n"
    assert _scored(source) == [("pick", 4)]
