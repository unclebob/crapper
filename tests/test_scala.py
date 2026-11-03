import pytest

from crapper.languages.scala import functions_in_source

SCORE = """
object Sample {
  def score(a: Boolean, b: Boolean, xs: List[Int]): Int = {
    for (x <- xs if x > 0) println(x)
    while (a) {}
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
    # 1, for, its guard, while, if, &&, ||, else if, three cases, a case guard, a catch case.
    assert _scored(SCORE) == [("score", 13)]


def test_lambdas_and_local_defs_stay_inside_the_method_and_anonymous_classes_are_skipped():
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


def test_operator_defs_are_entries_named_by_their_symbol():
    source = "object O {\n  def ++(o: O): O = o\n  def :=(v: Int) = v\n  def unary_! : Int = 1\n}\n"
    assert _scored(source) == [("++", 1), (":=", 1), ("unary_!", 1)]


def test_a_def_whose_name_is_missing_is_not_an_entry():
    assert _scored("object O {\n  def = 1\n}\n") == []
