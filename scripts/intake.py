#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from intake_engine import (
    DEFAULT_INVENTORY_LIMIT, DEFAULT_PAGE_LIMIT, apply_agent, collect, doctor, load_run,
    package, prepare_agent, public_state, read_jsonl, run_path, save_selection,
    select_patterns, start, validate,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="knowledge-intake", description="Inventory first; collect selected information; build Dify-ready Markdown.")
    root.add_argument("--workspace", default=".")
    commands = root.add_subparsers(dest="command", required=True)
    check = commands.add_parser("doctor")
    check.add_argument("--json", action="store_true")
    begin = commands.add_parser("start")
    begin.add_argument("source")
    begin.add_argument("--name")
    begin.add_argument("--inventory-limit", type=int, default=DEFAULT_INVENTORY_LIMIT)
    begin.add_argument("--json", action="store_true")
    show = commands.add_parser("status")
    show.add_argument("name")
    show.add_argument("--json", action="store_true")
    serve = commands.add_parser("serve")
    serve.add_argument("name")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--open", action="store_true")
    choose = commands.add_parser("select")
    choose.add_argument("name")
    choose.add_argument("--include", action="append", default=[])
    choose.add_argument("--recommended", action="store_true")
    choose.add_argument("--json", action="store_true")
    gather = commands.add_parser("collect")
    gather.add_argument("name")
    gather.add_argument("--max-pages", type=int, default=DEFAULT_PAGE_LIMIT)
    gather.add_argument("--json", action="store_true")
    needs = commands.add_parser("needs")
    needs.add_argument("name")
    needs.add_argument("--json", action="store_true")
    prep = commands.add_parser("prepare-agent")
    prep.add_argument("name")
    apply = commands.add_parser("apply-agent")
    apply.add_argument("name")
    apply.add_argument("--json", action="store_true")
    build = commands.add_parser("package")
    build.add_argument("name")
    build.add_argument("--json", action="store_true")
    verify = commands.add_parser("validate")
    verify.add_argument("name")
    verify.add_argument("--json", action="store_true")
    return root


def emit(value: object, as_json: bool = True) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2) if as_json else str(value))


def serve_report(path: Path, host: str, port: int, open_browser: bool) -> None:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/", "/report.html"}:
                self._send(200, "text/html; charset=utf-8", (path / "report.html").read_bytes())
            elif self.path == "/fonts/barlow-condensed-latin.woff2":
                self._send(200, "font/woff2", (path / "fonts" / "barlow-condensed-latin.woff2").read_bytes())
            elif self.path == "/api/run":
                self._send(200, "application/json; charset=utf-8", json.dumps(public_state(path), ensure_ascii=False).encode())
            else:
                self._send(404, "text/plain; charset=utf-8", b"Not found")

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/select":
                self._send(404, "text/plain", b"Not found")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(min(length, 2_000_000)))
                run = save_selection(path, list(payload.get("urls") or []))
                body = json.dumps(public_state(path, run), ensure_ascii=False).encode()
                self._send(200, "application/json; charset=utf-8", body)
            except Exception as exc:
                self._send(400, "application/json; charset=utf-8", json.dumps({"error": str(exc)}).encode())

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"Live intake report: {url}")
    print("Press Ctrl+C to stop the report server; the intake run is preserved.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> int:
    args = parser().parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        if args.command == "doctor":
            result = doctor()
            emit(result)
            return 0 if result["healthy"] else 2
        if args.command == "start":
            if not 1 <= args.inventory_limit <= 10000:
                raise ValueError("--inventory-limit must be between 1 and 10000")
            path, run = start(workspace, args.source, name=args.name, inventory_limit=args.inventory_limit)
            emit({"run_name": run["run_name"], "status": run["status"], "inventory_count": run["inventory_count"], "folder": str(path), "report": str(path / "report.html"), "next": "Open the live report and save a selection." if run["source_kind"] == "website" else "Run collect."})
            return 0
        path = run_path(workspace, args.name)
        if args.command == "status":
            emit(public_state(path))
        elif args.command == "serve":
            serve_report(path, args.host, args.port, args.open)
        elif args.command == "select":
            if not args.include and not args.recommended:
                raise ValueError("Use --include PATTERN or --recommended.")
            run = select_patterns(path, args.include, args.recommended)
            emit({"run_name": run["run_name"], "status": run["status"], "selected_count": run["selected_count"]})
        elif args.command == "collect":
            run = collect(path, args.max_pages)
            emit({"run_name": run["run_name"], "status": run["status"], "counts": run["counts"], "next": "Review queued items." if run["status"] == "review" else "Build the package."})
        elif args.command == "needs":
            queue = read_jsonl(path / "manifests" / "review_queue.jsonl")
            emit({"run_name": args.name, "count": len(queue), "items": queue})
        elif args.command == "prepare-agent":
            print(prepare_agent(path))
        elif args.command == "apply-agent":
            run = apply_agent(path)
            emit({"run_name": run["run_name"], "status": run["status"], "counts": run["counts"]})
        elif args.command == "package":
            target = package(path)
            emit({"run_name": args.name, "package": str(target), "status": load_run(path)["status"]})
        elif args.command == "validate":
            result = validate(path)
            emit(result)
            return 0 if result["healthy"] else 1
        return 0
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"Could not complete this step: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
