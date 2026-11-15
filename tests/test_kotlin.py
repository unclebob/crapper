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
