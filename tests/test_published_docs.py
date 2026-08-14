from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_MARKDOWN = [
    ROOT / "README.md",
    ROOT / "SKILL.md",
    ROOT / "DESIGN.md",
    ROOT / "AGENTS.md",
    *sorted((ROOT / "references").glob("*.md")),
]

# Reject machine-specific paths while allowing URLs and relative examples.
MACHINE_PATH = re.compile(
    r"(?:[A-Za-z]:\\|/Users/[^/\s]+/|/home/[^/\s]+/)"
)


class PublishedDocumentationPortabilityTests(unittest.TestCase):
    def test_published_markdown_has_no_machine_specific_paths(self) -> None:
        violations: list[str] = []
        for path in PUBLISHED_MARKDOWN:
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if MACHINE_PATH.search(line):
                    violations.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")

        self.assertEqual([], violations, "Machine-specific paths found:\n" + "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
