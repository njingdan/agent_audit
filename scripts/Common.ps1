Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Import-DotEnvFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }

    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $separator = $trimmed.IndexOf('=')
        if ($separator -lt 1) { throw "Invalid .env line in ${Path}: $line" }
        $name = $trimmed.Substring(0, $separator).Trim()
        if ($name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
            throw "Invalid environment variable name in ${Path}: $name"
        }
        $value = $trimmed.Substring($separator + 1).Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ([string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($name))) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Get-RequiredEnvironmentValue {
    param([Parameter(Mandatory = $true)][string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Required environment variable '$Name' is not set."
    }
    return $value
}

function ConvertTo-YamlQuotedString {
    param([Parameter(Mandatory = $true)][string]$Value)
    $escaped = $Value.Replace('\', '\\').Replace('"', '\"').Replace("`r", '').Replace("`n", '\n')
    return '"' + $escaped + '"'
}

function Get-AgentRunCli {
    $command = Get-Command agentrun -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "AgentRun CLI not found. Install the Windows binary, then use 'agentrun' (not 'ar')."
    }
    return $command.Source
}

function Assert-LastExitCode {
    param([Parameter(Mandatory = $true)][string]$Operation)
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE."
    }
}
