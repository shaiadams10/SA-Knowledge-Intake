from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from intake_engine import (  # noqa: E402
    apply_agent, basic_clean, package, prepare_agent, read_jsonl, save_selection,
    start, validate, write_jsonl,
)


INFORMATION = """# Practical source organization

Organize each source around one clear subject and preserve the relationship between its headings and paragraphs.
Keep units, table labels, definitions, and limitations beside the statements they explain so later retrieval retains context.
Remove navigation and repeated page furniture only after comparing the selected documents, because a short line may be meaningful on one page and boilerplate across many pages.
Use complete sentences and stable section headings, and check the final document for broken endings, duplicated passages, and unsupported additions.
This produces coherent source documents that a retrieval system can divide into parent and child chunks without losing their central meaning.
"""


class IntakeV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_local_run_uses_source_name_and_builds_knowledge_package(self) -> None:
        source = self.workspace / "Useful Guide.md"
        source.write_text(INFORMATION, encoding="utf-8")
        path, run = start(self.workspace, str(source))
        self.assertEqual(path.name, "useful-guide")
        self.assertEqual(run["status"], "selected")
        from intake_engine import collect
        collected = collect(path)
        self.assertEqual(collected["status"], "ready")
        target = package(path)
        result = validate(path)
        self.assertTrue(result["healthy"], result["errors"])
        self.assertEqual(read_jsonl(target / "manifest.jsonl")[0]["schema_version"], "markdown-document-v1")

    def test_cleanup_removes_byline_contact_and_promotion(self) -> None:
        dirty = INFORMATION + "\nBy: Example Person\nCall +1 212 555 0188\nSubscribe for a special offer\n"
        cleaned = basic_clean(dirty, "Practical source organization", public=True)
        self.assertNotIn("Example Person", cleaned)
        self.assertNotIn("555", cleaned)
        self.assertNotIn("Subscribe", cleaned)
        self.assertIn("Organize each source", cleaned)

    def test_website_selection_is_explicit(self) -> None:
        path = self.workspace / ".knowledge-intake" / "runs" / "example-com"
        for folder in ("manifests", "reports", "prepared", "agent"):
            (path / folder).mkdir(parents=True, exist_ok=True)
        from intake_engine import atomic_json
        inventory = [
            {"url": "https://example.com/guides/a", "group": "guides", "label": "a", "recommended": True, "selected": False, "status": "discovered"},
            {"url": "https://example.com/contact", "group": "contact", "label": "contact", "recommended": False, "selected": False, "status": "discovered"},
        ]
        write_jsonl(path / "inventory.jsonl", inventory)
        atomic_json(path / "run.json", {"run_name": "example-com", "source": "https://example.com/", "source_kind": "website", "status": "discovered", "message": "Choose", "created_at": "x", "updated_at": "x", "inventory_count": 2, "selected_count": 0, "counts": {"found": 0, "cleaned": 0, "review": 0, "ready": 0, "excluded": 0}, "events": []})
        atomic_json(path / "selection.json", {"saved_at": None, "urls": []})
        run = save_selection(path, ["https://example.com/guides/a"])
        self.assertEqual(run["selected_count"], 1)
        selected = [row for row in read_jsonl(path / "inventory.jsonl") if row["selected"]]
        self.assertEqual(selected[0]["group"], "guides")

    def test_agent_review_can_include_supported_scan_text(self) -> None:
        source = self.workspace / "scan.png"
        source.write_bytes(b"placeholder image")
        path, _ = start(self.workspace, str(source))
        from intake_engine import collect
        run = collect(path)
        self.assertEqual(run["status"], "review")
        tasks = read_jsonl(prepare_agent(path))
        write_jsonl(path / "agent" / "results.jsonl", [{
            "task_id": tasks[0]["task_id"], "status": "completed", "decision": "include",
            "cleaned_markdown": INFORMATION, "confidence": .95, "evidence": tasks[0]["evidence"],
            "notes": "Read directly from the source image",
        }])
        applied = apply_agent(path)
        self.assertEqual(applied["counts"]["ready"], 1)

    def test_health_sensitive_agent_result_stays_in_review(self) -> None:
        source = self.workspace / "scan.png"
        source.write_bytes(b"placeholder image")
        path, _ = start(self.workspace, str(source))
        from intake_engine import collect
        collect(path)
        tasks = read_jsonl(prepare_agent(path))
        sensitive = INFORMATION + "\nThis section discusses treatment dosage for an injury.\n"
        write_jsonl(path / "agent" / "results.jsonl", [{
            "task_id": tasks[0]["task_id"], "status": "completed", "decision": "include",
            "cleaned_markdown": sensitive, "confidence": .95, "evidence": tasks[0]["evidence"], "notes": "",
        }])
        applied = apply_agent(path)
        self.assertEqual(applied["status"], "review")
        self.assertEqual(read_jsonl(path / "manifests" / "documents.jsonl")[0]["lane"], "sensitive_review")

    def test_unicode_grouping_and_single_endpoint_consolidation(self) -> None:
        from intake_engine import inventory_group, unicode_slug
        self.assertEqual(unicode_slug("מאמרים"), "מאמרים")
        self.assertEqual(inventory_group("https://example.com/מאמרים/5-דרכים")[0], "מאמרים")
        self.assertTrue(inventory_group("https://example.com/מאמרים/5-דרכים")[1])
        self.assertFalse(inventory_group("https://example.com/upload/image.png")[1])
        self.assertFalse(inventory_group("https://example.com/צור-קשר")[1])


if __name__ == "__main__":
    unittest.main()



