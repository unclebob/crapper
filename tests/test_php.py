from crapper.discover import is_test_file, language_of


def test_php_files_are_php_except_blade_templates_and_tests():
    assert language_of("app/Services/AutoRefill.php") == "php"
    assert language_of("resources/views/welcome.blade.php") is None
    assert is_test_file("app/Services/AutoRefillTest.php") is True
    assert is_test_file("app/Services/AutoRefill.php") is False


def test_help_names_php_and_its_test_pattern(capsys):
    from crapper.cli import run

    assert run(["--help"]) == 0
    help_text = capsys.readouterr().out
    assert "PHP (.php, not .blade.php)" in help_text
    assert "*Test.php" in help_text


def test_help_names_the_php_namespace_for_uml_viewer(capsys):
    from crapper.cli import run

    assert run(["--help"]) == 0
    assert "PHP          namespace with dots" in capsys.readouterr().out


from crapper.languages import functions_in_file
from crapper.languages.php import functions_in_source

SCORE = """<?php
namespace App\\Services;

class AutoRefill
{
    public function score($a, $b, array $values)
    {
        for ($i = 0; $i < count($values); $i++) {
        }
        foreach ($values as $value) {
        }
        while ($a) {
            $a = false;
        }
        do {
            $b = false;
        } while ($b);
        if ($a && $b || $values) {
        } elseif ($a and $b or $values) {
        } else if ($a) {
        } else {
        }
        try {
            return $a ? 1 : ($b ?: 0);
        } catch (\\RuntimeException $e) {
            return 2;
        } catch (\\LogicException $e) {
            return 3;
        }
    }

    public function choose(int $value): string
    {
        switch ($value) {
            case 1:
                return 'one';
            case 2:
                return 'two';
            default:
                return 'many';
        }
    }

    public function label(int $value): string
    {
        return match ($value) {
            1, 2 => 'small',
            3 => 'medium',
            default => 'large',
        };
    }

    public function fallback($a, $b)
    {
        $a ??= $b;
        $c = $a xor $b;
        return $a ?? $b;
    }
}
"""


def test_counts_each_decision_once():
    methods = functions_in_source(SCORE, "app/Services/AutoRefill.php")
    assert [(method.name, method.complexity) for method in methods] == [
        ("score", 16),
        ("choose", 3),
        ("label", 3),
        ("fallback", 3),
    ]
    assert {method.namespace for method in methods} == {"App.Services.AutoRefill"}
    assert {method.language for method in methods} == {"php"}


ENTRIES = """<?php
namespace App\\Models;

function helper($a)
{
    $twice = fn ($n) => $n ? $n * 2 : 0;
    $check = function ($n) {
        if ($n) {
            return 1;
        }
        return 0;
    };
    return $a ? $twice($a) : $check($a);
}

interface Priced
{
    public function price(): int;
}

abstract class Base
{
    abstract public function name(): string;

    public function __construct(private int $amount)
    {
        if ($amount < 0) {
            throw new \\InvalidArgumentException();
        }
    }
}

trait Refundable
{
    public function refund(): bool
    {
        return $this->paid && ! $this->refunded;
    }
}

enum Status: string
{
    case Active = 'active';

    public function isActive(): bool
    {
        return $this === self::Active;
    }
}
"""


def test_entries_are_bodied_methods_and_top_level_functions():
    functions = functions_in_source(ENTRIES, "app/Models/Status.php")
    assert [(fn.namespace, fn.name, fn.complexity) for fn in functions] == [
        ("App.Models", "helper", 4),
        ("App.Models.Base", "__construct", 2),
        ("App.Models.Refundable", "refund", 2),
        ("App.Models.Status", "isActive", 1),
    ]
    first = functions[0]
    assert (first.start_line, first.end_line) == (4, 14)


MIGRATION = """<?php

use Illuminate\\Database\\Migrations\\Migration;

return new class extends Migration
{
    public function up(): void
    {
        if (true) {
        }
    }
};
"""

ANONYMOUS = """<?php
namespace App;

class Factory
{
    public function make()
    {
        return new class {
            public function run()
            {
                if (true) {
                }
            }
        };
    }
}
"""


def test_anonymous_class_methods_are_not_entries_and_do_not_raise_complexity():
    assert functions_in_source(MIGRATION, "database/migrations/create.php") == []
    methods = functions_in_source(ANONYMOUS, "app/Factory.php")
    assert [(method.name, method.complexity) for method in methods] == [("make", 1)]


def test_braced_namespace_and_the_global_namespace():
    braced = """<?php
namespace App\\Support {
    function tidy() { return 1; }
}
"""
    assert [(fn.namespace, fn.name) for fn in functions_in_source(braced, "a.php")] == [
        ("App.Support", "tidy")
    ]
    global_source = """<?php
function helper() { return 1; }
class Plain { public function go() { return 1; } }
"""
    functions = functions_in_source(global_source, "app/helpers.php")
    assert [(fn.namespace, fn.name) for fn in functions] == [
        ("helpers", "helper"),
        ("Plain", "go"),
    ]


def test_php_is_registered():
    functions = functions_in_file("php", SCORE, "app/Services/AutoRefill.php", "/proj")
    assert [fn.name for fn in functions] == ["score", "choose", "label", "fallback"]
