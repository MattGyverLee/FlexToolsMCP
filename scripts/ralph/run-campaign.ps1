<#
.SYNOPSIS
    Outer Ralph driver: walks the LEX crew through parser-check CP3..CP6, one
    bounded spurt per FRESH `claude -p` session.

.DESCRIPTION
    The ralph-loop plugin's Stop hook loops IN-SESSION, so context accumulates
    across iterations. This driver loops OUTSIDE the session instead: every
    spurt is a new `claude -p` process with an empty context window. Continuity
    comes from the files the crew already maintains -- STATUS.md, the
    per-feature .crew-handoff.json, tasks.md checkboxes, and git history.

    Per iteration the driver:
      1. reads specs/<feature>/.crew-handoff.json to decide whether to continue,
      2. renders scripts/ralph/prompts/spurt.md for the active checkpoint,
      3. runs one fresh `claude -p` session on that prompt,
      4. reads the handoff again and branches:
           in_progress      -> next fresh session
           needs_human      -> STOP, surface the blocker
           feature_complete -> advance to the next checkpoint
      5. stops on a stall (no commit AND no handoff change) twice running.

.EXAMPLE
    powershell -File scripts/ralph/run-campaign.ps1 -Only CP3 -DryRun
    powershell -File scripts/ralph/run-campaign.ps1 -Only CP3
    powershell -File scripts/ralph/run-campaign.ps1 -StopAfter CP3 -MaxIterations 8
#>
[CmdletBinding()]
param(
    [string] $Campaign = 'scripts/ralph/campaign.json',
    [string] $Only,
    [string] $StopAfter,
    [int]    $MaxIterations = 12,
    [double] $MaxBudgetUsd = 15,
    [string] $Model = 'opus',
    [ValidateSet('acceptEdits', 'bypassPermissions', 'auto', 'dontAsk')]
    [string] $PermissionMode = 'bypassPermissions',
    [int]    $AutoCompactTokens = 300000,
    [switch] $AllowWriteCheckpoints,
    [switch] $IgnoreDependencies,
    [switch] $NoPush,
    [switch] $DryRun
)

$ErrorActionPreference = 'Stop'

# The prompt is piped into a native exe; pin the pipe to UTF-8 without a BOM so
# Windows PowerShell 5.1 does not hand claude the ANSI codepage.
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Write-Banner([string] $Text, [string] $Color = 'Cyan') {
    Write-Host ''
    Write-Host ('=' * 78) -ForegroundColor $Color
    Write-Host $Text -ForegroundColor $Color
    Write-Host ('=' * 78) -ForegroundColor $Color
}

