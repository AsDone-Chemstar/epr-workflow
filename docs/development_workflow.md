# SpectraLab Development Workflow

This document defines the routine development and release-gate workflow after
M11. It is deliberately conservative: fast checks speed up iteration, but only
the release gate can approve a milestone.

## 1. Development sequence

1. Record the current Git HEAD and working-tree state.
2. Inspect the relevant code and tests before editing.
3. Identify the smallest change that preserves existing public behaviour.
4. Make maintenance changes separately from scientific feature changes.
5. Run the relevant fast or focused tests while iterating.
6. Run the complete release gate before reporting a milestone.
7. Update the milestone report and `docs/architecture_proposal.md`.
8. Do not commit, push or tag unless explicitly authorised.

Never mix a refactor and a new scientific algorithm in one uncontrolled step.
For M11, Part A maintenance must pass its gate before Part B normalization.

## 2. Test layers

All commands run from the project root on Windows PowerShell:

```powershell
.\scripts\check.ps1 -Mode fast
.\scripts\check.ps1 -Mode gui
.\scripts\check.ps1 -Mode arch
.\scripts\check.ps1 -Mode regression
.\scripts\check.ps1 -Mode full
.\scripts\check.ps1 -Mode release -Milestone m11
```

| Mode | Includes | Use when |
| --- | --- | --- |
| `fast` | Non-GUI, non-architecture tests | Frequent edit loop |
| `gui` | GUI/offscreen tests and GUI baseline | Changing panels, dialogs or Qt services |
| `arch` | Consolidated `tests/test_architecture.py` | Changing imports, package layout or dependencies |
| `regression` | Original EPR 14-file subset | Any change that could affect legacy EPR |
| `full` | Complete suite | Before reporting any milestone |
| `release` | Full verbose + `-W error::UserWarning` + original EPR | Milestone acceptance |

`release` writes:

```text
results/logs/pytest_<milestone>_<YYYYMMDD>_verbose.txt
results/logs/pytest_<milestone>_<YYYYMMDD>_userwarning.txt
results/logs/pytest_<milestone>_<YYYYMMDD>_original.txt
```

The release gate fails if any of the three commands fails. No layer is optional.

## 3. Required checks by change type

| Change | Minimum checks |
| --- | --- |
| Pure documentation | `fast` if code unchanged; otherwise relevant layer |
| Core model/import/export/processing/plotting | `fast` + `arch` |
| EPR backend or legacy-facing code | `fast` + `regression` + `arch` |
| FTIR backend/import/GUI | `fast` + `gui` + `arch` |
| GUI shell/controller/metadata/i18n | `gui` + `arch` |
| Importer suffix, package boundary or translation ownership | `arch` + `gui` + `regression` |
| Any release candidate | `release` |

## 4. Release-gate procedure

1. Confirm the working tree contains no unintended edits.
2. Run `.\scripts\check.ps1 -Mode release -Milestone mNN`.
3. Confirm all three logs end with the expected pass count.
4. Confirm the remaining skip is only a documented platform limitation.
5. Verify the real `S-BSAPEG-10.0.dpt` sample still imports with 4350 points,
   decreasing X axis, explicit ATR/Absorbance metadata and unchanged SHA-256.
6. Check that no raw data, legacy `epr_workflow` code or `requirements.txt`
   changed.
7. Update the report with actual counts, durations and any unresolved issue.
8. Do not claim a command succeeded unless it was actually run.

## 5. Baseline updates

- Baselines are actual measured results, never inferred from previous reports.
- Record full, warnings-as-errors and original-EPR counts separately.
- Record architecture test count and duration separately because it is the
  most sensitive to subprocess/cache state.
- On a cold Windows run, note the first-run import/font-cache effect; do not
  present a cold run as a warm-run regression.
- Any new skip must name the exact missing file or platform limitation.
- A baseline update is an explicit report change, not a silent test relaxation.

## 6. Scientific-integrity checklist

Before declaring a scientific feature complete, verify:

- [ ] Raw `Spectrum1D` arrays remain immutable and unchanged.
- [ ] Original point order, axis direction and X values are preserved.
- [ ] No automatic smoothing, baseline, normalization, filtering or ATR correction.
- [ ] Every processing operation is user-triggered and recorded.
- [ ] Requested options and resolved mappings remain distinct.
- [ ] Unknown units, semantics and acquisition modes remain explicitly unknown.
- [ ] Zero denominators, non-finite inputs/outputs and invalid parameters fail explicitly.
- [ ] Undo/redo restore stored states; preview never mutates committed history.
- [ ] Source SHA-256 and file size match the bytes actually parsed.
- [ ] No raw experimental data was modified.

## 7. Investigating failures

1. Re-run the single failing test with `-vv` before changing code.
2. Determine whether the failure is environmental, a stale cache, or a real
   regression; never start by loosening an assertion.
3. For architecture tests, inspect the named subprocess domain and its stderr.
   Do not merge incompatible import environments to make a failure disappear.
4. For GUI failures, run with `QT_QPA_PLATFORM=offscreen` and close windows in
   the test.
5. For numerical failures, compare against an independently calculated value,
   not against the implementation under test.
6. If a test must be superseded by a changed requirement, document the exact
   old assertion and its replacement in the milestone report.
7. Preserve the failing output in `results/logs/` when reporting a blocker.
