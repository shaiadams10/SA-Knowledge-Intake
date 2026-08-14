---
name: knowledge-intake
description: Turn websites, HTML, Markdown, text, PDFs, scans, and images into a clean, traceable, reviewable Markdown package ready for LLM knowledge bases and RAG retrieval. Always use when a user starts with `intake:` or invokes `$knowledge-intake`; also use for requests to inventory, crawl, select, clean, OCR, interpret, normalize, or prepare knowledge sources. The workflow inventories first, lets the user select relevant website sections in a live HTML report, collects only the selection, delegates uncertain reading to the current coding agent, and never uses or launches a local LLM.
---

# Knowledge Intake

Create a source-named intake folder containing evidence, a live report, a review queue, and a structured Markdown knowledge package. Use the current coding agent for judgment, OCR, and image interpretation when deterministic extraction is insufficient.

## Trigger

Treat these as explicit invocations:

```text
intake: https://example.com
intake: ./sources/guide.pdf
$knowledge-intake https://example.com
```

When invoked, begin the workflow. Do not only explain it.

## 1. Check the portable runtime

Set the canonical project or installed-skill directory as `INTAKE_HOME`, then run:

```powershell
uv run --project $env:INTAKE_HOME python "$env:INTAKE_HOME/scripts/intake.py" doctor
```

If Crawl4AI's browser is missing, run the setup command printed by `doctor`.

## 2. Inventory first (Websites require human selection)

```powershell
uv run --project $env:INTAKE_HOME python "$env:INTAKE_HOME/scripts/intake.py" start <SOURCE>
```

Runs live under `.knowledge-intake/runs/<source-name>/`, for example `.knowledge-intake/runs/example-com/` or `.knowledge-intake/runs/guide/`.

### For Website Sources:
1. `start` performs a fast sitemap/link inventory only. It does not render every page.
2. Launch the interactive proof-sheet report:

```powershell
uv run --project $env:INTAKE_HOME python "$env:INTAKE_HOME/scripts/intake.py" serve <source-name> --open
```

3. **CRITICAL STOP DIRECTIVE**: After running `serve --open`, you **MUST STOP calling tools immediately** and yield the turn to the user. Output the dashboard URL (e.g. `http://127.0.0.1:8765/`) and instruct the user to review the endpoints, click **Save selection**, and confirm when ready.
4. **DO NOT** autonomously run `select` or `collect` in the same turn, even if the input URL contained a specific subpath.
5. **DO NOT** use CLI `select` (`--include`) unless the user explicitly requested a headless/automated batch run without an interactive UI.

The dashboard server automatically handles port conflicts (rebinding to 8766+ if 8765 is busy) and auto-shuts down after 15 minutes of inactivity or when the user clicks **Close Server**. Saved selections are stored permanently in `selection.json`.

### For Local Files (PDFs, Markdown, images, text):
Local sources are selected automatically upon `start`. You may proceed directly to Step 3.

## 3. Collect only the selection

Wait until the user confirms their selection is saved, then run:

```powershell
uv run --project $env:INTAKE_HOME python "$env:INTAKE_HOME/scripts/intake.py" collect <source-name>
```

The collector runs selected web pages concurrently through Crawl4AI. Local Markdown/HTML/text is read directly. Text-bearing PDFs use deterministic PDF extraction. Scans and meaningful images enter the agent review queue instead of starting a local model service.

## 4. Handle the review queue as the current agent

```powershell
uv run --project $env:INTAKE_HOME python "$env:INTAKE_HOME/scripts/intake.py" needs <source-name> --json
uv run --project $env:INTAKE_HOME python "$env:INTAKE_HOME/scripts/intake.py" prepare-agent <source-name>
```

Read `agent/tasks.jsonl`. Inspect each referenced evidence item with the coding agent's available browser, PDF, OCR, or image tools. Write `agent/results.jsonl` following `references/analysis-result-schema.md`, then apply:

```powershell
uv run --project $env:INTAKE_HOME python "$env:INTAKE_HOME/scripts/intake.py" apply-agent <source-name>
```

Never invent unreadable text or missing visual meaning. Leave uncertain and health-sensitive material in review. Ask the user one consolidated question only when judgment is genuinely required.

## 5. Package and validate

```powershell
uv run --project $env:INTAKE_HOME python "$env:INTAKE_HOME/scripts/intake.py" package <source-name>
uv run --project $env:INTAKE_HOME python "$env:INTAKE_HOME/scripts/intake.py" validate <source-name>
```

Hand off `.knowledge-intake/runs/<source-name>/package/`. Its contract is documented in `references/package-contract.md`:

- `articles/*.md`: UTF-8, one top-level H1, structured headings and paragraphs, no frontmatter, raw HTML, broken images, source branding, contacts, promotions, or diagnostics. New packages use portable readable filenames such as `plant-vs-animal-protein--4df9b891.md`; the manifest's full `document_id` remains the stable identity.
- `manifest.jsonl`: one integrity row per Markdown document with SHA-256 digests.
- `package.json`: schema, run details, counts, and compatibility declaration.

## Cleanup policy

Apply cleanup in this order:

1. Remove scripts, styles, navigation, footer, forms, cookie overlays, and hidden UI.
2. Remove short lines repeated across many selected pages (shared menus, slogans, and chrome).
3. Remove contact blocks, phone numbers, email addresses, social handles/links, author/byline labels, and local paths.
4. Remove calls to buy, subscribe, book, register, follow, share, download an offer, or contact sales.
5. Remove empty, fragmentary, duplicate, login, legal, cart, tag/archive, search, and utility pages.
6. Preserve informational prose, headings, tables, units, citations, and names that are materially part of the information. Never erase a person's name merely because it is a name.
7. Route ambiguous, scan-dependent, image-dependent, or sensitive claims to review rather than guessing.

Read `references/protocol.md` for state and folder details, `references/analysis-result-schema.md` for agent results, and `references/package-contract.md` for the final package contract.
