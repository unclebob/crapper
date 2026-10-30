from crapper.languages.php import functions_in_source


def _rows(functions):
    return [(fn.namespace, fn.name, fn.complexity) for fn in functions]


def test_each_decision_counts_once():
    source = """<?php
namespace App\\Survey;

final class Board
{
    public function score($a, $b, array $values)
    {
        if ($a) {
        } elseif ($b) {
        } else if ($a && $b) {
        } else {
        }
        for ($i = 0; $i < 3; $i++) {
        }
        foreach ($values as $value) {
        }
        while ($a || $b) {
        }
        do {
        } while ($a and $b);
        try {
            $a = $b ? 1 : 2;
            $b = $a ?: 3;
        } catch (\\RuntimeException $e) {
        }
        switch ($a) {
            case 1:
                break;
            default:
                break;
        }
        $c = match ($a) {
            1, 2 => 'low',
            default => 'high',
        };
        return $a ?? $b?->c ?? $b?->d() ?? ($a or $b) ?? !$a;
    }
}
"""
    assert _rows(functions_in_source(source, "app/Survey/Board.php", "/proj")) == [
        ("App.Survey.Board", "score", 25),
    ]


def test_methods_functions_and_closures():
    source = """<?php
namespace App\\Survey;

interface Shape { public function area(): float; }

abstract class Base
{
    abstract protected function hook(): void;

    public function __construct(private int $y)
    {
        if ($y) {
        }
    }
}

trait Greets
{
    public function hi($loud) { return $loud ? 'HI' : 'hi'; }
}

enum Suit: string
{
    case Hearts = 'H';

    public function color(): string
    {
        return match ($this) { self::Hearts => 'Red', default => 'Black' };
    }
}

function helper($items)
{
    $keep = fn($x) => $x > 0 && $x < 10;
    $map = function ($x) use ($keep) {
        if ($keep($x)) {
            return $x;
        }
        return 0;
    };
    $anon = new class {
        public function hidden() { if (true) { } }
    };
    return array_map($map, $items);
}
"""
    assert _rows(functions_in_source(source, "src/Survey/helpers.php", "/proj")) == [
        ("App.Survey.Base", "__construct", 2),
        ("App.Survey.Greets", "hi", 2),
        ("App.Survey.Suit", "color", 3),
        ("App.Survey", "helper", 3),
    ]


def test_a_class_declared_inside_a_function_is_its_own_entry():
    source = """<?php
function factory()
{
    class Hidden
    {
        public function secret() { if (true) { } }
    }
    return new Hidden();
}
"""
    assert _rows(functions_in_source(source, "factory.php", "/proj")) == [
        ("factory", "factory", 1),
        ("Hidden", "secret", 2),
    ]


def test_bracketed_namespaces_each_name_their_own_classes():
    source = """<?php
namespace App\\One {
    class A { public function run() { return 1; } }
}

namespace App\\Two {
    class B { public function run() { return 2; } }
}
"""
    assert _rows(functions_in_source(source, "src/two.php", "/proj")) == [
        ("App.One.A", "run", 1),
        ("App.Two.B", "run", 1),
    ]


def test_global_code_uses_the_class_or_the_file_path():
    source = """<?php
class Legacy { public function run() { return 1; } }

function boot() { return 1; }
"""
    functions = functions_in_source(source, "/proj/src/support/helpers.php", "/proj")
    assert _rows(functions) == [
        ("Legacy", "run", 1),
        ("support.helpers", "boot", 1),
    ]
    assert (functions[0].start_line, functions[0].end_line) == (2, 2)
    assert functions[0].language == "php"


def test_keywords_in_comments_strings_and_case_are_not_decisions():
    source = """<?php
class Sample
{
    public function stable($name)
    {
        $text = "if && || ? case default catch {$name}";
        // if && || ? case default catch
        /* if && || ? case default catch */
        # elseif foreach
        return <<<EOT
        if $name and or
        EOT;
    }
}
"""
    assert _rows(functions_in_source(source, "Sample.php", "/proj")) == [
        ("Sample", "stable", 1),
    ]
