# CLAUDE.md — EPR Workflow

## 1. Project

A Python-based scientific workflow for EPR data processing and analysis, supporting:

- Bruker ELEXSYS E580 and Xepr.
- CW-EPR and spin-labelled samples.
- Protein–lipid membrane interactions.
- Future extensions to pulse EPR and DEER.

The developer is a chemistry PhD student learning Python. Prefer clear, readable, maintainable code and explain important technical decisions briefly.

## 2. Project Boundaries and Safety

Project root: `D:\EPR workflow`.

- Keep all project-related file operations inside this directory.
- Resolve and verify paths before writing, modifying, or deleting files.
- Never modify, overwrite, rename, or delete files in `data/raw/`.
- Write generated data, figures, logs, and reports under `results/`.
- Do not access or modify unrelated projects, global configurations, or system settings.
- Do not run administrator commands or destructive operations without explicit approval.
- Do not send experimental data to external services without permission.
- Never expose API keys, credentials, or tokens.

If a requested action cannot safely be completed within the project root, explain why and ask for permission.

## 3. Python Environment

- Windows and PowerShell.
- Python 3.11.9, 64-bit.
- Virtual environment: `.venv`.
- Expected packages: NumPy, SciPy, Matplotlib, Pandas, and Pytest.

Use the project interpreter:

`.\.venv\Scripts\python.exe`

Install dependencies only into `.venv`. Do not recreate the environment, change Python versions, or install global packages without approval.

Update `requirements.txt` when dependencies change.

## 4. Scientific Integrity

- Never fabricate measurements, metadata, units, or analysis results.
- Distinguish experimental data, calculated values, assumptions, and interpretations.
- Preserve original data and row order.
- Report malformed, missing, non-finite, or suspicious data rather than silently correcting it.
- Do not assume an EPR signal type, intensity unit, acquisition parameter, or axis direction without evidence.
- Do not automatically smooth, normalize, baseline-correct, filter, remove outliers, or fit experimental data.
- Keep raw-data import separate from processing and interpretation.
- Successful code execution does not establish scientific validity.

## 5. Data Formats and Analysis

The initial dataset is `data/raw/BSA3T275.ASC`.

Its observed columns are:

`index`, `Field [G]`, `Intensity []`

The file appears to use whitespace-separated columns. Field is reported in Gauss; the intensity unit is unspecified.

Inspect actual files before choosing a parser. Do not assume every Xepr ASC export has the same format.

Other possible formats include Bruker BES3T (`.DSC`/`.DTA`) and ESP (`.PAR`/`.SPC`). Verify compatibility before supporting them.

Do not implement pulse EPR or DEER analysis until the actual data format and scientific requirements are established. Never treat DEER time-domain data as an ordinary CW-EPR spectrum.

## 6. Code Quality and Testing

- Use modular, readable Python with clear function names and useful error messages.
- Prefer `pathlib.Path`, type hints where useful, and docstrings.
- Avoid unnecessary dependencies and premature abstraction.
- Add or update tests for meaningful code changes.
- Use temporary or synthetic datasets for error-handling tests.
- Never alter real experimental data to test code.

Run tests with:

`.\.venv\Scripts\python.exe -m pytest -v`

Report actual test results. Never claim a command succeeded unless it was executed successfully.

## 7. Outputs and Documentation

Keep generated files under `results/`, using descriptive filenames.

Include source-file information, processing parameters, software versions, and warnings in metadata where practical.

Maintain `README.md` and `requirements.txt` when relevant.

Do not overwrite existing outputs without checking them first.

## 8. Workflow for Every Task

1. Inspect relevant files and the current environment.
2. Identify the smallest appropriate change.
3. Check project boundaries and data integrity.
4. Implement the change.
5. Run relevant tests and the actual workflow when possible.
6. Inspect outputs and update documentation.
7. Report changed files, commands, test results, warnings, and unresolved issues.

Ask for clarification when ambiguity could affect scientific correctness. Do not rewrite unrelated modules or introduce major architectural changes without justification.

Priorities: scientific correctness, data integrity, reproducibility, security, and maintainability.
