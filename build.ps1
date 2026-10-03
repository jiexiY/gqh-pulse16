param([string]$Gowin = '')
$ErrorActionPreference = 'Stop'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $projectPython)) { $projectPython = 'python' }
$buildArgs = @((Join-Path $PSScriptRoot 'scripts\build_fpga.py'))
if ($Gowin) { $buildArgs += @('--gowin', $Gowin) }
& $projectPython @buildArgs
if ($LASTEXITCODE -ne 0) { throw 'Gowin build failed. Read the diagnostic above.' }
