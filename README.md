# changelog-format-checker-cli

Check CHANGELOG.md follows Keep a Changelog, fail CI on bad shape.

[![CI](https://github.com/haiderstudio/changelog-format-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/changelog-format-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`changelog_format_checker` reads a `CHANGELOG.md` file and checks it
follows the [Keep a Changelog](https://keepachangelog.com) shape. It
reports every problem with its file and line number, and exits 1 when
any file has a problem, so a CI step can fail the build until the
changelog is in shape. It exits 0 when every file passes.

The shape it checks:

- The file starts with a `# Changelog` title.
- An `## [Unreleased]` section comes first. (`--allow-no-unreleased`
  skips this one rule.)
- Every version section is `## [1.2.3] - YYYY-MM-DD`, with a real
  semver version and a real calendar date. Brackets around the
  version are optional, and a leading `v` is accepted
  (`## [v1.2.0] - 2026-02-10`).
- Versions run newest first, with no duplicates. A prerelease
  (`1.0.0-rc.1`) sorts before its release (`1.0.0`).
- Every subsection is one of Added, Changed, Deprecated, Removed,
  Fixed or Security, and has at least one bullet entry.
- Every entry is a bullet (`- ` or `* `) under a subsection — no
  loose text, no entry without a version.

It is report-only: it never writes or changes any file.

- It checks one file or several, and defaults to `CHANGELOG.md`
  in the current folder.
- `--json` prints the result as JSON on stdout, with the summary on
  standard error, so the JSON stays parseable.
- It runs fully offline: it sends nothing anywhere and needs no API
  key.

## What it does NOT do

- It does not write or fix `CHANGELOG.md`. It reports problems;
  fixing them is your call.
- It does not check whether the entries are true, or whether a
  version was actually released. It checks the file's shape, not
  its history.
- It does not check commit messages — that is
  [commit-message-skill](https://github.com/haiderstudio/commit-message-skill),
  which writes a message from a diff. This tool checks the
  changelog file itself.
- It does not write changelog entries — that is
  [changelog-writer-skill](https://github.com/haiderstudio/changelog-writer-skill),
  which turns a git log into an entry. Checking the format of an
  existing file is the other half of that job.

## How this differs

- `rcmachado/changelog` (47 stars, Go) reads, validates, and
  *manipulates* CHANGELOG.md files. This tool only checks the
  format, and only reports — it never changes the file — and it
  needs no Go install, just Python's standard library.
- `cyberark/parse-a-changelog` (18 stars, Ruby) is a validator
  library for changelogs. This tool is a standalone command-line
  checker with a CI exit code, not a library.
- `chavacava/changelog-lint` (5 stars, Go) is a simple changelog
  linter. This tool is the Python standard-library version of that
  one job, with line numbers on every problem.
- `vweevers/remark-changelog` (6 stars, JavaScript) lints *or
  fixes* a changelog. This tool never fixes anything; it only
  reports.
- `zattoo/changelog` (5 stars, JavaScript) is a GitHub Action that
  validates CHANGELOG.md. This tool runs anywhere Python runs, in
  CI or on your machine.

## Install

```sh
git clone https://github.com/haiderstudio/changelog-format-checker-cli.git
cd changelog-format-checker-cli
```

No install step, no dependencies — Python 3.12 or newer, standard
library only.

## Usage

Check the default file, `CHANGELOG.md`:

```sh
python3 src/changelog_format_checker.py
```

Check a named file:

```sh
python3 src/changelog_format_checker.py examples/bad-changelog.md
```

```
PROBLEM  examples/bad-changelog.md:5: no '[Unreleased]' section
PROBLEM  examples/bad-changelog.md:11: unknown subsection 'Stuff' — use Added, Changed, Deprecated, Removed, Fixed or Security
PROBLEM  examples/bad-changelog.md:15: version '1.3.0' comes after '1.2.0' — versions must be newest first
PROBLEM  examples/bad-changelog.md:23: subsection 'Added' has no entries
PROBLEM  examples/bad-changelog.md:25: version section '0.9.0' has no subsections
PROBLEM  examples/bad-changelog.md:27: text outside a subsection
6 problem(s) in 1 file(s)
```

Exit code 1 — six problems, each with its file and line.

Check a file that follows the shape:

```sh
python3 src/changelog_format_checker.py examples/good-changelog.md
```

```
OK — 1 file(s) follow Keep a Changelog.
```

Exit code 0.

A file that is fine except for a missing Unreleased section:

```sh
python3 src/changelog_format_checker.py examples/missing-unreleased.md
```

```
PROBLEM  examples/missing-unreleased.md:5: no '[Unreleased]' section
1 problem(s) in 1 file(s)
```

Allow a changelog with no Unreleased section:

```sh
python3 src/changelog_format_checker.py --allow-no-unreleased examples/missing-unreleased.md
```

```
OK — 1 file(s) follow Keep a Changelog.
```

Machine-readable output for CI:

```sh
python3 src/changelog_format_checker.py --json examples/missing-unreleased.md
```

```json
{
  "checked": 1,
  "problems": 1,
  "pass": false,
  "issues": [
    {
      "file": "examples/missing-unreleased.md",
      "line": 5,
      "message": "no '[Unreleased]' section"
    }
  ]
}
```

The summary line (`1 file(s) checked, 1 problem(s)`) goes to
standard error, so stdout is clean JSON.

## Examples

### A file with six problems

`examples/bad-changelog.md` has no Unreleased section, an unknown
subsection, versions out of order, an empty subsection, a version
with no subsections, and a line of text where a bullet belongs:

```sh
python3 src/changelog_format_checker.py examples/bad-changelog.md
```

```
PROBLEM  examples/bad-changelog.md:5: no '[Unreleased]' section
PROBLEM  examples/bad-changelog.md:11: unknown subsection 'Stuff' — use Added, Changed, Deprecated, Removed, Fixed or Security
PROBLEM  examples/bad-changelog.md:15: version '1.3.0' comes after '1.2.0' — versions must be newest first
PROBLEM  examples/bad-changelog.md:23: subsection 'Added' has no entries
PROBLEM  examples/bad-changelog.md:25: version section '0.9.0' has no subsections
PROBLEM  examples/bad-changelog.md:27: text outside a subsection
6 problem(s) in 1 file(s)
```

Exit code 1.

### A file that passes

`examples/good-changelog.md` has an Unreleased section, then
versions 1.2.0, 1.1.0 and 1.0.0 in order, each with dated headings
and bullet entries under Added, Changed or Fixed:

```sh
python3 src/changelog_format_checker.py examples/good-changelog.md
```

```
OK — 1 file(s) follow Keep a Changelog.
```

Exit code 0.

## How it is tested

```sh
python3 tests/test_changelog_format_checker.py
```

Tests, standard library `unittest` only — no third-party packages.
They cover: the title (missing, wrong, content before it, empty
file), the Unreleased section (missing, allowed, after a version,
with a date, duplicated, without brackets), version headings
(missing date, no brackets, `v` prefix, bad version, impossible
date, wrong date shape, prerelease, duplicate, no versions at
all), version order (newest first, prerelease before release),
subsections (all six known types, unknown, empty, version with
none, outside a version, deep headings, entries and text outside
a subsection, non-bullet lines, `*` bullets, entries before any
version), the CLI (exit 0/1/2, `--json` output, `--version`, bad
flags, the default file, multiple files, `--allow-no-unreleased`,
input files left unchanged), the bundled examples (the committed
`examples/sample-output.txt` is compared against a fresh run, and
the README's quoted outputs are checked against it), the example
script, and a check that the code and the tests import standard
library only.

The bundled example is a real run, not made-up output:

```sh
sh examples/run-example.sh
```

It checks the good file (passes), the bad file (fails on purpose),
and the missing-Unreleased file with the flag (passes). The
committed `examples/sample-output.txt` is the output of the
bad-file check.

## Contributing

Small, focused improvements are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

Built from scratch for this repo. The Keep a Changelog shape is a
public spec ([keepachangelog.com](https://keepachangelog.com)), and
this tool checks a file against that shape; no code was copied
from any existing changelog checker. The nearest tools validate
and change changelogs, or lint them from another language — and
this tool's slice (format-check only, report-only, Python
standard library, fails CI) is its own.
