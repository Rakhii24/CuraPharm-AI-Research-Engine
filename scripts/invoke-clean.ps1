<#
.SYNOPSIS
    Runs a CuraPharm command without the managed IDE's invalid proxy settings.

.DESCRIPTION
    The managed IDE/terminal environment currently injects a local proxy at
    127.0.0.1:9. That endpoint prevents CuraPharm's external API connections.

    This wrapper removes only the six HTTP proxy variables from the child
    process. It does not change Windows settings, the parent terminal, .env,
    or any other environment variables. GEMINI_API_KEY, GEMINI_MODEL, and all
    other CuraPharm settings are inherited unchanged and are never printed.

.EXAMPLE
    .\scripts\invoke-clean.ps1 .venv\Scripts\python.exe -m pytest -q

.EXAMPLE
    .\scripts\invoke-clean.ps1 .venv\Scripts\uvicorn.exe app.main:app --reload

.EXAMPLE
    .\scripts\invoke-clean.ps1 .venv\Scripts\streamlit.exe run app\ui\streamlit_app.py

.EXAMPLE
    .\scripts\invoke-clean.ps1 .venv\Scripts\python.exe <approved-smoke-test-module>

    Use the same wrapper for future Gemini smoke-test commands. Replace the
    placeholder with the approved project command when a smoke-test entry
    point is available. The Streamlit example applies when that UI exists.
#>

if ($args.Count -lt 1) {
    throw 'A command is required. Usage: .\scripts\invoke-clean.ps1 <command> [arguments...]'
}

$Command = $args[0]
$CommandArguments = @()
if ($args.Count -gt 1) {
    $CommandArguments = $args[1..($args.Count - 1)]
}

$proxyVariables = @(
    'HTTP_PROXY',
    'HTTPS_PROXY',
    'ALL_PROXY',
    'http_proxy',
    'https_proxy',
    'all_proxy'
)

$originalProxyValues = foreach ($name in $proxyVariables) {
    [pscustomobject]@{
        Name  = $name
        Value = [Environment]::GetEnvironmentVariable($name, 'Process')
    }
}
$exitCode = 1

try {
    foreach ($name in $proxyVariables) {
        Remove-Item -LiteralPath ("Env:{0}" -f $name) -ErrorAction SilentlyContinue
    }

    & $Command @CommandArguments
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) {
        $exitCode = 0
    }
}
finally {
    foreach ($originalProxyValue in $originalProxyValues) {
        $name = $originalProxyValue.Name
        $originalValue = $originalProxyValue.Value
        if ($null -eq $originalValue) {
            Remove-Item -LiteralPath ("Env:{0}" -f $name) -ErrorAction SilentlyContinue
        }
        else {
            [Environment]::SetEnvironmentVariable($name, $originalValue, 'Process')
        }
    }
}
exit $exitCode
