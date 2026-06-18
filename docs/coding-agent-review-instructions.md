# Coding Agent Review Instructions

Use this checklist when reviewing and promoting the multi-table routing work.

## Current branch targeting

- Working branch: `copilot/handle-multiple-tables`
- Preferred merge target: `baseline/main-tree-2026-06-17`
- Current comparison at the time this file was written: working branch is `5` commits ahead of `baseline/main-tree-2026-06-17`, and baseline is `0` commits ahead of the working branch.
- Do **not** treat `main` as the primary validation branch until the baseline branch has been validated.

## Scope of the review

Confirm the branch contains these changes:
- multi-table SQL loading with primary/supplemental table roles
- `lookup_part_details` supplemental lookup tool
- system prompt routing that keeps scrap/status questions on the primary table and product-detail questions on the supplemental table

Reference document: `/home/runner/work/PY_CHAT_AGENT/PY_CHAT_AGENT/docs/feature-multi-table-routing.md`

## 1. Prepare real SQL test data locally

Before local validation, update the real SQL test environment so it includes the supplemental table used by this feature.

Required setup:
- set `DATASOURCE=sql`
- configure `SQL_SERVER`, `SQL_DATABASE`, and authentication settings in `.env`
- set `SQL_TABLES` to include both the obsolescence table and `production.dimProducts`
- set `SQL_PRIMARY_TABLE` to the obsolescence table
- keep `SQL_TABLE` available only for backward-compatibility checks

Data requirement:
- create or refresh `production.dimProducts` in the same SQL Server database used for validation
- use the DDL and seed expectations documented in `/home/runner/work/PY_CHAT_AGENT/PY_CHAT_AGENT/docs/feature-multi-table-routing.md`
- ensure at least some `PartNumber` values exist in both the primary table and `production.dimProducts`
- ensure there are also rows present only in the supplemental table so routing and negative cases can be checked

## 2. Run scripted validation locally

From the repository root:

```bash
python -m pip install pytest -r requirements.txt
python -m pytest main_test.py tests/ -v
```

Notes:
- one existing path-traversal test may already be failing in this environment; review whether that remains unrelated to this feature before blocking promotion
- if new tests are added for multi-table SQL behavior, they must pass against the local SQL-backed configuration

## 3. Run manual local validation

After the SQL tables are updated, start the app locally and verify end-to-end behavior.

```bash
python main.py
```

Open `http://localhost:3978` and manually verify:
- scrap/status/disposition questions still resolve against the primary table
- product description, phase, and product-flag questions resolve against `production.dimProducts`
- responses do not mix primary and supplemental columns in the same answer
- part numbers present in both tables behave correctly
- part numbers present only in one table return the expected fallback behavior

Recommended manual prompts:
- ask whether a known part can be scrapped
- ask for the description of the same known part
- ask for `Phase` on a known supplemental-only part
- ask for a product-flag case such as `International_PowerCord` or `CustomButton`

## 4. Merge into baseline and validate again

After local review is complete:
- merge `copilot/handle-multiple-tables` into `baseline/main-tree-2026-06-17`
- re-run the same scripted tests on the baseline branch
- repeat the same manual local checks on the baseline branch
- confirm no customer-tested behavior regressed while incorporating this feature

## 5. Promote baseline into actual main

Only after the baseline branch is validated:
- merge `baseline/main-tree-2026-06-17` into `main`
- re-run scripted tests on `main`
- run another manual local smoke test on `main`
- verify environment settings for any deployment target still match the SQL multi-table configuration

## 6. Validate after deployment

After deploying the promoted code:
- verify the app loads successfully in the deployed environment
- verify both configured SQL tables are available in runtime configuration
- repeat smoke tests for scrap/status queries and supplemental detail queries
- confirm download/export and auth behavior still work as expected
- check logs for SQL loading errors, missing table configuration, or prompt-routing regressions

## 7. Cross-check against the customer's codebase

A separate comparison should be done before shipping back to the customer.

When ready, request the customer code path and then compare:
- prompt content and routing instructions
- SQL environment variable names and values
- table names and schemas
- manual test prompts and expected responses
- any local patches in the customer branch that are not yet present here
- deployment settings that could affect SQL loading or authentication

Do not finalize customer delivery until this comparison is complete.

## 8. Final sign-off checklist

- [ ] real SQL supplemental table is populated for testing
- [ ] scripted tests reviewed locally
- [ ] manual local SQL validation completed
- [ ] merged and re-validated on `baseline/main-tree-2026-06-17`
- [ ] merged and re-validated on `main`
- [ ] deployed environment smoke-tested
- [ ] customer codebase comparison completed after obtaining the customer path
