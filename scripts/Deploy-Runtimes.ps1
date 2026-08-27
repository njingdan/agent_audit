param(
    [ValidateSet("Leaves", "Concierge", "All")]
    [string]$Phase = "All",
    [switch]$RenderOnly,
    [string]$Timeout = "20m"
)

. (Join-Path $PSScriptRoot "Common.ps1")

$cli = Get-AgentRunCli
$temporaryDirectory = Join-Path ([IO.Path]::GetTempPath()) ("agentrun-a2a-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temporaryDirectory | Out-Null

try {
    $renderScript = Join-Path $PSScriptRoot "Render-Runtime.ps1"
    $files = @(& $renderScript -Phase $Phase -OutputDirectory $temporaryDirectory)
    foreach ($file in $files) {
        Write-Host "Validating $file"
        & $cli runtime render -f $file
        Assert-LastExitCode "agentrun runtime render"
        if (-not $RenderOnly) {
            Write-Host "Applying $file"
            & $cli runtime apply -f $file --wait --timeout $Timeout
            Assert-LastExitCode "agentrun runtime apply"
        }
    }
}
finally {
    if (Test-Path -LiteralPath $temporaryDirectory) {
        Remove-Item -LiteralPath $temporaryDirectory -Recurse -Force
    }
}

