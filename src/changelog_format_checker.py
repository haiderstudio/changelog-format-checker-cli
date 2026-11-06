"""changelog-format-checker-cli: check CHANGELOG.md follows Keep a Changelog.

One job only: read one or more changelog files and check each one
follows the Keep a Changelog shape (keepachangelog.com):

- the file starts with a ``# Changelog`` title,
- an ``## [Unreleased]`` section comes first (unless
  ``--allow-no-unreleased`` is given),
- every version section is ``## [1.2.3] - YYYY-MM-DD`` with a real
  semver version and a real calendar date,
- versions run newest first, with no duplicates,
- every subsection is one of Added, Changed, Deprecated, Removed,
  Fixed or Security, and has at least one bullet entry,
- every entry is a bullet under a subsection.

Every problem names the file and line. Exit 1 when any file has a
problem, so a CI step can fail the build. Exit 0 when every file
passes. Exit 2 on a usage problem (missing file, unreadable file,
bad flag).

Report-only: it never writes or changes any file.

Standard library only.
"""

import argparse
import contextlib
import datetime
import json
import re
import sys
from pathlib import Path

VERSION = "1.0.0"

KNOWN_SECTIONS = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
BULLET_RE = re.compile(r"^\s*[-*]\s+\S")
# A version heading, e.g. "## [1.2.3] - 2026-01-15" or "## 1.2.3 - 2026-01-15".
VERSION_HEADING_RE = re.compile(
    r"^\[?(v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)\]?"
    r"\s*-\s*(\d{4}-\d{2}-\d{2})\s*$"
)
SEMVER_RE = re.compile(
    r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


class UsageError(Exception):
    """A usage problem: exit 2, not a changelog problem."""


def semver_key(version):
    """Sort key for a semver string: higher means newer.

    A release beats its own prerelease; prerelease parts compare
    number by number, and a number beats a word.
    """
    match = SEMVER_RE.match(version)
    major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
    prerelease = match.group(4)
    if prerelease is None:
        return (major, minor, patch, 1, ())
    parts = []
    for part in prerelease.split("."):
        if part.isdigit():
            parts.append((0, int(part), ""))
        else:
            parts.append((1, 0, part))
    return (major, minor, patch, 0, tuple(parts))


def check_text(text, filename, allow_no_unreleased=False):
    """Check one changelog's text. Returns a list of problem dicts.

    Each problem is ``{"file": ..., "line": ..., "message": ...}``.
    """
    problems = []
    lines = text.splitlines()

    def add(line_no, message):
        problems.append({"file": filename, "line": line_no, "message": message})

    # --- Find the headings, with line numbers. ---
    headings = []  # (line_no, level, text)
    for index, line in enumerate(lines, start=1):
        match = HEADING_RE.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))

    # --- Title: the first heading must be "# Changelog". ---
    if not headings:
        add(1, "no '# Changelog' title")
        return problems
    first_line, first_level, first_text = headings[0]
    if first_level != 1 or first_text.lower() != "changelog":
        add(first_line, "first heading must be '# Changelog'")
    for index, line in enumerate(lines, start=1):
        if index >= first_line:
            break
        if line.strip():
            add(index, "content before the '# Changelog' title")

    # --- Walk the file in order, headings and body lines together. ---
    seen_unreleased = False
    seen_versions = {}  # version string -> line
    previous_key = None
    previous_version = None
    current_version = None  # None, "unreleased", or a version string
    current_version_line = None
    current_version_has_subsection = False
    current_subsection = None
    current_subsection_line = None
    current_subsection_has_entry = False

    def close_subsection():
        nonlocal current_subsection, current_subsection_line
        nonlocal current_subsection_has_entry
        if current_subsection is not None and not current_subsection_has_entry:
            add(
                current_subsection_line,
                "subsection '%s' has no entries" % current_subsection,
            )
        current_subsection = None
        current_subsection_line = None
        current_subsection_has_entry = False

    def close_version():
        nonlocal current_version, current_version_line
        nonlocal current_version_has_subsection
        if current_version is not None and not current_version_has_subsection:
            name = "Unreleased" if current_version == "unreleased" else current_version
            add(
                current_version_line,
                "version section '%s' has no subsections" % name,
            )
        current_version = None
        current_version_line = None
        current_version_has_subsection = False

    for index, line in enumerate(lines, start=1):
        match = HEADING_RE.match(line)
        if match:
            level, text = len(match.group(1)), match.group(2).strip()
            if level == 1:
                continue
            if level >= 4:
                add(
                    index,
                    "heading level too deep — only #, ## and ### are used",
                )
                continue
            if level == 2:
                close_subsection()
                close_version()
                plain = text.strip("[]").strip()
                if plain.lower() == "unreleased":
                    if seen_unreleased:
                        add(index, "duplicate '[Unreleased]' section")
                    if seen_versions:
                        add(
                            index,
                            "'[Unreleased]' must come before all version sections",
                        )
                    seen_unreleased = True
                    current_version = "unreleased"
                    current_version_line = index
                    continue
                if plain.lower().startswith("unreleased"):
                    add(index, "'[Unreleased]' must not have a date")
                    seen_unreleased = True
                    current_version = "unreleased"
                    current_version_line = index
                    continue
                version_match = VERSION_HEADING_RE.match(text)
                if not version_match:
                    add(
                        index,
                        "version heading needs a version and a date, "
                        "like '## [1.2.3] - 2026-01-15'",
                    )
                    current_version = None
                    current_version_line = None
                    continue
                version, date_text = version_match.group(1), version_match.group(2)
                if not SEMVER_RE.match(version):
                    add(index, "'%s' is not a valid version" % version)
                    current_version = None
                    current_version_line = None
                    continue
                try:
                    year, month, day = (int(part) for part in date_text.split("-"))
                    datetime.date(year, month, day)
                except ValueError:
                    add(index, "date '%s' is not a real date" % date_text)
                if version in seen_versions:
                    add(
                        index,
                        "duplicate version '%s' (first seen at line %d)"
                        % (version, seen_versions[version]),
                    )
                seen_versions[version] = index
                key = semver_key(version)
                if previous_key is not None and key >= previous_key:
                    add(
                        index,
                        "version '%s' comes after '%s' — versions must be newest first"
                        % (version, previous_version),
                    )
                else:
                    previous_key = key
                    previous_version = version
                current_version = version
                current_version_line = index
                continue
            # level 3: a subsection heading.
            if current_version is None:
                add(index, "subsection '%s' outside a version section" % text)
                continue
            close_subsection()
            current_version_has_subsection = True
            if text not in KNOWN_SECTIONS:
                add(
                    index,
                    "unknown subsection '%s' — use Added, Changed, Deprecated, "
                    "Removed, Fixed or Security" % text,
                )
            current_subsection = text
            current_subsection_line = index
            current_subsection_has_entry = False
            continue
        # A body line.
        stripped = line.strip()
        if not stripped:
            continue
        if current_version is None:
            # Intro text between the title and the first version
            # section is fine; a bullet there has no version to live in.
            if BULLET_RE.match(line):
                add(index, "entry outside a version section")
            continue
        if current_subsection is None:
            if BULLET_RE.match(line):
                add(index, "entry outside a subsection")
            else:
                add(index, "text outside a subsection")
            continue
        if BULLET_RE.match(line):
            current_subsection_has_entry = True
        else:
            add(index, "line is not a bullet entry")

    close_subsection()
    close_version()

    if not seen_unreleased and not allow_no_unreleased:
        if seen_versions:
            first_version_line = min(seen_versions.values())
            add(first_version_line, "no '[Unreleased]' section")
        else:
            add(1, "no '[Unreleased]' section")
    if not seen_unreleased and not seen_versions:
        add(1, "no version sections — add '## [Unreleased]' or a dated version")

    # Problems are reported in file order.
    problems.sort(key=lambda problem: problem["line"])
    return problems


