#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


KEEP = ["SKILL.md", "pyproject.toml", "uv.lock", "agents", "assets", "references", "scripts", "tests"]
IGNORE = shutil.ignore_patterns(".venv", "__pycache__", "*.pyc", ".git", ".knowledge-intake", "install_skill.py")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the canonical Knowledge Intake skill into a project.")
    parser.add_argument("project_root")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent.parent
    project = Path(args.project_root).expanduser().resolve()
    if not project.is_dir():
        raise SystemExit(f"Project folder not found: {project}")
    target = project / ".agents" / "skills" / "knowledge-intake"
    target.mkdir(parents=True, exist_ok=True)
    for name in KEEP:
        src = source / name
        dst = target / name
        if not src.exists():
            continue
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=IGNORE)
        else:
            shutil.copy2(src, dst)
    print(f"Installed Knowledge Intake from {source} to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
