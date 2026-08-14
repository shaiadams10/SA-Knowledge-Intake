# Knowledge Package Output Contract

## Package Boundary

Only the `package/` directory is intended for downstream import into knowledge bases, vector databases, or RAG pipelines. Raw crawl artifacts, review tasks, and temporary source paths remain safely outside it.

```text
package/
  articles/
    <readable-ascii-title>--<8-character-public-id>.md
  manifest.jsonl
  package.json
  README.md
```

## Markdown Profile: `markdown-knowledge-v1`

Each article must:

- be UTF-8 Markdown;
- contain exactly one descriptive top-level `# H1` heading;
- use `## H2` and `### H3` headings for stable semantic sections;
- use complete paragraphs with blank lines between them;
- preserve factual wording, numeric units, table relationships, and useful definitions;
- contain no YAML frontmatter, raw HTML tags, broken image syntax, personal contact details, social links, local paths, crawl diagnostics, or promotional calls to action;
- end on a complete sentence or a structurally complete list/table;
- contain enough standalone context to remain meaningful during vector chunking.

Do not pre-split into tiny arbitrary fragments. Downstream retrieval systems can apply semantic or parent-child chunking to these coherent documents cleanly.

## Manifest Profile

`manifest.jsonl` contains one object per article:

```json
{
  "schema_version": "markdown-document-v1",
  "run_name": "example-com",
  "document_id": "6dbfa2c5d96e2ca1",
  "title": "Example guide",
  "language": "en",
  "path": "articles/example-guide--6dbfa2c5.md",
  "sha256": "...",
  "word_count": 842
}
```

The public document ID is clean and source-neutral. Original provenance is preserved in internal manifests. Article filenames combine a lowercase ASCII title slug with the first eight characters of that stable ID, for example `plant-vs-animal-protein--4df9b891.md`. The full ID remains authoritative in `document_id`; filenames are readable transport labels, not identity keys. If a title has no ASCII representation, use `knowledge` as the portable fallback slug.

Regenerating a package applies this convention only to that newly generated package. It does not rename files in earlier packages or documents already imported into a downstream knowledge base. Consumers must use `manifest.jsonl` document IDs and digests, rather than filenames alone, for incremental identity and update decisions.

## Import Behavior

The package is universal and self-contained:
- Ingest `articles/*.md` into any Knowledge Base, RAG pipeline, or document store.
- Use `manifest.jsonl` SHA-256 digests for idempotency and incremental updates.
- Indexing and embedding strategies can be applied independently downstream.
