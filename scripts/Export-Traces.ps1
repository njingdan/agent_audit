param(
    [string]$ServiceName = "",
    [string[]]$TraceId = @(),
    [int]$Minutes = 60,
    [string]$OutputDirectory = ""
)

. (Join-Path $PSScriptRoot "Common.ps1")

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Import-DotEnvFile (Join-Path $projectRoot ".env.local")
$tool = Join-Path $projectRoot "tools\export_arms_traces.py"
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $projectRoot "trace-export"
}

$venvPython = Join-Path $projectRoot ".venv-trace\Scripts\python.exe"
$python = Get-Command python -ErrorAction SilentlyContinue
$pythonLauncher = Get-Command py -ErrorAction SilentlyContinue

if (Test-Path -LiteralPath $venvPython) {
    $executable = $venvPython
    $arguments = @($tool, "--minutes", $Minutes, "--output", $OutputDirectory)
}
elseif ($null -ne $python -and -not [string]::IsNullOrWhiteSpace($env:VIRTUAL_ENV)) {
    $executable = $python.Source
    $arguments = @($tool, "--minutes", $Minutes, "--output", $OutputDirectory)
}
elseif ($null -ne $pythonLauncher) {
    $executable = $pythonLauncher.Source
    $arguments = @("-3.11", $tool, "--minutes", $Minutes, "--output", $OutputDirectory)
}
elseif ($null -ne $python) {
    $executable = $python.Source
    $arguments = @($tool, "--minutes", $Minutes, "--output", $OutputDirectory)
}
else {
    throw "Python 3.11 is required to export ARMS traces."
}

if (-not [string]::IsNullOrWhiteSpace($ServiceName)) {
    $arguments += @("--service-name", $ServiceName)
}
foreach ($id in $TraceId) {
    $arguments += @("--trace-id", $id)
}
& $executable @arguments

if ($LASTEXITCODE -ne 0) { throw "ARMS trace export failed with exit code $LASTEXITCODE" }