function Get-RepoRoot {
    $root = & git rev-parse --show-toplevel
    if ($LASTEXITCODE -ne 0) { throw 'Not inside a git repository.' }
    return ($root -replace '/', '\')
}

function Get-SpecResolution([string] $FeatureDir) {
    # Ask the Companion resolver where the pipeline actually is. It prints a
    # trailing `RESOLUTION: {json}` line that /speckit.companion.resume parses
    # deterministically; we parse the same line to pick a prompt.
    # Read-only -- this never writes .spec-context.json.
    $script = '.specify/extensions/companion/scripts/status-context.py'
    if (-not (Test-Path $script)) { return $null }
    try {
        $out = & python $script --feature-dir $FeatureDir 2>$null
    }
    catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
    $line = @($out) | Where-Object { $_ -match '^RESOLUTION:' } | Select-Object -Last 1
    if (-not $line) { return $null }
    try {
        return ($line -replace '^RESOLUTION:\s*', '') | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Get-HandoffState([string] $Path) {
    if (-not (Test-Path $Path)) {
        return [pscustomobject]@{ Exists = $false; Status = 'absent'; Blocker = $null; Entry = $null; Hash = '' }
    }
    $raw = Get-Content -Raw -Path $Path
    $md5 = [System.Security.Cryptography.MD5]::Create()
    $hash = [System.BitConverter]::ToString($md5.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($raw))).Replace('-', '')
    try {
        $json = $raw | ConvertFrom-Json
    }
    catch {
        return [pscustomobject]@{ Exists = $true; Status = 'unparseable'; Blocker = $null; Entry = $null; Hash = $hash }
    }
    return [pscustomobject]@{
        Exists  = $true
        Status  = $json.status
        Blocker = $json.blocker
        Entry   = $json.next_entry
        Hash    = $hash
    }
}

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------
$repo = Get-RepoRoot
Set-Location $repo

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    throw 'claude CLI not found on PATH.'
}

if (Test-Path '.claude/ralph-loop.local.md') {
    throw 'An in-session ralph-loop is active (.claude/ralph-loop.local.md exists). Cancel it with /ralph-loop:cancel-ralph first -- an in-session loop and this driver would fight over iteration and defeat the fresh-context design.'
}

$campaignPath = Join-Path $repo $Campaign
if (-not (Test-Path $campaignPath)) { throw "Campaign file not found: $campaignPath" }
$plan = Get-Content -Raw $campaignPath | ConvertFrom-Json

$spurtTemplate = Get-Content -Raw (Join-Path $repo 'scripts/ralph/prompts/spurt.md')
$resumeTemplate = Get-Content -Raw (Join-Path $repo 'scripts/ralph/prompts/resume.md')

$checkpoints = @($plan.checkpoints)
if ($Only) { $checkpoints = @($checkpoints | Where-Object { $_.id -eq $Only }) }
if ($checkpoints.Count -eq 0) { throw "No checkpoints selected (did -Only '$Only' match an id?)." }

$runStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$runDir = Join-Path $repo "reports/ralph/$runStamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$doPush = ($plan.push -eq $true) -and (-not $NoPush)

Write-Banner "Ralph campaign: $($plan.campaign)"
Write-Host "  repo            : $repo"
Write-Host "  checkpoints     : $(($checkpoints | ForEach-Object { $_.id }) -join ', ')"
Write-Host "  model           : $Model"
Write-Host "  permission mode : $PermissionMode  (prompts: none -- nothing can hang on a human)"
Write-Host "  autocompact at  : $AutoCompactTokens tokens"
Write-Host "  budget/iteration: $MaxBudgetUsd USD"
Write-Host "  push spurts     : $doPush"
Write-Host "  logs            : $runDir"
if ($DryRun) { Write-Host '  DRY RUN -- prompts are rendered, no session is started.' -ForegroundColor Yellow }

# --------------------------------------------------------------------------
# Checkpoint walk
# --------------------------------------------------------------------------
foreach ($cp in $checkpoints) {

    Write-Banner "$($cp.id) -- $($cp.title)" 'Green'

    if ($cp.writes -eq $true -and (-not $AllowWriteCheckpoints)) {
        Write-Host "[STOP] $($cp.id) is a WRITE checkpoint; this driver will not run it unattended." -ForegroundColor Yellow
        Write-Host "       $($cp.unattended_note)" -ForegroundColor Yellow
        Write-Host "       Re-run with -AllowWriteCheckpoints -Only $($cp.id) to automate its spec/plan" -ForegroundColor Yellow
        Write-Host '       passes only; the spurt prompt still forbids a live write.' -ForegroundColor Yellow
        break
    }

    # ---- predecessor gate ------------------------------------------------
    # depends_on reads "<feature-slug> at feature_complete". A checkpoint that
    # starts on top of an unfinished predecessor plans against a moving spec.
    if ($cp.depends_on -and (-not $IgnoreDependencies)) {
        $depSlug = ([string]$cp.depends_on -split '\s+at\s+')[0].Trim()
        $depHandoff = Join-Path $repo "specs/$depSlug/.crew-handoff.json"
        $depState = Get-HandoffState $depHandoff
        if ($depState.Status -ne 'feature_complete') {
            Write-Host "[STOP] $($cp.id) depends on '$depSlug' at feature_complete, but its" -ForegroundColor Yellow
            Write-Host "       handoff status is '$($depState.Status)'." -ForegroundColor Yellow
            if ($depState.Entry) { Write-Host "       predecessor next_entry: $($depState.Entry)" -ForegroundColor DarkGray }
            Write-Host '       Finish the predecessor first, or pass -IgnoreDependencies.' -ForegroundColor Yellow
            break
        }
    }

    $handoffPath = Join-Path $repo "$($cp.feature_dir)/.crew-handoff.json"
    $stall = 0

    for ($i = 1; $i -le $MaxIterations; $i++) {

        $state = Get-HandoffState $handoffPath

        if ($state.Status -eq 'feature_complete') {
            Write-Host "[DONE] $($cp.id) is feature_complete." -ForegroundColor Green
            break
        }
        if ($state.Status -eq 'needs_human') {
            Write-Host "[HALT] $($cp.id) needs a human decision:" -ForegroundColor Yellow
            Write-Host "       $($state.Blocker)"
            Write-Host '       Resolve it, set status back to in_progress, then re-run.'
            exit 2
        }

        # ---- pick the prompt: crew briefing, or the thin resume leg ---------
        # Once the pipeline is inside implement with an unchecked task, the
        # Companion resolver knows exactly where to restart (tasks.md order vs
        # journaled checkboxes). That beats re-deriving position from prose, so
        # the session gets a short "resume, then hand off" brief instead.
        $res = Get-SpecResolution $cp.feature_dir
        $useResume = ($null -ne $res) -and ($null -ne $res.nextTask) -and ($res.nextTask -ne '')

        if ($useResume) {
            $promptTemplate = $resumeTemplate
            $promptKind = "resume @ $($res.nextTask)"
        }
        else {
            $promptTemplate = $spurtTemplate
            $promptKind = 'crew spurt'
            if ($null -ne $res -and $res.currentStep) { $promptKind += " (step: $($res.currentStep))" }
        }

        # ---- render the prompt for this iteration ---------------------------
        $pushClause = ''
        if ($doPush) { $pushClause = ', then push it to the current branch' }
        $refs = (@($cp.scope_refs) | ForEach-Object { "`n   - $_" }) -join ''

        $prompt = $promptTemplate
        if ($null -ne $res) {
            $prompt = $prompt.Replace('{{CURRENT_STEP}}', [string]$res.currentStep)
            $prompt = $prompt.Replace('{{SPEC_STATUS}}', [string]$res.status)
            $prompt = $prompt.Replace('{{NEXT_TASK}}', [string]$res.nextTask)
            $prompt = $prompt.Replace('{{NEXT_COMMAND}}', [string]$res.nextCommand)
        }
        $prompt = $prompt.Replace('{{CP}}', [string]$cp.id)
        $prompt = $prompt.Replace('{{CP_LOWER}}', ([string]$cp.id).ToLower())
        $prompt = $prompt.Replace('{{TITLE}}', [string]$cp.title)
        $prompt = $prompt.Replace('{{FEATURE}}', [string]$cp.feature)
        $prompt = $prompt.Replace('{{FEATURE_DIR}}', [string]$cp.feature_dir)
        $prompt = $prompt.Replace('{{PARENT_SPEC}}', [string]$plan.parent_spec)
        $prompt = $prompt.Replace('{{ROADMAP_SECTION}}', [string]$plan.roadmap_section)
        $prompt = $prompt.Replace('{{SCOPE}}', [string]$cp.scope)
        $prompt = $prompt.Replace('{{SCOPE_REFS}}', $refs)
        $prompt = $prompt.Replace('{{ITERATION}}', [string]$i)
        $prompt = $prompt.Replace('{{MAX_ITERATIONS}}', [string]$MaxIterations)
        $prompt = $prompt.Replace('{{PUSH_CLAUSE}}', $pushClause)

        $tag = '{0}-iter{1:d2}' -f $cp.id, $i
        $promptFile = Join-Path $runDir "$tag.prompt.md"
        $rawLog = Join-Path $runDir "$tag.jsonl"
        Set-Content -Path $promptFile -Value $prompt -Encoding ascii

        Write-Host ''
        Write-Host "--- $tag  (handoff: $($state.Status) | prompt: $promptKind) ---" -ForegroundColor Cyan
        if ($state.Entry) { Write-Host "    next_entry: $($state.Entry)" -ForegroundColor DarkGray }

        if ($DryRun) {
            Write-Host "    [DRY RUN] prompt rendered to $promptFile"
            break
        }

        # ---- state fingerprint before the session ---------------------------
        $headBefore = (& git rev-parse HEAD)
        $hashBefore = $state.Hash

        # ---- one fresh session ----------------------------------------------
        $claudeArgs = @(
            '-p'
            '--model', $Model
            '--permission-mode', $PermissionMode
            '--permission-prompts', 'none'
            '--output-format', 'stream-json'
            '--verbose'
            '--autocompact', "$AutoCompactTokens"
            '--max-budget-usd', "$MaxBudgetUsd"
            '--name', "ralph-$tag"
        )
        foreach ($d in @($cp.extra_dirs)) {
            if ($d) { $claudeArgs += @('--add-dir', $d) }
        }

        $env:SPECIFY_FEATURE_DIRECTORY = $cp.feature_dir

        $started = Get-Date
        $prompt | & claude @claudeArgs | ForEach-Object {
            Add-Content -Path $rawLog -Value $_ -Encoding utf8
            $line = $_
            if (-not $line.StartsWith('{')) { return }
            try { $o = $line | ConvertFrom-Json } catch { return }
            if ($o.type -eq 'assistant' -and $o.message.content) {
                foreach ($b in $o.message.content) {
                    if ($b.type -eq 'tool_use') {
                        Write-Host "    . $($b.name)" -ForegroundColor DarkGray
                    }
                    elseif ($b.type -eq 'text' -and $b.text -and $b.text.Trim()) {
                        $first = ($b.text -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
                        if ($first.Length -gt 110) { $first = $first.Substring(0, 110) + '...' }
                        Write-Host "    | $first"
                    }
                }
            }
            elseif ($o.type -eq 'result') {
                $cost = [math]::Round([double]$o.total_cost_usd, 2)
                Write-Host "    result: is_error=$($o.is_error)  turns=$($o.num_turns)  cost=$cost USD" -ForegroundColor Cyan
            }
        }
        $sessionExit = $LASTEXITCODE
        $elapsed = [math]::Round(((Get-Date) - $started).TotalMinutes, 1)
        Write-Host "    session exited $sessionExit after $elapsed min" -ForegroundColor DarkGray

        if ($sessionExit -ne 0) {
            Write-Host "[HALT] claude exited $sessionExit. Log: $rawLog" -ForegroundColor Red
            exit 1
        }

        # ---- did anything actually move? ------------------------------------
        $headAfter = (& git rev-parse HEAD)
        $stateAfter = Get-HandoffState $handoffPath
        $moved = ($headAfter -ne $headBefore) -or ($stateAfter.Hash -ne $hashBefore)

        if ($moved) {
            $stall = 0
        }
        else {
            $stall++
            Write-Host "[WARN] iteration $i produced no commit and no handoff change (stall $stall/2)." -ForegroundColor Yellow
            if ($stall -ge 2) {
                Write-Host '[HALT] two stalled iterations in a row -- stopping so you can look.' -ForegroundColor Red
                exit 3
            }
        }

        if ($i -eq $MaxIterations) {
            Write-Host "[HALT] hit -MaxIterations ($MaxIterations) on $($cp.id)." -ForegroundColor Yellow
            exit 4
        }
    }

    if ($StopAfter -and $cp.id -eq $StopAfter) {
        Write-Host "[STOP] -StopAfter $StopAfter reached." -ForegroundColor Green
        break
    }
}

Write-Banner 'Campaign run finished.' 'Green'
Write-Host "Logs: $runDir"
exit 0
