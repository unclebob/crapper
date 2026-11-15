from pathlib import Path

from crapper.runners import gradle_builds, gradle_command, gradle_init_script, gradle_reports, run_coverage

REPORT = "build/reports/jacoco/test/jacocoTestReport.xml"


def write(root: Path, relative: str, text: str = "x\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_init_script_adds_jacoco_xml_to_every_java_project_without_touching_the_build():
    script = gradle_init_script()
    assert "allprojects" in script
    assert "withPlugin('java')" in script
    assert "apply plugin: 'jacoco'" in script
    assert "xml.required = true" in script


def test_the_wrapper_is_preferred_then_gradle_on_the_path_then_nothing(tmp_path):
    script = tmp_path / "init.gradle"
    which = {"gradle": "/usr/bin/gradle"}
    assert gradle_command(tmp_path, script, which.get) == [
        "/usr/bin/gradle", "test", "jacocoTestReport", "--init-script", str(script),
    ]
    write(tmp_path, "gradlew")
    assert gradle_command(tmp_path, script, which.get) == [
        str(tmp_path / "gradlew"), "test", "jacocoTestReport", "--init-script", str(script),
    ]
    (tmp_path / "gradlew").unlink()
    assert gradle_command(tmp_path, script, {}.get) is None


def test_reports_are_found_in_the_root_and_in_subprojects_to_two_levels(tmp_path):
    found = [write(tmp_path, p) for p in (REPORT, f"app/{REPORT}", f"libs/core/{REPORT}")]
    write(tmp_path, "a/b/c/" + REPORT)
    assert sorted(gradle_reports(tmp_path)) == sorted(found)


def test_the_build_root_is_the_settings_file_else_the_nearest_build_file(tmp_path):
    write(tmp_path, "settings.gradle.kts")
    write(tmp_path, "app/build.gradle.kts")
    write(tmp_path, "solo/build.gradle")
    nested = write(tmp_path, "app/src/main/kotlin/A.kt")
    lone = write(tmp_path / "solo", "src/B.kt")
    elsewhere = write(tmp_path, "docs/C.java")
    assert gradle_builds([nested, lone, elsewhere], tmp_path) == [tmp_path]
    assert gradle_builds([lone], tmp_path / "solo") == [tmp_path / "solo"]
    (tmp_path / "settings.gradle.kts").unlink()
    assert gradle_builds([nested, lone, elsewhere], tmp_path) == [
        tmp_path / "app",
        tmp_path / "solo",
    ]


def run_kotlin(tmp_path, monkeypatch, *, result=0, which=None):
    seen = []

    def shell(command, cwd):
        script = Path(command[command.index("--init-script") + 1])
        seen.append((command, cwd, script.read_text(encoding="utf-8"), (tmp_path / REPORT).exists()))
        return result

    monkeypatch.setattr("crapper.runners.run_shell", shell)
    monkeypatch.setattr("crapper.runners.shutil.which", lambda name: which)
    write(tmp_path, "settings.gradle.kts")
    write(tmp_path, "app/build.gradle.kts")
    source = write(tmp_path, "app/src/main/kotlin/App.kt", "fun f() = 1\n")
    write(tmp_path, REPORT, "stale")
    code = run_coverage(tmp_path, [source], None)
    return code, seen


def test_gradle_runs_once_at_the_build_root_with_the_init_script_and_a_fresh_report(
    tmp_path, monkeypatch
):
    write(tmp_path, "gradlew")
    code, seen = run_kotlin(tmp_path, monkeypatch)
    assert code == 0
    [(command, cwd, script, stale_present)] = seen
    assert command[0] == str(tmp_path / "gradlew")
    assert command[1:3] == ["test", "jacocoTestReport"]
    assert cwd == tmp_path
    assert "jacoco" in script
    assert not stale_present


def test_the_init_script_does_not_outlive_the_run(tmp_path, monkeypatch):
    write(tmp_path, "gradlew")
    _, seen = run_kotlin(tmp_path, monkeypatch)
    [(command, *_)] = seen
    assert not Path(command[command.index("--init-script") + 1]).exists()


def test_a_failed_gradle_run_warns_and_the_run_still_returns(tmp_path, monkeypatch, capsys):
    write(tmp_path, "gradlew")
    code, seen = run_kotlin(tmp_path, monkeypatch, result=1)
    assert code == 0 and len(seen) == 1
    assert "Kotlin coverage exited 1" in capsys.readouterr().err


def test_without_gradle_the_run_warns_and_starts_nothing(tmp_path, monkeypatch, capsys):
    code, seen = run_kotlin(tmp_path, monkeypatch)
    assert code == 0 and seen == []
    assert "No gradlew and no gradle" in capsys.readouterr().err


def test_without_a_gradle_build_file_the_run_warns_and_starts_nothing(tmp_path, monkeypatch, capsys):
    commands = []
    monkeypatch.setattr("crapper.runners.run_shell", lambda command, cwd: commands.append(command))
    source = write(tmp_path, "src/main/kotlin/App.kt", "fun f() = 1\n")
    run_coverage(tmp_path, [source], None)
    assert commands == []
    assert "No Gradle build" in capsys.readouterr().err
