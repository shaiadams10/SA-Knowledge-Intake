# Knowledge Intake

Canonical project for the portable `$knowledge-intake` coding-agent skill.

The workflow inventories a source, lets the user select useful website sections in a live local report, collects only that selection, gives uncertain items to the current coding agent, and produces validated `dify-markdown-v1` output. It does not use a local LLM and does not upload to Dify.

```powershell
uv sync
uv run crawl4ai-setup
uv run python scripts/intake.py start https://example.com
uv run python scripts/intake.py serve example-com --open
```

Install or refresh the skill in another project:

```powershell
python scripts/install_skill.py D:\Projects\TargetProject
```

