param(
    [string]$ServiceName = "",
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

$python = Get-Command py -ErrorAction SilentlyContinue
if ($null -ne $python) {
    $arguments = @("-3.12", $tool, "--minutes", $Minutes, "--output", $OutputDirectory)
    if (-not [string]::IsNullOrWhiteSpace($ServiceName)) {
        $arguments += @("--service-name", $ServiceName)
    }
    & $python.Source @arguments
}
else {
    $arguments = @($tool, "--minutes", $Minutes, "--output", $OutputDirectory)
    if (-not [string]::IsNullOrWhiteSpace($ServiceName)) {
        $arguments += @("--service-name", $ServiceName)
    }
    python @arguments
}

if ($LASTEXITCODE -ne 0) { throw "ARMS trace export failed with exit code $LASTEXITCODE" }
