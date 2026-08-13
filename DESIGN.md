---
name: Knowledge Intake Report
description: A prepress proof-sheet visual system for bounded, auditable knowledge intake.
colors:
  paper: "#f1ecdf"
  paper-deep: "#e4dbc7"
  sheet: "#faf7ed"
  ink: "#171915"
  muted: "#666257"
  rule: "#aaa08c"
  signal: "#e34b2f"
typography:
  display: '"Barlow Condensed Intake", sans-serif'
  body: 'Georgia, "Times New Roman", serif'
  label: '"Cascadia Mono", Consolas, monospace'
---

# Knowledge Intake report design

The report is a deliberately physical prepress proof sheet: warm paper, dark ink,
hairline rules, production marks, and one vermilion signal color. It must feel
auditable and calm, not like a generic application dashboard.

Desktop uses a bordered sheet, an asymmetric masthead, a compact statistics row,
and a selection/progress workbench. At 780px and below it becomes one long proof
with no horizontal overflow. Long URLs, IDs, and Hebrew or English text wrap.

Use the self-hosted Barlow Condensed face for uppercase display text, Georgia for
readable prose, and monospace only for operational labels and evidence. Everything
is square and print-like: no rounded cards, gradients, glass effects, decorative
color bands, or icon substitutes. Status meaning must always be expressed in text
as well as color, and keyboard focus must remain visible.

Rows are divided by rules rather than cards. The current action may use one dark
ink panel. Signal red is reserved for active attention and registration marks;
completed states use ink and a faint neutral fill.
