$ErrorActionPreference = 'Stop'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $projectPython)) { $projectPython = 'python' }
& $projectPython (Join-Path $PSScriptRoot 'scripts\preflight.py')
if ($LASTEXITCODE -ne 0) { throw 'Software preflight found missing or stale evidence.' }
