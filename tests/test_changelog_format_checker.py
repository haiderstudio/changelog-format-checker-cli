"""Tests for changelog-format-checker-cli.

Standard library unittest only. Run with:

    python3 tests/test_changelog_format_checker.py
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import changelog_format_checker as cfc  # noqa: E402

GOOD = """# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- A new thing.

## [1.2.0] - 2026-02-10

### Fixed

- A bug fix.

## [1.0.0] - 2026-01-05

### Added

- First release.
"""


def messages(problems):
    return [problem["message"] for problem in problems]


def check(text, **kwargs):
    return cfc.check_text(text, "CHANGELOG.md", **kwargs)


class TestTitle(unittest.TestCase):
    def test_good_title_passes(self):
        self.assertEqual(check(GOOD), [])

    def test_missing_title(self):
        text = GOOD.replace("# Changelog\n\n", "", 1)
        problems = check(text)
        self.assertTrue(any("first heading" in m for m in messages(problems)))

    def test_wrong_title(self):
        text = GOOD.replace("# Changelog", "# Changes", 1)
        problems = check(text)
        self.assertTrue(any("first heading" in m for m in messages(problems)))

    def test_no_headings_at_all(self):
        problems = check("Just some words.\nNo headings here.\n")
        self.assertTrue(any("no '# Changelog' title" in m for m in messages(problems)))

    def test_content_before_title(self):
        text = "A stray line.\n\n" + GOOD
        problems = check(text)
        self.assertTrue(
            any("content before the '# Changelog' title" in m for m in messages(problems))
        )

    def test_empty_file(self):
        problems = check("")
        self.assertTrue(any("no '# Changelog' title" in m for m in messages(problems)))


class TestUnreleased(unittest.TestCase):
    def test_missing_unreleased(self):
        text = GOOD.replace("## [Unreleased]\n\n### Added\n\n- A new thing.\n\n", "")
        problems = check(text)
        self.assertEqual(len(problems), 1)
        self.assertIn("no '[Unreleased]' section", messages(problems)[0])
        self.assertEqual(problems[0]["line"], 5)

    def test_missing_unreleased_allowed(self):
        text = GOOD.replace("## [Unreleased]\n\n### Added\n\n- A new thing.\n\n", "")
        self.assertEqual(check(text, allow_no_unreleased=True), [])

    def test_unreleased_after_a_version(self):
        text = GOOD.replace(
            "## [Unreleased]\n\n### Added\n\n- A new thing.\n\n", ""
        )
        text += "\n## [Unreleased]\n\n### Added\n\n- Late.\n"
        problems = check(text)
        self.assertTrue(
            any("must come before all version sections" in m for m in messages(problems))
        )

    def test_unreleased_with_a_date(self):
        text = GOOD.replace("## [Unreleased]", "## [Unreleased] - 2026-03-01", 1)
        problems = check(text)
        self.assertTrue(
            any("must not have a date" in m for m in messages(problems))
        )

    def test_duplicate_unreleased(self):
        text = GOOD + "\n## [Unreleased]\n\n### Added\n\n- Again.\n"
        problems = check(text)
        self.assertTrue(any("duplicate '[Unreleased]'" in m for m in messages(problems)))

    def test_unreleased_without_brackets(self):
        text = GOOD.replace("## [Unreleased]", "## Unreleased", 1)
        self.assertEqual(check(text), [])


class TestVersionHeadings(unittest.TestCase):
    def test_version_without_a_date(self):
        text = GOOD.replace("## [1.2.0] - 2026-02-10", "## [1.2.0]", 1)
        problems = check(text)
        self.assertTrue(
            any("needs a version and a date" in m for m in messages(problems))
        )

    def test_version_without_brackets(self):
        text = GOOD.replace("## [1.2.0] - 2026-02-10", "## 1.2.0 - 2026-02-10", 1)
        self.assertEqual(check(text), [])

    def test_v_prefix_accepted(self):
        text = GOOD.replace("## [1.2.0] - 2026-02-10", "## [v1.2.0] - 2026-02-10", 1)
        self.assertEqual(check(text), [])

    def test_bad_version(self):
        text = GOOD.replace("## [1.2.0] - 2026-02-10", "## [1.2] - 2026-02-10", 1)
        problems = check(text)
        self.assertTrue(
            any("needs a version and a date" in m for m in messages(problems))
        )

    def test_impossible_date(self):
        text = GOOD.replace("2026-02-10", "2026-02-30", 1)
        problems = check(text)
        self.assertTrue(
            any("not a real date" in m for m in messages(problems))
        )

    def test_bad_month(self):
        text = GOOD.replace("2026-02-10", "2026-13-10", 1)
        problems = check(text)
        self.assertTrue(
            any("not a real date" in m for m in messages(problems))
        )

    def test_wrong_date_shape(self):
        text = GOOD.replace("2026-02-10", "10-02-2026", 1)
        problems = check(text)
        self.assertTrue(
            any("needs a version and a date" in m for m in messages(problems))
        )

    def test_prerelease_version(self):
        text = GOOD.replace(
            "## [1.2.0] - 2026-02-10", "## [1.2.0-rc.1] - 2026-02-10", 1
        )
        self.assertEqual(check(text), [])

    def test_duplicate_version(self):
        text = GOOD.replace("## [1.0.0] - 2026-01-05", "## [1.2.0] - 2026-01-05", 1)
        problems = check(text)
        self.assertTrue(any("duplicate version" in m for m in messages(problems)))

    def test_no_version_sections(self):
        text = "# Changelog\n\nAll notable changes.\n"
        problems = check(text, allow_no_unreleased=True)
        self.assertTrue(any("no version sections" in m for m in messages(problems)))


class TestVersionOrder(unittest.TestCase):
    def test_newest_first_passes(self):
        self.assertEqual(check(GOOD), [])

    def test_older_after_newer_fails(self):
        text = GOOD.replace("## [1.0.0] - 2026-01-05", "## [1.3.0] - 2026-01-05", 1)
        problems = check(text)
        self.assertTrue(
            any("newest first" in m for m in messages(problems))
        )

    def test_prerelease_before_release_passes(self):
        text = """# Changelog

