param(
    [switch]$ListCables,
    [switch]$Scan,
    [switch]$ProgramSram,
    [string]$Location = ''
)
$ErrorActionPreference = 'Stop'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $projectPython)) { $projectPython = 'python' }
$programArgs = @((Join-Path $PSScriptRoot 'scripts\program_fpga.py'))
if ($ListCables) { $programArgs += '--list-cables' }
if ($Scan) { $programArgs += '--scan' }
if ($ProgramSram) { $programArgs += '--program-sram' }
if ($Location) { $programArgs += @('--location', $Location) }
& $projectPython @programArgs
if ($LASTEXITCODE -ne 0) { throw 'Programming helper stopped. Read the diagnostic and receipt above.' }
