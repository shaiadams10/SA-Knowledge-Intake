#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

KEEP = [
    "SKILL.md", "pyproject.toml", "uv.lock", "README.md", "DESIGN.md",
    "AGENTS.md", "agents", "assets", "references", "scripts", "tests"
]
IGNORE = shutil.ignore_patterns(
    ".venv", "__pycache__", "*.pyc", ".git", ".knowledge-intake",
    ".pytest_cache", ".coverage", "scratch"
)


def compute_hash(path: Path) -> str:
    """Compute deterministic SHA256 digest of a file or directory tree."""
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    hasher = hashlib.sha256()
    for child in sorted(path.rglob("*")):
        if child.is_file() and not any(p in child.parts for p in [".venv", "__pycache__", ".git", ".knowledge-intake"]):
            rel = str(child.relative_to(path)).replace("\\", "/")
            hasher.update(rel.encode())
            hasher.update(child.read_bytes())
    return hasher.hexdigest()


def detect_target_dir(project_path: Path) -> Path:
    """Detect appropriate agent skill directory for the project."""
    # Check if custom skill folder already exists
    for candidate in [
        project_path / ".agents" / "skills" / "knowledge-intake",
        project_path / ".gemini" / "antigravity" / "skills" / "knowledge-intake",
        project_path / ".codex" / "skills" / "knowledge-intake",
        project_path / ".claude" / "skills" / "knowledge-intake",
    ]:
        if candidate.parent.exists():
            return candidate
    return project_path / ".agents" / "skills" / "knowledge-intake"


def install(source: Path, target: Path, check_only: bool = False) -> tuple[bool, str]:
    target.mkdir(parents=True, exist_ok=True)
    is_up_to_date = True
    changes = []

    for name in KEEP:
        src = source / name
        dst = target / name
        if not src.exists():
            continue

        if src.is_dir():
            if not dst.exists() or compute_hash(src) != compute_hash(dst):
                is_up_to_date = False
                changes.append(f"[update] {name}/")
                if not check_only:
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst, ignore=IGNORE)
        else:
            if not dst.exists() or compute_hash(src) != compute_hash(dst):
                is_up_to_date = False
                changes.append(f"[update] {name}")
                if not check_only:
                    shutil.copy2(src, dst)

    if check_only:
        if is_up_to_date:
            return True, f"Knowledge Intake is already up to date at: {target}"
        return False, f"Updates available for: {target}\nChanges:\n  " + "\n  ".join(changes)

    return True, f"Installed/Updated Knowledge Intake successfully into:\n  {target}"


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="install_skill",
        description="Install or update the canonical Knowledge Intake skill into any project or agent environment."
    )
    parser.add_argument("target", nargs="?", default=".", help="Target project root directory or explicit skill path (default: current directory)")
    parser.add_argument("--global", "-g", dest="is_global", action="store_true", help="Install into global user skills directory (~/.codex/skills or ~/.gemini/antigravity/skills)")
    parser.add_argument("--check", action="store_true", help="Check if the target skill installation is up to date without modifying files")
    args = parser.parse_args()

    source = Path(__file__).resolve().parent.parent

    if args.is_global:
        home = Path.home()
        # Prefer existing global agent folders
        if (home / ".gemini" / "antigravity" / "skills").exists():
            target = home / ".gemini" / "antigravity" / "skills" / "knowledge-intake"
        elif (home / ".codex" / "skills").exists():
            target = home / ".codex" / "skills" / "knowledge-intake"
        elif (home / ".claude" / "skills").exists():
            target = home / ".claude" / "skills" / "knowledge-intake"
        else:
            target = home / ".agents" / "skills" / "knowledge-intake"
    else:
        target_input = Path(args.target).expanduser().resolve()
        if target_input.name == "knowledge-intake" and (target_input / "SKILL.md").exists():
            target = target_input
        elif target_input.is_dir():
            target = detect_target_dir(target_input)
        else:
            target = detect_target_dir(target_input)

    success, message = install(source, target, check_only=args.check)
    print(message)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
