param([string]$Port = '', [ValidateSet('quick','robust','fullrange','both','qualification','all')][string]$Test = 'both')
$ErrorActionPreference = 'Stop'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $projectPython)) { $projectPython = 'python' }
$testArgs = @((Join-Path $PSScriptRoot 'scripts\board_test.py'), '--test', $Test)
if ($Port) { $testArgs += @('--port', $Port) }
& $projectPython @testArgs
if ($LASTEXITCODE -ne 0) { throw 'Board test did not pass. Read the diagnostic above.' }
