[CmdletBinding()]
param([switch]$Update)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VendorRoot = Join-Path $ProjectRoot 'vendor'
New-Item -ItemType Directory -Force -Path $VendorRoot | Out-Null

$repos = @(
    @{
        Name = 'BrowserOS'
        Url = 'https://github.com/browseros-ai/BrowserOS.git'
        Commit = '0f957a86ab68409dc906d18e542673152d30bb24'
        Sparse = @('packages/browseros-agent', 'docs', '.agents')
    },
    @{
        Name = 'agent-browser'
        Url = 'https://github.com/vercel-labs/agent-browser.git'
        Commit = '6dcea79b4b567a5671f1e1164807204f69542a5c'
    },
    @{
        Name = 'marketingskills'
        Url = 'https://github.com/coreyhaines31/marketingskills.git'
        Commit = '7868cb9251fad80a73d26e488a5ad5f6c4a9f335'
    },
    @{
        Name = 'opentabs'
        Url = 'https://github.com/opentabs-dev/opentabs.git'
        Commit = 'de9200b1231cae419d1a437e410114a9e2fe8eca'
    }
)

foreach ($repo in $repos) {
    $path = Join-Path $VendorRoot $repo.Name
    if (-not (Test-Path -LiteralPath $path)) {
        if ($repo.Sparse) {
            git clone --filter=blob:none --no-checkout $repo.Url $path
            git -C $path sparse-checkout init --cone
            git -C $path sparse-checkout set @($repo.Sparse)
        } else {
            git clone --filter=blob:none --no-checkout $repo.Url $path
        }
    } elseif ($Update) {
        git -C $path fetch origin
    }

    git -C $path checkout --detach $repo.Commit
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to checkout $($repo.Name) at $($repo.Commit)"
    }
}

Write-Output "Vendored dependencies are ready under $VendorRoot"
