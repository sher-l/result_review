# Automated Audit Hardening

This guide describes the extra guardrails added on top of the existing audit framework.

## What Was Added

1. `audit_state.json`
   - Generated in `result_review_report/<project_id>/`
   - Tracks the current phase of the audit
   - Prevents step skipping

2. `final_report_linter.py`
   - Checks whether the final markdown report is structurally complete
   - Verifies required companion files exist
   - Blocks vague close-out text from being treated as complete

3. `convergence_compare.py`
   - Validates the three agent JSON payloads
   - Aggregates `mechanical_dispositions`
   - Aggregates `high_risk_modules`
   - Requires structured evidence fields on every finding

4. `build_rereview_diff.py`
   - Compares two review directories
   - Summarizes changed files and changed issue bullets
   - Makes targeted re-review possible instead of repeating full first-pass review

## Required Finding Evidence Fields

Every agent finding should carry:

- `source_type`
- `source_path`
- `locator`
- `quote_or_value`

If any one of these is missing, the finding is incomplete.

## Recommended Execution Order

1. Run `auto_audit_pipeline.py`
2. Read `ai_execution_manifest.json`
3. Read `audit_state.json`
4. Finish visual audit
5. Run the three subagents
6. Save all three `agent_*_result.json`
7. Run `convergence_compare.py`
8. Write markdown deliverables
9. Run `final_report_linter.py`
10. Run `sync_audit_state.py`
11. Export HTML

## Re-review Mode

If there is an older review directory for the same project or for the previous re-review round:

1. Run `build_rereview_diff.py <old_review_dir> <new_review_dir>`
2. Review the diff first
3. Only reopen changed files, unresolved items, and newly added evidence

This reduces repeated work and makes the re-review decision path explicit.

## New Recurrent Guardrails

After multiple recent audits, the following patterns should be treated as first-class guardrails rather than ad hoc reviewer memory:

1. Delivery-root flexibility
   - Do not assume every project uses `结果文件/`.
   - Formal delivery may instead be organized as `分析结果/` + `代码/` + `附件-前期结果/`.
   - Precheck scripts should classify these roots explicitly before judging module absence.

2. High-risk text-vs-files mismatch
   - If the report claims molecular dynamics, docking, or similar high-risk results, the agent must verify both:
   - the result directory is non-empty
   - the referenced figures actually exist in extracted images or delivered files
   - “Text has figure numbers but files are empty” should be treated as a blocking pattern.

3. Docking-to-MD selection consistency
   - When the report says MD uses the “lowest binding energy” complex, the reviewer must compare the score table with the named MD target.
   - Any mismatch is a method-result consistency finding, not a wording nit.

4. DEG table-type discrimination
   - A file inside a DEG directory is not automatically a DEG result table.
   - Agents should distinguish expression matrices from true DEG outputs by checking for columns such as `logFC`, `padj`, `pvalue`, `adj.P.Val`, `regulation`, or equivalent differential-analysis fields.

5. Figure numbering continuity
   - Figure ranges stated in正文 should be checked against the actual captions.
   - Patterns like `Fig.6-1` followed by `Fig.10-2` / `Fig.10-3` should be auto-raised as figure-consistency issues.
