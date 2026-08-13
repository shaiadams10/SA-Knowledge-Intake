# Knowledge intake protocol

## State machine

`discovered -> selected -> collecting -> collected -> review | ready -> packaged -> validated`

Website discovery is deliberately cheap: inventory URLs first, then render only the pages the user selected. Local files begin selected.

## Source-named run

```text
.knowledge-intake/runs/<source-name>/
  run.json
  status.json
  report.html
  inventory.jsonl
  selection.json
  evidence/
  prepared/
  agent/tasks.jsonl
  agent/results.jsonl
  manifests/source_snapshot.jsonl
  manifests/documents.jsonl
  manifests/review_queue.jsonl
  package/articles/*.md
  package/manifest.jsonl
  package/package.json
  reports/validation.json
```

Website names use the hostname without `www` and with filesystem-safe hyphens. Local sources use the filename stem. A repeated `start` for the same source refreshes inventory in the same folder; a name collision with a different source fails and asks for `--name`.

## Inventory groups

Group website URLs by their first meaningful path segment. Mark common noise groups (`account`, `author`, `cart`, `checkout`, `contact`, `legal`, `login`, `privacy`, `search`, `tag`, `terms`) as not recommended. The report shows counts and example URLs; the user controls the saved selection.

## Cleanup gates

- Page-level: remove DOM chrome and obvious promotional/contact/byline lines.
- Corpus-level: remove normalized short lines repeated on at least 35% of selected pages, with a minimum of three occurrences.
- Duplicate-level: compare normalized content hashes and retain one canonical document.
- Quality-level: exclude fragments and utility pages; review image/scan dependencies and sensitive claims.
- Package-level: strip provenance, contacts, URLs, raw HTML, and diagnostics; validate one H1 and substantive content.

Names inside informational content are preserved. Only labeled bylines, author cards, contacts, and repeated site identity are removed automatically.

## Live report

`serve` runs a loopback-only standard-library HTTP server. The report polls `/api/run` for small status updates and posts selection to `/api/select`. It never sends source content to a remote service. Closing the server does not affect the run.

