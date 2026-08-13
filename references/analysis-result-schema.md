# Agent review result

Write UTF-8 JSONL to `agent/results.jsonl`, one object per task:

```json
{
  "task_id": "task-0123456789ab",
  "status": "completed",
  "decision": "include",
  "cleaned_markdown": "# Useful title\n\nFaithfully recovered information...",
  "confidence": 0.93,
  "evidence": ["evidence/source/guide.pdf"],
  "notes": "Short uncertainty note"
}
```

- `status`: `completed` or `unresolved`.
- `decision`: `include`, `exclude`, or `review`.
- `cleaned_markdown`: required for `include`; one H1 and only faithfully supported information.
- `confidence`: 0 to 1. Inclusion requires at least 0.80.
- `evidence`: run-relative paths already present in the task.
- Never infer unreadable words, hidden chart values, identities, or medical conclusions.
- Use `review` for sensitive claims or material that needs user judgment.

