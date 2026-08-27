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
        # `runtime render` prints the fully rendered environment, including
        # secret values. Validation output is therefore intentionally hidden.
        & $cli runtime render -f $file *> $null
        Assert-LastExitCode "agentrun runtime render"
        Write-Host "Validation passed (rendered values hidden)."
        if (-not $RenderOnly) {
            Write-Host "Applying $file"
            $applyOutput = @(& $cli runtime apply -f $file --wait --timeout $Timeout 2>&1)
            $applyExitCode = $LASTEXITCODE
            $safeOutput = $applyOutput -join [Environment]::NewLine
            foreach ($secret in @($env:DEEPSEEK_API_KEY, $env:ARMS_LICENSE_KEY)) {
                if (-not [string]::IsNullOrWhiteSpace($secret)) {
                    $safeOutput = $safeOutput.Replace($secret, "***REDACTED***")
                }
            }
            if (-not [string]::IsNullOrWhiteSpace($safeOutput)) {
                Write-Host $safeOutput
            }
            if ($applyExitCode -ne 0) {
                throw "agentrun runtime apply failed with exit code $applyExitCode."
            }
        }
    }
}
finally {
    if (Test-Path -LiteralPath $temporaryDirectory) {
        Remove-Item -LiteralPath $temporaryDirectory -Recurse -Force
    }
}
