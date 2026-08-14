#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from intake_engine import (
    DEFAULT_INVENTORY_LIMIT, DEFAULT_PAGE_LIMIT, apply_agent, collect, doctor, load_run,
    package, prepare_agent, public_state, read_jsonl, run_path, save_selection,
    select_patterns, start, validate,
)

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")



def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="knowledge-intake", description="Inventory first; collect selected information; build clean Markdown knowledge packages.")
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
    serve.add_argument("--idle-timeout", type=int, default=900, help="Seconds of inactivity before auto-shutdown (0 to disable, default 900)")
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


class ResilientHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False


def find_available_server(host: str, initial_port: int, handler_cls: type[BaseHTTPRequestHandler], max_tries: int = 20) -> tuple[ThreadingHTTPServer, int]:
    for offset in range(max_tries):
        port = initial_port + offset
        try:
            server = ResilientHTTPServer((host, port), handler_cls)
            return server, port
        except OSError as exc:
            if offset == max_tries - 1:
                raise exc
    raise OSError(f"Could not bind to any port in range {initial_port}..{initial_port + max_tries - 1}")


def serve_report(path: Path, host: str, port: int, open_browser: bool, idle_timeout: int = 900) -> None:
    last_activity = [time.time()]
    active_clients: dict[str, float] = {}
    is_shutting_down = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            last_activity[0] = time.time()
            if self.path in {"/", "/report.html"}:
                self._send(200, "text/html; charset=utf-8", (path / "report.html").read_bytes())
            elif self.path == "/fonts/barlow-condensed-latin.woff2":
                self._send(200, "font/woff2", (path / "fonts" / "barlow-condensed-latin.woff2").read_bytes())
            elif self.path == "/api/run":
                self._send(200, "application/json; charset=utf-8", json.dumps(public_state(path), ensure_ascii=False).encode())
            else:
                self._send(404, "text/plain; charset=utf-8", b"Not found")

        def do_POST(self) -> None:  # noqa: N802
            last_activity[0] = time.time()
            if self.path == "/api/select":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(min(length, 2_000_000)))
                    run = save_selection(path, list(payload.get("urls") or []))
                    body = json.dumps(public_state(path, run), ensure_ascii=False).encode()
                    self._send(200, "application/json; charset=utf-8", body)
                except Exception as exc:
                    self._send(400, "application/json; charset=utf-8", json.dumps({"error": str(exc)}).encode())
            elif self.path == "/api/heartbeat":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(min(length, 10_000))) if length > 0 else {}
                    client_id = str(payload.get("client_id") or "anonymous")
                    active_clients[client_id] = time.time()
                except Exception:
                    pass
                self._send(200, "application/json; charset=utf-8", json.dumps({"ok": True, "idle_timeout": idle_timeout}).encode())
            elif self.path == "/api/leave":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(min(length, 10_000))) if length > 0 else {}
                    client_id = str(payload.get("client_id") or "")
                    if client_id in active_clients:
                        del active_clients[client_id]
                except Exception:
                    pass
                self._send(200, "application/json; charset=utf-8", json.dumps({"ok": True}).encode())
            elif self.path == "/api/shutdown":
                self._send(200, "application/json; charset=utf-8", json.dumps({"ok": True, "message": "Server shutting down."}).encode())
                is_shutting_down.set()
                threading.Thread(target=server.shutdown, daemon=True).start()
            else:
                self._send(404, "text/plain", b"Not found")

        def log_message(self, format: str, *args: object) -> None:
            return

    server, bound_port = find_available_server(host, port, Handler)
    url = f"http://{host}:{bound_port}/"
    print(f"Live intake report: {url}")
    if bound_port != port:
        print(f"(Port {port} was in use; automatically bound to port {bound_port})")
    if idle_timeout > 0:
        print(f"Auto-shutdown: Server will stop after {idle_timeout}s of inactivity if all tabs are closed.")
    print("Press Ctrl+C or click 'Close Server' in the dashboard to stop; the intake run is preserved.")

    def monitor_idle() -> None:
        while not is_shutting_down.is_set():
            time.sleep(2)
            if is_shutting_down.is_set():
                break
            now_ts = time.time()
            stale_keys = [k for k, v in active_clients.items() if now_ts - v > 35]
            for k in stale_keys:
                del active_clients[k]

            if idle_timeout > 0 and (now_ts - last_activity[0]) > idle_timeout:
                print(f"\nDashboard server stopped automatically after {idle_timeout}s of inactivity.", flush=True)
                is_shutting_down.set()
                threading.Thread(target=server.shutdown, daemon=True).start()
                break

    monitor_thread = threading.Thread(target=monitor_idle, daemon=True)
    monitor_thread.start()

    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        is_shutting_down.set()
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
            serve_report(path, args.host, args.port, args.open, idle_timeout=args.idle_timeout)
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
