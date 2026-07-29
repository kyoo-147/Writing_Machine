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
    },
    @{
        Name = 'mattpocock-skills'; Url = 'https://github.com/mattpocock/skills.git'
        Commit = '2ab958093e83e0ec752e6c1c5932da465bf23e0c'
    },
    @{
        Name = 'superpowers'; Url = 'https://github.com/obra/superpowers.git'
        Commit = '44c9b2d6e889982ac18c27d05a19fefe335194e1'
    },
    @{
        Name = 'ai-berkshire'; Url = 'https://github.com/xbtlin/ai-berkshire.git'
        Commit = '09ebc400a8815636e02f5b7d1d811a53164a0b92'
    },
    @{
        Name = 'agency-agents'; Url = 'https://github.com/msitarzewski/agency-agents.git'
        Commit = '8ef49232e02431f7ca4792b487e5a85a7939ff3a'
    },
    @{
        Name = 'firecrawl'; Url = 'https://github.com/firecrawl/firecrawl.git'
        Commit = '1135c555c2c8a19d209d7f4aaf84f961c37a3970'
    },
    @{
        Name = 'firecrawl-web-agent'; Url = 'https://github.com/firecrawl/firecrawl-web-agent.git'
        Commit = 'f023adf1cd1f731e27fdc844af62996f6c2a41c4'
    },
    @{
        Name = 'apify-agent-skills'; Url = 'https://github.com/apify/agent-skills.git'
        Commit = '7eb62968907e8d9d722f5b139998963cd81c8351'
    },
    @{
        Name = 'crawl4ai'; Url = 'https://github.com/unclecode/crawl4ai.git'
        Commit = '7e801521428ee12509994d39151006f64055ebe3'
    },
    @{
        Name = 'rsshub'; Url = 'https://github.com/DIYgod/RSSHub.git'
        Commit = '53df037bd7f88d2031282f17371170e8593b9aef'
    },
    @{
        Name = 'browser-use'; Url = 'https://github.com/browser-use/browser-use.git'
        Commit = 'f0aa3a8bb03779c71a5aa262d389e3bfe6b77cdc'
    },
    @{
        Name = 'deer-flow'; Url = 'https://github.com/bytedance/deer-flow.git'
        Commit = '1b5220e35e7a120131b6abbbbd336acf2385837b'
    },
    @{
        Name = 'openfang'; Url = 'https://github.com/RightNow-AI/openfang.git'
        Commit = 'acf2587e46be174c10200489c9a2d23a39a98aeb'
    },
    @{
        Name = 'hermes-agent'; Url = 'https://github.com/NousResearch/hermes-agent.git'
        Commit = '015718066ab8e9499c3caea3cda9f7ea469036fc'
    },
    @{
        Name = 'maxun'; Url = 'https://github.com/getmaxun/maxun.git'
        Commit = '35cf97b83c7d432818d5e2abfb6e62afe481765a'
    },
    @{
        Name = 'intern-agent'; Url = 'https://github.com/anthropics/anthropic-quickstarts.git'
        Commit = 'fa8c3eedfa9751d3752ea6eb49220b303ac2397d'
    },
    @{
        Name = 'openagent'; Url = 'https://github.com/OpenBMB/ChatDev.git'
        Commit = 'b6b282d1ece08dea4429576c0625007778234e58'
    },
    @{
        Name = 'horizon'; Url = 'https://github.com/ByteDance-Seed/UI-TARS-desktop.git'
        Commit = '1e2fdc7ccb177f33c59aef2082c4093e1e82b22c'
    },
    @{
        Name = 'social-media-skills'; Url = 'https://github.com/Prat011/social-media-skills.git'
        Commit = '4f85b07069983b3b0b9bbe6519fed7017edcce81'
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
