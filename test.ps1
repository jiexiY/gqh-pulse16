param([string]$Python = "")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!$Python) {
    $existingPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $existingPython) { $Python = $existingPython }
    else { $Python = 'python' }
}
& $Python -u sim/run_tests.py
if ($LASTEXITCODE -ne 0) { throw 'FPGA simulation failed. See the output above.' }

