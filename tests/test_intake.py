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

    def test_server_port_fallback_and_lifecycle_endpoints(self) -> None:
        import json
        import threading
        import time
        import urllib.request
        from intake import find_available_server, serve_report
        from intake_engine import atomic_json, render_report

        path = self.workspace / ".knowledge-intake" / "runs" / "test-site"
        for folder in ("manifests", "reports", "prepared", "agent"):
            (path / folder).mkdir(parents=True, exist_ok=True)
        inventory = [
            {"url": "https://example.com/a", "group": "a", "label": "a", "recommended": True, "selected": False, "status": "discovered"},
        ]
        write_jsonl(path / "inventory.jsonl", inventory)
        atomic_json(path / "run.json", {"run_name": "test-site", "source": "https://example.com/", "source_kind": "website", "status": "discovered", "message": "Choose", "created_at": "x", "updated_at": "x", "inventory_count": 1, "selected_count": 0, "counts": {"found": 0, "cleaned": 0, "review": 0, "ready": 0, "excluded": 0}, "events": []})
        atomic_json(path / "selection.json", {"saved_at": None, "urls": []})
        render_report(path)

        # Test port conflict auto-fallback
        from http.server import SimpleHTTPRequestHandler
        server1, port1 = find_available_server("127.0.0.1", 9870, SimpleHTTPRequestHandler)
        self.assertEqual(port1, 9870)
        server2, port2 = find_available_server("127.0.0.1", 9870, SimpleHTTPRequestHandler)
        self.assertEqual(port2, 9871)
        server1.server_close()
        server2.server_close()

        # Start server in thread
        server_thread = threading.Thread(target=serve_report, args=(path, "127.0.0.1", 9880, False, 60), daemon=True)
        server_thread.start()
        time.sleep(0.4)

        base_url = "http://127.0.0.1:9880"
        # Test /api/run
        with urllib.request.urlopen(f"{base_url}/api/run", timeout=2) as resp:
            state = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(state["run_name"], "test-site")

        # Test /api/heartbeat
        req = urllib.request.Request(f"{base_url}/api/heartbeat", data=b'{"client_id": "test_tab_1"}', headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            hb = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(hb["ok"])

        # Test /api/leave
        req = urllib.request.Request(f"{base_url}/api/leave", data=b'{"client_id": "test_tab_1"}', headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            leave = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(leave["ok"])

        # Test /api/select
        req = urllib.request.Request(f"{base_url}/api/select", data=b'{"urls": ["https://example.com/a"]}', headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            sel = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(sel["selected_count"], 1)

        # Test /api/shutdown
        req = urllib.request.Request(f"{base_url}/api/shutdown", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            shut = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(shut["ok"])

        server_thread.join(timeout=3)
        self.assertFalse(server_thread.is_alive())

    def test_server_idle_auto_shutdown(self) -> None:
        import threading
        import time
        from intake import serve_report
        from intake_engine import atomic_json, render_report

        path = self.workspace / ".knowledge-intake" / "runs" / "idle-site"
        for folder in ("manifests", "reports", "prepared", "agent"):
            (path / folder).mkdir(parents=True, exist_ok=True)
        write_jsonl(path / "inventory.jsonl", [])
        atomic_json(path / "run.json", {"run_name": "idle-site", "source": "https://example.com/", "source_kind": "website", "status": "discovered", "message": "Choose", "created_at": "x", "updated_at": "x", "inventory_count": 0, "selected_count": 0, "counts": {"found": 0, "cleaned": 0, "review": 0, "ready": 0, "excluded": 0}, "events": []})
        atomic_json(path / "selection.json", {"saved_at": None, "urls": []})
        render_report(path)

        # Start server with 1s idle timeout
        start_time = time.time()
        server_thread = threading.Thread(target=serve_report, args=(path, "127.0.0.1", 9890, False, 1), daemon=True)
        server_thread.start()

        # Wait for idle shutdown (should finish within ~3-4 seconds)
        server_thread.join(timeout=5)
        self.assertFalse(server_thread.is_alive())
        elapsed = time.time() - start_time
        self.assertLess(elapsed, 5)


if __name__ == "__main__":
    unittest.main()