## [Unreleased]

### Added

- Something.

## [1.0.0] - 2026-01-05

### Added

- Release.

## [1.0.0-rc.1] - 2026-01-01

### Added

- Candidate.
"""
        self.assertEqual(check(text), [])

    def test_release_before_prerelease_fails(self):
        text = """# Changelog

## [Unreleased]

### Added

- Something.

## [1.0.0-rc.1] - 2026-01-05

### Added

- Candidate.

## [1.0.0] - 2026-01-01

### Added

- Release.
"""
        problems = check(text)
        self.assertTrue(
            any("newest first" in m for m in messages(problems))
        )


class TestSubsections(unittest.TestCase):
    def test_all_known_sections_pass(self):
        text = "# Changelog\n\n## [Unreleased]\n\n"
        for section in cfc.KNOWN_SECTIONS:
            text += "### %s\n\n- One thing.\n\n" % section
        self.assertEqual(check(text), [])

    def test_unknown_subsection(self):
        text = GOOD.replace("### Fixed", "### Stuff", 1)
        problems = check(text)
        self.assertTrue(any("unknown subsection 'Stuff'" in m for m in messages(problems)))

    def test_empty_subsection(self):
        text = GOOD.replace("### Fixed\n\n- A bug fix.\n", "### Fixed\n", 1)
        problems = check(text)
        self.assertTrue(
            any("subsection 'Fixed' has no entries" in m for m in messages(problems))
        )

    def test_version_with_no_subsections(self):
        text = GOOD.replace("### Fixed\n\n- A bug fix.\n", "", 1)
        problems = check(text)
        self.assertTrue(
            any("has no subsections" in m for m in messages(problems))
        )

    def test_subsection_outside_a_version(self):
        text = "# Changelog\n\n### Added\n\n- Orphan.\n"
        problems = check(text, allow_no_unreleased=True)
        self.assertTrue(
            any("outside a version section" in m for m in messages(problems))
        )

    def test_deep_heading(self):
        text = GOOD.replace(
            "### Fixed\n\n- A bug fix.\n",
            "### Fixed\n\n#### Detail\n\n- A bug fix.\n",
            1,
        )
        problems = check(text)
        self.assertTrue(any("too deep" in m for m in messages(problems)))

    def test_entry_outside_a_subsection(self):
        text = GOOD.replace(
            "## [1.2.0] - 2026-02-10\n\n### Fixed",
            "## [1.2.0] - 2026-02-10\n\n- Loose entry.\n\n### Fixed",
            1,
        )
        problems = check(text)
        self.assertTrue(
            any("entry outside a subsection" in m for m in messages(problems))
        )

    def test_text_outside_a_subsection(self):
        text = GOOD.replace(
            "## [1.2.0] - 2026-02-10\n\n### Fixed",
            "## [1.2.0] - 2026-02-10\n\nSome words.\n\n### Fixed",
            1,
        )
        problems = check(text)
        self.assertTrue(
            any("text outside a subsection" in m for m in messages(problems))
        )

    def test_non_bullet_line_in_subsection(self):
        text = GOOD.replace("- A bug fix.", "A bug fix.", 1)
        problems = check(text)
        self.assertTrue(
            any("not a bullet entry" in m for m in messages(problems))
        )

    def test_star_bullet_accepted(self):
        text = GOOD.replace("- A bug fix.", "* A bug fix.", 1)
        self.assertEqual(check(text), [])

    def test_entry_before_any_version(self):
        text = "# Changelog\n\n- Orphan entry.\n\n" + GOOD.split("\n\n", 1)[1]
        problems = check(text)
        self.assertTrue(
            any("entry outside a version section" in m for m in messages(problems))
        )


class TestCLI(unittest.TestCase):
    def run_cli(self, *argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cfc.run(list(argv))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_exit_0_good_file(self):
        code, out, _ = self.run_cli("examples/good-changelog.md")
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_exit_1_bad_file(self):
        code, out, _ = self.run_cli("examples/bad-changelog.md")
        self.assertEqual(code, 1)
        self.assertIn("6 problem(s) in 1 file(s)", out)

    def test_exit_2_missing_file(self):
        code, _, err = self.run_cli("no-such-file.md")
        self.assertEqual(code, 2)
        self.assertIn("error:", err)

    def test_exit_2_bad_flag(self):
        code, _, _ = self.run_cli("--nope")
        self.assertEqual(code, 2)

    def test_version_flag(self):
        code, out, _ = self.run_cli("--version")
        self.assertEqual(code, 0)
        self.assertIn("changelog-format-checker", out)

    def test_json_output(self):
        code, out, err = self.run_cli("--json", "examples/bad-changelog.md")
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data["checked"], 1)
        self.assertEqual(data["problems"], 6)
        self.assertFalse(data["pass"])
        self.assertEqual(len(data["issues"]), 6)
        self.assertEqual(data["issues"][0]["line"], 5)
        self.assertIn("1 file(s) checked, 6 problem(s)", err)

    def test_json_clean_run(self):
        code, out, _ = self.run_cli("--json", "examples/good-changelog.md")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["pass"])
        self.assertEqual(data["issues"], [])

    def test_default_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CHANGELOG.md"
            path.write_text(GOOD)
            old = os.getcwd()
            os.chdir(tmp)
            try:
                code, out, _ = self.run_cli()
            finally:
                os.chdir(old)
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_multiple_files(self):
        code, out, _ = self.run_cli(
            "examples/good-changelog.md", "examples/missing-unreleased.md"
        )
        self.assertEqual(code, 1)
        self.assertIn("1 problem(s) in 2 file(s)", out)

    def test_allow_no_unreleased_flag(self):
        code, out, _ = self.run_cli(
            "--allow-no-unreleased", "examples/missing-unreleased.md"
        )
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_input_files_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CHANGELOG.md"
            path.write_text(GOOD)
            before = path.read_text()
            self.run_cli(str(path))
            self.assertEqual(path.read_text(), before)


class TestExamples(unittest.TestCase):
    def test_sample_output_matches_fresh_run(self):
        result = subprocess.run(
            [sys.executable, "src/changelog_format_checker.py",
             "examples/bad-changelog.md"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        committed = (ROOT / "examples" / "sample-output.txt").read_text()
        self.assertEqual(result.stdout, committed)

    def test_good_example_passes(self):
        result = subprocess.run(
            [sys.executable, "src/changelog_format_checker.py",
             "examples/good-changelog.md"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)

    def test_run_example_script(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_readme_quotes_real_output(self):
        readme = (ROOT / "README.md").read_text()
        sample = (ROOT / "examples" / "sample-output.txt").read_text()
        for line in sample.strip().splitlines():
            self.assertIn(line, readme, line)


class TestRepoHygiene(unittest.TestCase):
    def test_stdlib_only(self):
        allowed = {
            "argparse", "contextlib", "datetime", "io", "json", "os", "re",
            "subprocess", "sys", "tempfile", "unittest", "pathlib",
        }
        local_modules = {"changelog_format_checker"}
        for path in list((ROOT / "src").rglob("*.py")) + list(
            (ROOT / "tests").rglob("*.py")
        ):
            for line in path.read_text().splitlines():
                line = line.strip()
                if line.startswith("import "):
                    for name in line[7:].split(","):
                        top = name.strip().split(".")[0].split(" ")[0]
                        self.assertIn(
                            top, allowed | local_modules, "%s in %s" % (top, path)
                        )
                elif line.startswith("from "):
                    top = line.split()[1].split(".")[0]
                    self.assertIn(
                        top, allowed | local_modules, "%s in %s" % (top, path)
                    )

    def test_no_placeholders_or_secrets(self):
        banned = (
            "TODO",
            "FIXME",
            "lorem",
            "coming soon",
            "API_KEY",
            "api_key",
            "password =",
        )
        # The tests directory is excluded from this scan: the test file
        # itself names the banned words in its own check list, and it
        # uses temp paths. The shipped content is what must be clean.
        # .git is excluded too: GitHub's checkout ships sample hooks
        # under .git/hooks/ that contain "TODO" (Day 21 CI lesson).
        shipped = [
            path
            for path in ROOT.rglob("*")
            if path.is_file()
            and "__pycache__" not in str(path)
            and ".git" not in path.parts
            and "tests" not in path.parts
        ]
        for path in shipped:
            text = path.read_text(errors="ignore")
            for word in banned:
                self.assertNotIn(word, text, "%s in %s" % (word, path))

    def test_no_absolute_paths(self):
        # Same exclusion as the placeholder scan: the test file itself
        # names temp paths in its own check list.
        shipped = [
            path
            for path in ROOT.rglob("*")
            if path.is_file()
            and "__pycache__" not in str(path)
            and ".git" not in path.parts
            and "tests" not in path.parts
        ]
        for path in shipped:
            text = path.read_text(errors="ignore")
            self.assertNotIn("/home/hatch", text, "absolute path in %s" % path)
            self.assertNotIn("/tmp/", text, "absolute path in %s" % path)

    def test_gitignore_lists_env_first(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")


if __name__ == "__main__":
    unittest.main()
