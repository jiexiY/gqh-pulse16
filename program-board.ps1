param(
    [switch]$ListCables,
    [switch]$Scan,
    [switch]$ProgramSram,
    [string]$Location = '',
    [string]$Programmer = ''
)
$ErrorActionPreference = 'Stop'
if ($PSBoundParameters.ContainsKey('Programmer') -and [string]::IsNullOrWhiteSpace($Programmer)) {
    throw 'Programmer path must not be empty; omit -Programmer to use the optional local installation.'
}
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $projectPython)) { $projectPython = 'python' }
$programArgs = @((Join-Path $PSScriptRoot 'scripts\program_fpga.py'))
if ($ListCables) { $programArgs += '--list-cables' }
if ($Scan) { $programArgs += '--scan' }
if ($ProgramSram) { $programArgs += '--program-sram' }
if ($Location) { $programArgs += @('--location', $Location) }
if ($PSBoundParameters.ContainsKey('Programmer')) { $programArgs += @('--programmer', $Programmer) }
& $projectPython @programArgs
if ($LASTEXITCODE -ne 0) { throw 'Programming helper stopped. Read the diagnostic and receipt above.' }
