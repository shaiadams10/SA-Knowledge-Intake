# Knowledge Package Output Contract

## Package Boundary

Only the `package/` directory is intended for downstream import into knowledge bases, vector databases, or RAG pipelines. Raw crawl artifacts, review tasks, and temporary source paths remain safely outside it.

```text
package/
  articles/
    knowledge-<public-id>.md
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
  "path": "articles/knowledge-6dbfa2c5d96e2ca1.md",
  "sha256": "...",
  "word_count": 842
}
```

The public document ID is clean and source-neutral. Original provenance is preserved in internal manifests.

## Import Behavior

The package is universal and self-contained:
- Ingest `articles/*.md` into any Knowledge Base, RAG pipeline, or document store.
- Use `manifest.jsonl` SHA-256 digests for idempotency and incremental updates.
- Indexing and embedding strategies can be applied independently downstream.
