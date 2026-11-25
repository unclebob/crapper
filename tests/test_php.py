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
