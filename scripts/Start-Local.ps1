param(
    [switch]$Build,
    [switch]$Down
)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composeFile = Join-Path $projectRoot "docker\compose.local.yml"
$envFile = Join-Path $projectRoot ".env.local"

if ($Down) {
    docker compose -f $composeFile down
    exit $LASTEXITCODE
}

$arguments = @("compose", "-f", $composeFile)
if (Test-Path -LiteralPath $envFile) {
    $arguments += @("--env-file", $envFile)
}
$arguments += "up"
if ($Build) { $arguments += "--build" }
$arguments += "-d"

& docker @arguments
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed with exit code $LASTEXITCODE" }

Write-Host "Agent Cards:"
Write-Host "  http://localhost:19090/.well-known/agent-card.json"
Write-Host "  http://localhost:19091/.well-known/agent-card.json"
Write-Host "  http://localhost:19092/.well-known/agent-card.json"
Write-Host "  http://localhost:19093/.well-known/agent-card.json"

