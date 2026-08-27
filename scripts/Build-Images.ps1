param(
    [string]$Repository = "",
    [string]$Tag = "",
    [ValidateSet("All", "Policy", "Research", "Provider", "Concierge")]
    [string]$Agent = "All",
    [switch]$Push
)

. (Join-Path $PSScriptRoot "Common.ps1")

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Import-DotEnvFile (Join-Path $projectRoot ".env.local")
if ([string]::IsNullOrWhiteSpace($Repository)) { $Repository = $env:AGENTRUN_IMAGE_REPOSITORY }
if ([string]::IsNullOrWhiteSpace($Tag)) { $Tag = $(if ($env:AGENTRUN_IMAGE_TAG) { $env:AGENTRUN_IMAGE_TAG } else { "arms-v1" }) }

if ([string]::IsNullOrWhiteSpace($Repository)) {
    throw "Specify -Repository or set AGENTRUN_IMAGE_REPOSITORY."
}
$Repository = $Repository.TrimEnd("/")

$dockerfile = Join-Path $projectRoot "docker\Dockerfile"
$outputMode = if ($Push) { "--push" } else { "--load" }
$agents = if ($Agent -eq "All") { @("policy", "research", "provider", "concierge") } else { @($Agent.ToLowerInvariant()) }

foreach ($agentName in $agents) {
    $image = "${Repository}:${agentName}-${Tag}"
    Write-Host "Building $agentName -> $image"
    docker buildx build `
        --platform linux/amd64 `
        --build-arg "AGENT_NAME=$agentName" `
        --file $dockerfile `
        --tag $image `
        $outputMode `
        $projectRoot
    Assert-LastExitCode "docker buildx build ($agentName)"

    if (-not $Push) {
        $platform = docker image inspect $image --format '{{.Os}}/{{.Architecture}}'
        Assert-LastExitCode "docker image inspect ($agentName)"
        if ($platform.Trim() -ne "linux/amd64") {
            throw "Unexpected image platform for ${agentName}: $platform (expected linux/amd64)."
        }
    }
}

Write-Host "Completed $($agents.Count) Agent image(s)."
