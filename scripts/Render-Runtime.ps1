param(
    [ValidateSet("Leaves", "Concierge", "All")]
    [string]$Phase = "All",
    [string]$OutputDirectory = ""
)

. (Join-Path $PSScriptRoot "Common.ps1")

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Import-DotEnvFile (Join-Path $projectRoot ".env.local")
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $projectRoot "runtime\generated"
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$values = @{
    "__DEEPSEEK_API_KEY__" = ConvertTo-YamlQuotedString (Get-RequiredEnvironmentValue "DEEPSEEK_API_KEY")
    "__DEEPSEEK_BASE_URL__" = ConvertTo-YamlQuotedString ($(if ($env:DEEPSEEK_BASE_URL) { $env:DEEPSEEK_BASE_URL } else { "https://api.deepseek.com" }))
    "__DEEPSEEK_ANTHROPIC_BASE_URL__" = ConvertTo-YamlQuotedString ($(if ($env:DEEPSEEK_ANTHROPIC_BASE_URL) { $env:DEEPSEEK_ANTHROPIC_BASE_URL } else { "https://api.deepseek.com/anthropic" }))
    "__REGION__" = ConvertTo-YamlQuotedString ($(if ($env:AGENTRUN_REGION) { $env:AGENTRUN_REGION } else { "cn-hangzhou" }))
    "__ARMS_LICENSE_KEY__" = ConvertTo-YamlQuotedString (Get-RequiredEnvironmentValue "ARMS_LICENSE_KEY")
}

function Render-One {
    param(
        [Parameter(Mandatory = $true)][string]$TemplateName,
        [Parameter(Mandatory = $true)][string]$OutputName,
        [hashtable]$ExtraValues = @{}
    )
    $templatePath = Join-Path $projectRoot "runtime\templates\$TemplateName"
    $content = Get-Content -Raw -Encoding UTF8 -LiteralPath $templatePath
    $allValues = @{} + $values
    foreach ($key in $ExtraValues.Keys) { $allValues[$key] = $ExtraValues[$key] }
    foreach ($key in $allValues.Keys) { $content = $content.Replace($key, $allValues[$key]) }
    if ($content -match '__[A-Z0-9_]+__') {
        throw "Unresolved placeholder in ${TemplateName}: $($Matches[0])"
    }
    $outputPath = Join-Path $OutputDirectory $OutputName
    [IO.File]::WriteAllText($outputPath, $content, [Text.UTF8Encoding]::new($false))
    Write-Output $outputPath
}

if ($Phase -in @("Leaves", "All")) {
    $leafValues = @{
        "__POLICY_IMAGE__" = ConvertTo-YamlQuotedString (Get-RequiredEnvironmentValue "AGENTRUN_POLICY_IMAGE")
        "__RESEARCH_IMAGE__" = ConvertTo-YamlQuotedString (Get-RequiredEnvironmentValue "AGENTRUN_RESEARCH_IMAGE")
        "__PROVIDER_IMAGE__" = ConvertTo-YamlQuotedString (Get-RequiredEnvironmentValue "AGENTRUN_PROVIDER_IMAGE")
    }
    Render-One "leaves.yaml.tmpl" "leaves.yaml" $leafValues
}

if ($Phase -in @("Concierge", "All")) {
    $conciergeValues = @{
        "__CONCIERGE_IMAGE__" = ConvertTo-YamlQuotedString (Get-RequiredEnvironmentValue "AGENTRUN_CONCIERGE_IMAGE")
        "__POLICY_A2A_URL__" = ConvertTo-YamlQuotedString (Get-RequiredEnvironmentValue "POLICY_A2A_URL")
        "__RESEARCH_A2A_URL__" = ConvertTo-YamlQuotedString (Get-RequiredEnvironmentValue "RESEARCH_A2A_URL")
        "__PROVIDER_A2A_URL__" = ConvertTo-YamlQuotedString (Get-RequiredEnvironmentValue "PROVIDER_A2A_URL")
    }
    Render-One "concierge.yaml.tmpl" "concierge.yaml" $conciergeValues
}