def check_file(path, allow_no_unreleased=False):
    """Check one changelog file. Returns its problem list."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise UsageError("file not found: %s" % path)
    except (OSError, UnicodeDecodeError) as exc:
        raise UsageError("cannot read %s: %s" % (path, exc))
    return check_text(text, str(path), allow_no_unreleased)


def run(argv=None):
    """Run the CLI. Returns the exit code: 0 pass, 1 problems, 2 usage."""
    parser = argparse.ArgumentParser(
        prog="changelog-format-checker",
        description="Check CHANGELOG.md follows Keep a Changelog.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        default=["CHANGELOG.md"],
        help="changelog files to check (default: CHANGELOG.md)",
    )
    parser.add_argument(
        "--allow-no-unreleased",
        action="store_true",
        help="do not require an '[Unreleased]' section",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the result as JSON on stdout",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="changelog-format-checker " + VERSION,
    )
    try:
        with contextlib.redirect_stderr(sys.stderr):
            args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0

    all_problems = []
    try:
        for name in args.files:
            all_problems.extend(check_file(Path(name), args.allow_no_unreleased))
    except UsageError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    passed = not all_problems
    if args.json:
        result = {
            "checked": len(args.files),
            "problems": len(all_problems),
            "pass": passed,
            "issues": all_problems,
        }
        print(json.dumps(result, indent=2))
        print(
            "%d file(s) checked, %d problem(s)"
            % (len(args.files), len(all_problems)),
            file=sys.stderr,
        )
    else:
        for problem in all_problems:
            print(
                "PROBLEM  %s:%d: %s"
                % (problem["file"], problem["line"], problem["message"])
            )
        if passed:
            print(
                "OK — %d file(s) follow Keep a Changelog." % len(args.files)
            )
        else:
            print(
                "%d problem(s) in %d file(s)"
                % (len(all_problems), len(args.files))
            )
    return 0 if passed else 1


def main():
    sys.exit(run())


if __name__ == "__main__":
    main()
