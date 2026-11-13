param(
    [ValidateSet("fast", "gui", "regression", "full", "release")]
    [string]$Mode = "full",
    [string]$Milestone = "legacy"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:QT_QPA_PLATFORM = "offscreen"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "results\logs"
$Date = Get-Date -Format "yyyyMMdd"

if (-not (Test-Path $Python)) {
    throw "Project interpreter not found: $Python"
}

function Invoke-Pytest {
    param(
        [string]$Label,
        [string[]]$PytestArgs,
        [string]$LogPath = ""
    )
    Write-Host ""
    Write-Host "=== $Label ==="
    $arguments = @("-m", "pytest") + $PytestArgs
    if ($LogPath) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogPath) | Out-Null
        $output = & $Python @arguments 2>&1
        $code = $LASTEXITCODE
        $output | Out-Host
        $output | Out-File -FilePath $LogPath -Encoding utf8
    }
    else {
        $output = & $Python @arguments 2>&1
        $code = $LASTEXITCODE
        $output | Out-Host
    }
    Write-Host "$Label exit code: $code"
    return $code
}

$GuiTargets = @(
    Get-ChildItem (Join-Path $ProjectRoot "tests") -Filter "test_gui_*.py" |
        Sort-Object Name |
        ForEach-Object { "tests/$($_.Name)" }
)
$GuiTargets += "tests/test_m0_gui_baseline.py"

$RegressionTargets = @(
    "tests/test_batch.py",
    "tests/test_bes3t.py",
    "tests/test_gui_bes3t.py",
    "tests/test_gui_controller.py",
    "tests/test_gui_i18n.py",
    "tests/test_gui_plot_editor.py",
    "tests/test_gui_preprocessing.py",
    "tests/test_gui_widgets.py",
    "tests/test_plot_asc.py",
    "tests/test_plot_export.py",
    "tests/test_plot_settings.py",
    "tests/test_preprocessing.py",
    "tests/test_processed_export.py",
    "tests/test_savgol.py"
)

switch ($Mode) {
    "fast" {
        $fastArgs = @("-q") + ($GuiTargets | ForEach-Object { "--ignore=$_" })
        exit (Invoke-Pytest -Label "Fast non-GUI EPR tests" -PytestArgs $fastArgs)
    }
    "gui" {
        exit (Invoke-Pytest -Label "Legacy EPR GUI tests" -PytestArgs (@("-q") + $GuiTargets))
    }
    "regression" {
        exit (Invoke-Pytest -Label "Original EPR regression" -PytestArgs (@("-q") + $RegressionTargets))
    }
    "full" {
        exit (Invoke-Pytest -Label "Full Legacy EPR test suite" -PytestArgs @("-q"))
    }
    "release" {
        $verboseLog = Join-Path $LogDir "pytest_${Milestone}_${Date}_verbose.txt"
        $warningLog = Join-Path $LogDir "pytest_${Milestone}_${Date}_userwarning.txt"
        $regressionLog = Join-Path $LogDir "pytest_${Milestone}_${Date}_regression.txt"

        $codes = @()
        $codes += Invoke-Pytest -Label "Release: full verbose" -PytestArgs @("-v") -LogPath $verboseLog
        $codes += Invoke-Pytest -Label "Release: warnings-as-errors" -PytestArgs @("-q", "-W", "error::UserWarning") -LogPath $warningLog
        $codes += Invoke-Pytest -Label "Release: original EPR regression" -PytestArgs (@("-q") + $RegressionTargets) -LogPath $regressionLog

        $failed = $false
        foreach ($code in $codes) {
            if ($code -ne 0) { $failed = $true }
        }
        if ($failed) {
            Write-Host ""
            Write-Host "Release gate FAILED."
            exit 1
        }
        Write-Host ""
        Write-Host "Release gate passed."
        Write-Host "Logs: $verboseLog"
        Write-Host "Logs: $warningLog"
        Write-Host "Logs: $regressionLog"
        exit 0
    }
}
