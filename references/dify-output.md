# Dify-ready output contract

## Package boundary

Only the `package/` directory is intended for downstream import. Evidence, source URLs, crawl notes, review tasks, and private paths remain outside it.

```text
package/
  articles/
    knowledge-<public-id>.md
  manifest.jsonl
  package.json
  README.md
```

## Markdown profile: `dify-markdown-v1`

Each article must:

- be UTF-8 Markdown;
- contain exactly one descriptive H1;
- use H2/H3 headings for stable semantic sections;
- use complete paragraphs with blank lines between them;
- preserve factual wording, units, table relationships, and useful citations;
- contain no YAML frontmatter, raw HTML, image syntax, contact details, social links, local paths, crawl diagnostics, model notes, or promotional calls to action;
- end on a complete sentence or a structurally complete list/table;
- contain enough standalone context to remain meaningful after Dify chunks it.

Do not pre-split into tiny arbitrary chunks. Dify can apply parent-child chunking to these coherent documents later.

## Manifest profile

`manifest.jsonl` contains one object per article:

```json
{
  "schema_version": "dify-markdown-document-v1",
  "run_name": "example-com",
  "document_id": "6dbfa2c5d96e2ca1",
  "title": "Example guide",
  "language": "en",
  "path": "articles/knowledge-6dbfa2c5d96e2ca1.md",
  "sha256": "...",
  "word_count": 842
}
```

The public document ID is source-neutral. Original provenance exists only in the internal manifests.

## Import behavior

The package is compatible with Dify document upload but does not contain dataset IDs, credentials, chunk settings, or an upload action. A later importer may upload `articles/*.md`, use `manifest.jsonl` for idempotency, and choose dataset-specific indexing settings separately.

