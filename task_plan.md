# Task Plan: AppStore CI/CD Action Architecture

## Goal
Define a concrete target directory structure and implementation checklist for splitting the AppStore publishing system into reusable GitHub Actions plus top-level orchestration workflows.

## Current Phase
Phase 2

## Phases

### Phase 1: Requirements & Discovery
- [x] Understand user intent
- [x] Identify current workflow boundaries and constraints
- [x] Document findings in findings.md
- **Status:** complete

### Phase 2: Planning & Structure
- [x] Define target action/workflow architecture
- [x] Assign responsibilities and data flow
- [x] Document rollout order and tradeoffs
- **Status:** complete

### Phase 3: Implementation Blueprint
- [x] Define each action's inputs, outputs, and artifacts
- [x] Define each workflow's triggers, permissions, and job graph
- [x] Capture report format and shared utilities
- [x] Implement the first shared utility action (`render-report`)
- **Status:** complete

### Phase 4: Rollout Strategy
- [x] Break implementation into low-risk milestones
- [x] Identify migration path from current workflows
- [x] Note compatibility risks and fallback points
- **Status:** complete

### Phase 5: Delivery
- [x] Summarize recommended structure for the user
- [x] Provide next implementation step options
- [x] Implement first validation action and wire it into PR workflow
- [x] Implement first v2 build wrapper action and wire it into validation/release workflows
- [x] Implement v1 packaging action and wire it into release workflow
- [x] Split continuous build and tag release into separate workflows
- [x] Add reusable job summary output for validation, build, and release workflows
- **Status:** in_progress

## Key Questions
1. Which responsibilities should live in reusable actions versus top-level workflows?
2. How should validation/build/release share structured reporting and artifacts?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Keep publishing/tag orchestration in workflows, not actions | Trigger rules, permissions, releases, and pages deployment are workflow concerns |
| Introduce a shared `report.json -> report.html` path | Structured data makes validation/build/release reporting reusable and debuggable |
| Split v2 build and v1 packaging into separate actions | Keeps business logic focused and avoids duplicating store-build behavior |
| Implement `render-report` first | It is the lowest-risk shared utility and unblocks validation/build reporting |
| Keep build validation as a separate step after compose validation | This preserves the current safety net while allowing structured report rollout incrementally |
| Wrap the upstream v2 build action instead of replacing it | Keeps compatibility with the existing build logic while adding local reporting and orchestration hooks |
| Keep v1 packaging as a local Python action | The logic is repository-specific and easier to evolve locally than in shell embedded in workflow YAML |
| Keep `release.yml` as the main-branch build workflow and add `release-store.yml` for tag publishing | Minimizes churn while aligning with the desired split between build and release |
| Render job summaries from report JSON instead of duplicating Markdown in workflows | Keeps summary formatting consistent across workflows and reduces YAML noise |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| None | 1 | N/A |

## Notes
- Current repo has `.github/workflows/release.yml` and `.github/workflows/validator.yml`, but no local reusable actions yet.
- The target architecture should minimize duplicated shell logic and make reports/artifacts available on both success and failure.
- `actions/render-report/` now exists as the first local reusable action.
- `actions/validate-compose/` now replaces the ad-hoc shell checks for compose metadata validation.
- `actions/build-store-v2/` now wraps the external build action and emits a structured build report for both validation and release workflows.
- `actions/build-store-v1/` now owns legacy `main.zip` packaging and reporting.
- `.github/workflows/release.yml` is now a build-only workflow for `main`.
- `.github/workflows/release-store.yml` is now the tag-driven publish workflow for Pages and GitHub Release.
- `actions/write-job-summary/` now provides a shared summary layer on top of the structured reports.
