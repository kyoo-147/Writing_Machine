[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'init', 'doctor', 'new', 'prompt', 'status', 'auth', 'open')]
    [string]$Command = 'help',

    [string]$Query = '',
    [string]$Title = '',
    [int]$Count = 3,
    [ValidateSet('auto', 'video', 'carousel', 'image', 'text')]
    [string]$Format = 'auto',
    [string]$Tone = 'builder+skeptical',
    [string]$Audience = 'mixed',
    [string]$Platforms = 'tiktok',
    [string]$Job = '',
    [ValidateSet('x', 'facebook', 'reddit', 'tiktok', 'github', 'custom')]
    [string]$Platform = 'custom',
    [string]$Url = '',
    [ValidateSet('auto', 'browseros', 'agent-browser', 'opentabs')]
    [string]$Backend = 'auto',
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
function Find-ProjectRoot([string]$StartPath) {
    $candidate = [System.IO.DirectoryInfo]::new($StartPath)
    while ($null -ne $candidate) {
        if (Test-Path -LiteralPath (Join-Path $candidate.FullName 'VENDOR_LOCK.md')) {
            return $candidate.FullName
        }
        $candidate = $candidate.Parent
    }
    throw 'Could not locate the Content_Machine project root.'
}

$ProjectRoot = Find-ProjectRoot $PSScriptRoot
$DataRoot = Join-Path $ProjectRoot 'data'
$JobsRoot = Join-Path $DataRoot 'jobs'
$ResultsRoot = Join-Path $DataRoot 'results'
$ProfilesRoot = Join-Path $DataRoot 'browser-profiles'

function Ensure-Directories {
    @($DataRoot, $JobsRoot, $ResultsRoot, $ProfilesRoot) | ForEach-Object {
        New-Item -ItemType Directory -Force -Path $_ | Out-Null
    }
}

