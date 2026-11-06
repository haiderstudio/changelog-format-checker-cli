#!/bin/sh
# Check the bundled examples. The bad file is wrong on purpose,
# so its check exits 1 — that is the expected result, not a failure.
set -e
cd "$(dirname "$0")/.."
python3 src/changelog_format_checker.py examples/good-changelog.md
python3 src/changelog_format_checker.py examples/bad-changelog.md || true
python3 src/changelog_format_checker.py --allow-no-unreleased examples/missing-unreleased.md
