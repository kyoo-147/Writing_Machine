$scriptPath = Join-Path $PSScriptRoot '.agents\skills\ai-content-machine\scripts\content-machine.ps1'
& $scriptPath @args
exit $LASTEXITCODE