function Command-Exists([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-PlatformUrl([string]$Name) {
    switch ($Name) {
        'x' { return 'https://x.com' }
        'facebook' { return 'https://www.facebook.com' }
        'reddit' { return 'https://www.reddit.com' }
        'tiktok' { return 'https://www.tiktok.com' }
        'github' { return 'https://github.com' }
        default {
            if ([string]::IsNullOrWhiteSpace($Url)) {
                throw 'Provide -Url when -Platform is custom.'
            }
            return $Url
        }
    }
}

function Resolve-Backend {
    if ($Backend -ne 'auto') { return $Backend }
    if ((Command-Exists 'browseros-cli') -or (Command-Exists 'bos')) { return 'browseros' }
    if (Command-Exists 'opentabs') { return 'opentabs' }
    if (Command-Exists 'agent-browser') { return 'agent-browser' }
    return 'none'
}

function Show-Help {
    @'
AI Content Machine CLI

  .\cm.ps1 init
  .\cm.ps1 doctor [-Json]
  .\cm.ps1 new -Query "AI news today" -Count 3 -Format auto -Tone skeptical
  .\cm.ps1 prompt [-Job <id>]
  .\cm.ps1 status
  .\cm.ps1 auth -Platform x [-Backend auto]
  .\cm.ps1 open -Url https://example.com [-Backend auto]

The CLI prepares jobs and authenticated browser sessions. Invoke
$ai-content-machine in chat to research, verify, and produce the result.
'@
}

function Initialize-Project {
    Ensure-Directories
    $gitIgnore = Join-Path $ProjectRoot '.gitignore'
    if (-not (Test-Path -LiteralPath $gitIgnore)) {
        @'
data/browser-profiles/
data/auth/
data/**/*.state.json
data/**/*.cookies.json
data/**/*.har
.env
.env.*
'@ | Set-Content -LiteralPath $gitIgnore -Encoding utf8
    }
    Write-Output "Initialized: $ProjectRoot"
}

function Invoke-Doctor {
    Ensure-Directories
    $checks = @(
        [PSCustomObject]@{ Name = 'vendor/BrowserOS'; Ready = Test-Path (Join-Path $ProjectRoot 'vendor\BrowserOS\README.md'); Required = $false },
        [PSCustomObject]@{ Name = 'vendor/agent-browser'; Ready = Test-Path (Join-Path $ProjectRoot 'vendor\agent-browser\README.md'); Required = $true },
        [PSCustomObject]@{ Name = 'vendor/marketingskills'; Ready = Test-Path (Join-Path $ProjectRoot 'vendor\marketingskills\skills'); Required = $true },
        [PSCustomObject]@{ Name = 'vendor/opentabs'; Ready = Test-Path (Join-Path $ProjectRoot 'vendor\opentabs\README.md'); Required = $false },
        [PSCustomObject]@{ Name = 'git'; Ready = Command-Exists 'git'; Required = $true },
        [PSCustomObject]@{ Name = 'node'; Ready = Command-Exists 'node'; Required = $false },
        [PSCustomObject]@{ Name = 'agent-browser CLI'; Ready = Command-Exists 'agent-browser'; Required = $false },
        [PSCustomObject]@{ Name = 'BrowserOS CLI'; Ready = (Command-Exists 'browseros-cli') -or (Command-Exists 'bos'); Required = $false },
        [PSCustomObject]@{ Name = 'OpenTabs CLI'; Ready = Command-Exists 'opentabs'; Required = $false }
    )
    if ($Json) {
        $checks | ConvertTo-Json
    } else {
        $checks | Format-Table -AutoSize
        Write-Output ''
        Write-Output 'At least one browser CLI is needed for authenticated research.'
    }
}

function New-Job {
    Ensure-Directories
    if ([string]::IsNullOrWhiteSpace($Query)) {
        throw 'Provide -Query.'
    }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $id = "content-$stamp"
    $record = [ordered]@{
        id = $id
        phase = 'discover'
        status = 'briefed'
        query = $Query
        title = $Title
        count = $Count
        format = $Format
        tone = $Tone
        audience = $Audience
        platforms = $Platforms -split ',' | ForEach-Object { $_.Trim() }
        created_at = (Get-Date).ToString('o')
        manual_publish = $true
    }
    $path = Join-Path $JobsRoot "$id.json"
    $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding utf8
    Write-Output "Created job: $id"
    Write-Output "Brief: $path"
    Write-Output "Next: .\cm.ps1 prompt -Job $id"
}

function Get-JobPath {
    Ensure-Directories
    if (-not [string]::IsNullOrWhiteSpace($Job)) {
        $candidate = Join-Path $JobsRoot "$Job.json"
        if (-not (Test-Path -LiteralPath $candidate)) { throw "Job not found: $Job" }
        return $candidate
    }
    $latest = Get-ChildItem -LiteralPath $JobsRoot -Filter '*.json' |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $latest) { throw 'No jobs found. Run .\cm.ps1 new first.' }
    return $latest.FullName
}

function Show-Prompt {
    $path = Get-JobPath
    $brief = Get-Content -Raw -LiteralPath $path
    @"
Use `$ai-content-machine for this job.

Read the brief below, run the discover phase, verify primary sources, and return
a concise ranked shortlist. Do not publish anything. Stop for my selection.

Brief:
$brief
"@
}

function Show-Status {
    Ensure-Directories
    $items = foreach ($file in (Get-ChildItem -LiteralPath $JobsRoot -Filter '*.json' | Sort-Object LastWriteTime -Descending)) {
        $jobData = Get-Content -Raw -LiteralPath $file.FullName | ConvertFrom-Json
        [PSCustomObject]@{
            Id = $jobData.id
            Phase = $jobData.phase
            Status = $jobData.status
            Query = $jobData.query
            Created = $jobData.created_at
        }
    }
    if ($Json) { $items | ConvertTo-Json } else { $items | Format-Table -AutoSize }
}

function Open-AuthenticatedBrowser([string]$TargetUrl) {
    Ensure-Directories
    $selected = Resolve-Backend
    switch ($selected) {
        'browseros' {
            $cli = if (Command-Exists 'browseros-cli') { 'browseros-cli' } else { 'bos' }
            & $cli launch | Out-Host
            & $cli open $TargetUrl | Out-Host
        }
        'opentabs' {
            Start-Process 'opentabs' -ArgumentList 'start'
            Start-Process $TargetUrl
            Write-Output 'OpenTabs started. Log in manually and keep the tab open.'
        }
        'agent-browser' {
            $profile = Join-Path $ProfilesRoot $Platform
            & agent-browser --profile $profile open $TargetUrl --headed | Out-Host
        }
        default {
            Start-Process $TargetUrl
            Write-Output 'No supported browser CLI found. Opened the system browser for manual login.'
        }
    }
}

switch ($Command) {
    'help' { Show-Help }
    'init' { Initialize-Project }
    'doctor' { Invoke-Doctor }
    'new' { New-Job }
    'prompt' { Show-Prompt }
    'status' { Show-Status }
    'auth' { Open-AuthenticatedBrowser (Get-PlatformUrl $Platform) }
    'open' {
        if ([string]::IsNullOrWhiteSpace($Url)) { throw 'Provide -Url.' }
        Open-AuthenticatedBrowser $Url
    }
}
