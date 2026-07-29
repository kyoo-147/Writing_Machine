$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & $python.Source -m content_machine @args
    exit $LASTEXITCODE
}

$scriptPath = Join-Path $PSScriptRoot '.agents\skills\ai-content-machine\scripts\content-machine.ps1'
& $scriptPath @args
exit $LASTEXITCODE
