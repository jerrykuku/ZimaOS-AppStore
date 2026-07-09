# Findings & Decisions

## Requirements
- User wants a multi-action publishing system inside the repo.
- PR validation should auto-run and produce an HTML report.
- V2 store build should use `build-appstore-action`, always produce an HTML report, and upload build artifacts.
- V1 store packaging should be a separate unit.
- Publishing to GitHub Pages and GitHub Release should happen on tag, not every merge.
- Current request is to design the target directory structure and action/workflow checklist first.

## Research Findings
- Current repo only has two top-level workflows: `.github/workflows/validator.yml` and `.github/workflows/release.yml`.
- Current `validator.yml` mixes compose validation and appstore build validation.
- Current `release.yml` mixes v2 build, v1 zip packaging, and gh-pages deployment.
- There is no `actions/` implementation in this repo yet, so the architecture can start clean.
- The external `IceWhaleTech/build-appstore-action@v1` already handles v2 store build execution and cache-aware script invocation.
- A minimal local reusable action can be introduced without touching the live workflows first.
- `docker compose config -q` cannot be exercised locally in this workspace because Docker is unavailable, so the script includes a skip mode for local smoke tests.
- A wrapper composite action can call the upstream build action with `continue-on-error`, emit a local report, then fail at the end so workflows still get artifacts.
- The legacy v1 packaging logic can be reproduced locally with `zip`/`unzip` and repository file copies, so it is safe to move out of workflow shell into a Python action.
- A clean split works well with the current repo shape: keep `release.yml` for `main` builds and add a dedicated tag workflow for Pages + Release publication.
- Job summaries can be generated entirely from the existing report JSON files, so they do not need custom per-workflow formatting logic.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Use reusable local actions for single-purpose units | Easier testing, reuse, and long-term maintenance |
| Use top-level workflows for PR, main-branch build, and tag release orchestration | Triggers, permissions, artifact upload, Pages, and Release belong at workflow level |
| Standardize on a shared machine-readable report (`report.json`) | Makes HTML rendering and future PR comments/job summaries consistent |
| Add a dedicated report-render action | Avoids duplicating HTML generation logic across validation/build/release flows |
| Keep the first report renderer dependency-free | Using Python stdlib lowers setup complexity and makes the action easy to adopt |
| Let validation steps `continue-on-error` and fail at the end | This guarantees report generation and artifact upload even when validation fails |
| Use the same report/render/upload pattern for v2 builds | Keeps validation, build, and later release flows consistent for users and maintainers |
| Use the same report/render/upload pattern for v1 packaging | Keeps release deliverables and failure handling consistent across both store formats |
| Publish release bundles as both workflow artifacts and GitHub Release assets | Gives maintainers fast CI access and end users stable downloadable release files |
| Add a dedicated summary action instead of inline shell Markdown | Easier to reuse and evolve across validation/build/release flows |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| None during planning | N/A |

## Resources
- `.github/workflows/validator.yml`
- `.github/workflows/release.yml`
- `.github/workflows/release-store.yml`
- `IceWhaleTech/build-appstore-action@v1`
- `actions/render-report/action.yml`
- `actions/render-report/scripts/render_report.py`
- `actions/validate-compose/action.yml`
- `actions/validate-compose/scripts/validate_compose.py`
- `actions/build-store-v2/action.yml`
- `actions/build-store-v2/scripts/write_build_report.py`
- `actions/build-store-v1/action.yml`
- `actions/build-store-v1/scripts/build_store_v1.py`
- `actions/write-job-summary/action.yml`
- `actions/write-job-summary/scripts/write_job_summary.py`

## Visual/Browser Findings
- No browser-only findings were needed for this planning task.
