# Framework Hardening Progress (2026-04-17)

## New borrowings already landed

### 1. Action-suggester style remediation
- `final_report_linter.py` now outputs `suggested_fixes`
- each failed lint item is paired with a concrete next action
- this turns lint from pure blocking into actionable repair guidance

### 2. Baseline / ignore mechanism
- `audit_policy.json` now supports:
  - `lint_policy.ignore_external_url_patterns`
  - `lint_policy.ignored_warning_prefixes`
- this borrows the idea used by tools like `lychee` and other lint baselines
- result: known noisy warnings can be suppressed in policy instead of being hand-waved in reports

### 3. Markdown structure as a real gate
- final deliverables are now checked for:
  - multiple H1 headings
  - heading level jumps
  - empty sections
  - placeholder text
  - broken internal anchors
  - broken local links
  - failing external links

### 4. Link cache + terminology policy
- external link checks now write `lint_link_cache.json`
- repeated lint runs reuse recent link-check results instead of probing the same URLs every time
- audit wording is now policy-driven:
  - forbidden phrases like `人工复核`
  - preferred phrases like `AI复核 / AI处置 / AI裁定`
- warning families can now be escalated to errors by policy prefix

### 5. Autofix-aware lint output
- `suggested_fixes` now includes:
  - `autofix_safe`
  - `patch_hint`
- this makes the next AI step much easier because it can distinguish:
  - safe mechanical cleanup
  - items that still need judgment

### 6. Machine-readable autofix plan
- new script: `generate_lint_autofix_plan.py`
- output: `lint_autofix_plan.json`
- current supported safe actions:
  - remove placeholder-like terms
  - delete empty heading lines
  - replace forbidden terminology with policy replacements
- this pushes lint one step closer to deterministic repair instead of manual interpretation

### 7. Safe autofix executor
- new script: `apply_lint_autofix_plan.py`
- output: `lint_autofix_apply_report.json`
- supports deterministic line-based execution for the safe subset
- records:
  - `applied`
  - `already_applied`
  - `conflict`
- this closes the loop from lint -> plan -> execution -> re-lint

### 8. Required-section backfill chain
- new scripts:
  - `generate_required_section_backfill.py`
  - `apply_required_section_backfill.py`
- outputs:
  - `final_report_backfill_plan.json`
  - `final_report_backfill_apply_report.json`
- current goal:
  - reconstruct missing required sections from existing deliverables instead of forcing manual rewrite
- current targets:
  - `three_agent_convergence`
  - `mechanical_disposition`
  - `high_risk_modules`

### 9. Nested section false-positive reduction
- `final_report_linter.py` no longer flags a heading as an empty section when that heading is immediately followed by child headings
- this matters because audit reports often use parent sections as containers for structured sub-sections
- result:
  - fewer false positives after required-section backfill
  - cleaner `lint -> backfill -> re-lint` convergence

## Why this matters

Previously the framework was strongest at checking analysis content, but weaker at judging the quality of the audit deliverables themselves.

The new direction makes the framework stricter in two ways:

1. It blocks under-specified audit outputs earlier.
2. It gives the next AI step explicit repair instructions instead of only saying "warning".

## Recommended next hardening targets

1. Add richer patch strategies for safe sections, not only single-line replace/delete.
2. Expand section backfill coverage beyond `three_agent_convergence` to `mechanical_disposition` and `high_risk_modules`.
3. Add a broader terminology style layer for standard audit wording, similar to Vale/textlint rule packs.
4. Add cache invalidation/reporting visibility so lint output can show whether a link result came from cache or live probing.
