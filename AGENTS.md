# KnowledgeIntake

This folder is the canonical source of truth for the portable Knowledge Intake skill. Make all future skill changes here, test them here, then run `python scripts/install_skill.py <project-root>` to refresh a project-local installation.

## Commands

- Sync dependencies: `uv sync`
- Check runtime: `uv run python scripts/intake.py doctor --json`
- Run tests: `uv run python -m unittest discover -s tests -v`
- Validate skill metadata: `python C:\Users\shaib\.codex\skills\.system\skill-creator\scripts\quick_validate.py .`
- Install into a project: `python scripts/install_skill.py <project-root>`

## Boundaries

- No local or cloud LLM runtime belongs in this project.
- The current coding agent performs OCR/visual judgment through `agent/tasks.jsonl` and `agent/results.jsonl`.
- Keep source evidence immutable, preserve factual meaning, and route uncertainty to review.
- The package format is `dify-markdown-v1`, but this project never uploads to Dify.
- Use deterministic IDs, atomic writes, source-named runs, and bounded website inventory/crawls.

