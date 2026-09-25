<#
.SYNOPSIS
  Drive HermitCrab (hc) outside FieldWorks for the FLExTools MCP sandbox spine.

.DESCRIPTION
  Packaged driver for the parser-check CP5 sandbox spine. The interface between
  the MCP and this script is specs/parser-check-cp5/contracts/hcparse.md; keep
  the two in step.

  Modes:
    Generate  Copy the allowlisted project files into -WorkDir, run
              GenerateHCConfig on the copy, write the config to -ConfigOut.
    Parse     Run hc over -Config for the words in -WordFile or -Words.
    Test      Run hc over -Config for the assertions in -AssertionFile.

  Targets Windows PowerShell 5.1. Do not use PowerShell 7 syntax here: no
  null-coalescing, no null-conditional member access, no ternary, and no
  pipeline chain operators.

  The script never opens the project through LCM and never writes inside a
  project folder. Every tool path (hc, GenerateHCConfig) is passed in by the
  MCP; none is hard-coded here (FR-002).

  Console output is ASCII-only progress prose for a human (FR-021). The MCP
  never parses it (FR-023): the outcome of an invocation is in run.json.

.NOTES
  Invocation (the MCP builds this as an argv list, never a command string,
  with stdin closed):

    powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <hcparse.ps1> <params>

  Exit codes (the script's own, not hc's):

    0  The invocation completed. The outcome is in run.json; 0 does not mean
       the words parsed.
    1  Unexpected script error (not part of the contract; run.json is still
       written when the invocation got past parameter validation).
    2  A bad parameter or a missing input file. No run.json is written.
    3  -ConfigOut was refused (under a sandboxes directory). Nothing is written.
    4  Generation failed (details in run.json).
    5  hc failed to start (Load Error / IO Error, exit -1).
    6  Timeout (hc or the generator was killed).

  Encoding lessons carried over from the contributed root-level script (H11):
    - Word files are read with Get-Content -Encoding UTF8. PS 5.1 otherwise
      reads a BOM-less file in the ANSI code page and mangles non-Latin words.
    - -Words is split on [,\s]+ because `-File` delivers a comma list as one
      string.
    - hc-script.txt is written as UTF-8 without a BOM:
      [IO.File]::WriteAllLines(p, lines, (New-Object Text.UTF8Encoding($false)))
#>
[CmdletBinding()]
param(
    # Generate | Parse | Test. Validated in Assert-Parameters rather than with
    # [ValidateSet()]: a binding failure under `-File` exits 1, and the
    # contract wants 2 for a bad parameter. The same goes for the [string]
    # timeouts below.
    [string]$Mode,

    # Parse, Test: an hc.exe, or an hc.dll run as `dotnet <dll>`.
    [string]$HcPath,

    # Generate: the GenerateHCConfig executable.
    [string]$GenerateHCConfigPath,

    # Generate: absolute path to the live .fwdata. It is only read.
    [string]$FwData,

    # Generate: created by the MCP, holds the marker. Emptied in finally.
    [string]$WorkDir,

    # Generate: the output config path. Refused (exit 3) under `sandboxes`.
    [string]$ConfigOut,

    # Parse, Test: the hc-config.xml to run.
    [string]$Config,

    # Parse: UTF-8, one word per line.
    [string]$WordFile,

    # Parse: stand-alone use; split on [,\s]+.
    [string[]]$Words,

    # Test: the corpus JSON (data-model section 5).
    [string]$AssertionFile,

    # All modes: destination for this invocation's files.
    [string]$RunDir,

    # Parse, Test: wall clock for the hc process.
    [string]$TimeoutSeconds,

    # Generate: wall clock for the generator (covers the SLDR start-up).
    [string]$GenerateTimeoutSeconds = '600'
)

$script:HCPARSE_VERSION = '5.0.0'

Set-StrictMode -Version 3.0
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Script state
# ---------------------------------------------------------------------------

# The exit code the script ends with. Set by Stop-Hcparse; a mode function that
# returns normally leaves it at 0.
$script:ExitCode = 0
# True once Stop-Hcparse raised the current error (as opposed to a crash).
$script:Stopped = $false

# run.json sections. Mode functions fill these; Write-RunJson serialises them.
#   Generate -> $script:Run.generate, $script:Run.copy
#   Parse/Test -> $script:Run.hc, $script:Run.items
$script:Run = [ordered]@{
    generate = $null
    hc       = $null
    copy     = $null
    items    = $null
    error    = $null
}
$script:StartedAt = $null
# Validated timeouts as ints, set by Assert-Parameters. Mode functions use these
# rather than the raw [string] parameters.
$script:HcTimeout = 0
$script:GenerateTimeout = 0
# Test mode: the corpus assertions, read and checked by Assert-Parameters.
$script:Corpus = $null

# ---------------------------------------------------------------------------
# Output helpers (ASCII only, FR-021)
# ---------------------------------------------------------------------------

function ConvertTo-AsciiText {
    param([AllowNull()][string]$Text)
    if ($null -eq $Text) { return '' }
    $sb = New-Object System.Text.StringBuilder
    foreach ($ch in $Text.ToCharArray()) {
        $code = [int]$ch
        if (($code -ge 32 -and $code -le 126) -or $code -eq 9) {
            [void]$sb.Append($ch)
        } else {
            [void]$sb.Append('?')
        }
    }
    return $sb.ToString()
}

function Write-HcLog {
    # Progress prose for a human. Never parsed by the MCP.
    param([string]$Message)
    Write-Host ('hcparse: ' + (ConvertTo-AsciiText $Message))
}

function Write-HcError {
    param([string]$Message)
    [Console]::Error.WriteLine('hcparse: error: ' + (ConvertTo-AsciiText $Message))
}

function Stop-Hcparse {
    # End the invocation with one of the contract's exit codes.
    param(
        [Parameter(Mandatory = $true)][int]$Code,
        [Parameter(Mandatory = $true)][string]$Message
    )
    $script:ExitCode = $Code
    $script:Stopped = $true
    throw $Message
}

# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

function Get-Utf8NoBom {
    return (New-Object System.Text.UTF8Encoding($false))
}

function Write-Utf8Lines {
    # H11 verbatim: UTF-8, no BOM.
    param([string]$Path, [string[]]$Lines)
    [System.IO.File]::WriteAllLines($Path, $Lines, (New-Object Text.UTF8Encoding($false)))
}

function Write-Utf8Text {
    param([string]$Path, [string]$Text)
    [System.IO.File]::WriteAllText($Path, $Text, (Get-Utf8NoBom))
}

function Get-IsoUtc {
    param([DateTime]$When)
    return $When.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
}

# ---------------------------------------------------------------------------
# Parameter validation (exit 2 / 3; runs before anything is written)
# ---------------------------------------------------------------------------

function Assert-Required {
    param([string]$Name, [AllowNull()][string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        Stop-Hcparse -Code 2 -Message ("-$Name is required in -Mode $Mode.")
    }
}

function Assert-FileExists {
    param([string]$Name, [string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Stop-Hcparse -Code 2 -Message ("-$Name file not found: $Path")
    }
}

function Assert-DirectoryExists {
    param([string]$Name, [string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        Stop-Hcparse -Code 2 -Message ("-$Name directory not found: $Path")
    }
}

function Get-SandboxRoot {
    # The MCP's parse root: FLEXTOOLSMCP_PARSE_SANDBOX_DIR, else
    # ~/.flextoolsmcp/parse (sandbox/paths.py).
    $override = [Environment]::GetEnvironmentVariable('FLEXTOOLSMCP_PARSE_SANDBOX_DIR')
    if (-not [string]::IsNullOrWhiteSpace($override)) {
        return [System.IO.Path]::GetFullPath($override)
    }
    $userHome = [Environment]::GetFolderPath('UserProfile')
    return [System.IO.Path]::GetFullPath((Join-Path (Join-Path $userHome '.flextoolsmcp') 'parse'))
}

function Test-PathUnder {
    # True when $Path (already full) is $Root or inside it. Case-insensitive.
    param([string]$Path, [string]$Root)
    $p = $Path.TrimEnd('\', '/')
    $r = $Root.TrimEnd('\', '/')
    if ($p.Equals($r, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    return $p.StartsWith($r + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Assert-ConfigOutAllowed {
    # FR-026: refuse (exit 3) a -ConfigOut that resolves under the `sandboxes`
    # directory of the sandbox root. A second, independent gate behind
    # cache.py being the only caller that passes -ConfigOut (R-12).
    param([string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    $sandboxes = Join-Path (Get-SandboxRoot) 'sandboxes'
    if (Test-PathUnder -Path $full -Root $sandboxes) {
        Stop-Hcparse -Code 3 -Message ("-ConfigOut is under the sandboxes root and is refused: $full")
    }
}

function ConvertTo-PositiveSeconds {
    # Returns the value as an int, or stops with exit 2.
    param([string]$Name, [AllowNull()][string]$Value)
    $parsed = 0
    if ([string]::IsNullOrWhiteSpace($Value) -or
        (-not [int]::TryParse($Value, [ref]$parsed)) -or
        ($parsed -le 0)) {
        Stop-Hcparse -Code 2 -Message ("-$Name is required in -Mode $Mode and must be a positive whole number of seconds.")
    }
    return $parsed
}

function Assert-Parameters {
    if ([string]::IsNullOrWhiteSpace($Mode)) {
        Stop-Hcparse -Code 2 -Message '-Mode is required: Generate, Parse or Test.'
    }
    $canonical = $null
    foreach ($name in @('Generate', 'Parse', 'Test')) {
        if ($Mode -ieq $name) { $canonical = $name }
    }
    if ($null -eq $canonical) {
        Stop-Hcparse -Code 2 -Message ("-Mode must be Generate, Parse or Test, not: $Mode")
    }
    $script:Mode = $canonical

    Assert-Required -Name 'RunDir' -Value $RunDir
    Assert-DirectoryExists -Name 'RunDir' -Path $RunDir

    switch ($Mode) {
        'Generate' {
            Assert-Required -Name 'GenerateHCConfigPath' -Value $GenerateHCConfigPath
            Assert-Required -Name 'FwData' -Value $FwData
            Assert-Required -Name 'WorkDir' -Value $WorkDir
            Assert-Required -Name 'ConfigOut' -Value $ConfigOut
            $script:GenerateTimeout = ConvertTo-PositiveSeconds -Name 'GenerateTimeoutSeconds' -Value $GenerateTimeoutSeconds
            Assert-FileExists -Name 'GenerateHCConfigPath' -Path $GenerateHCConfigPath
            Assert-FileExists -Name 'FwData' -Path $FwData
            Assert-DirectoryExists -Name 'WorkDir' -Path $WorkDir
            Assert-ConfigOutAllowed -Path $ConfigOut
        }
        'Parse' {
            Assert-Required -Name 'HcPath' -Value $HcPath
            Assert-Required -Name 'Config' -Value $Config
            if ([string]::IsNullOrWhiteSpace($WordFile) -and (-not $Words)) {
                Stop-Hcparse -Code 2 -Message 'Supply -WordFile or -Words in -Mode Parse.'
            }
            $script:HcTimeout = ConvertTo-PositiveSeconds -Name 'TimeoutSeconds' -Value $TimeoutSeconds
            Assert-FileExists -Name 'HcPath' -Path $HcPath
            Assert-FileExists -Name 'Config' -Path $Config
            if (-not [string]::IsNullOrWhiteSpace($WordFile)) {
                Assert-FileExists -Name 'WordFile' -Path $WordFile
            }
        }
        'Test' {
            Assert-Required -Name 'HcPath' -Value $HcPath
            Assert-Required -Name 'Config' -Value $Config
            Assert-Required -Name 'AssertionFile' -Value $AssertionFile
            $script:HcTimeout = ConvertTo-PositiveSeconds -Name 'TimeoutSeconds' -Value $TimeoutSeconds
            Assert-FileExists -Name 'HcPath' -Path $HcPath
            Assert-FileExists -Name 'Config' -Path $Config
            Assert-FileExists -Name 'AssertionFile' -Path $AssertionFile
            $script:Corpus = Read-Corpus
        }
    }
}

# ---------------------------------------------------------------------------
# run.json (contracts/hcparse.md section 5)
# ---------------------------------------------------------------------------

function Get-RunInputs {
    $inputs = [ordered]@{}
    switch ($Mode) {
        'Generate' {
            $inputs.fwdata = $FwData
            $inputs.config_out = $ConfigOut
            $inputs.timeout_seconds = $script:GenerateTimeout
        }
        default {
            $inputs.config = $Config
            $inputs.word_count = $null
            $inputs.timeout_seconds = $script:HcTimeout
            if ($null -ne $script:Run.items) {
                $inputs.word_count = @($script:Run.items).Count
            }
        }
    }
    return $inputs
}

function Write-RunJson {
    # Written in the top-level finally of every invocation that got past
    # parameter validation. Python reads it first; the exit code is only a
    # cross-check.
    $ended = [DateTime]::UtcNow
    $doc = [ordered]@{
        schema          = 'flextoolsmcp.hcparse-run/1'
        hcparse_version = $script:HCPARSE_VERSION
        mode            = $Mode.ToLowerInvariant()
        exit_code       = $script:ExitCode
        inputs          = (Get-RunInputs)
        started_at      = (Get-IsoUtc $script:StartedAt)
        ended_at        = (Get-IsoUtc $ended)
        duration_ms     = [int64]($ended - $script:StartedAt).TotalMilliseconds
    }
    if ($Mode -eq 'Generate') {
        $doc.generate = $script:Run.generate
        $doc.copy = $script:Run.copy
    } else {
        $doc.hc = $script:Run.hc
        $doc.items = $script:Run.items
    }
    if ($null -ne $script:Run.error) {
        $doc.error = $script:Run.error
    }
    $json = $doc | ConvertTo-Json -Depth 10
    Write-Utf8Text -Path (Join-Path $RunDir 'run.json') -Text $json
}

# ---------------------------------------------------------------------------
# Process helpers (shared by every mode)
# ---------------------------------------------------------------------------

# The MCP's marker in -WorkDir (data-model section 2). The script never
# deletes it; SandboxClient removes the whole work/<run_id>/ afterwards.
$script:WorkMarker = '.flextoolsmcp-sandbox-work'

function ConvertTo-ProcessArgument {
    # Quote one argument for CommandLineToArgvW / the MSVC runtime.
    param([string]$Value)
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append('"')
    $slashes = 0
    foreach ($ch in $Value.ToCharArray()) {
        if ($ch -eq '\') {
            $slashes++
            continue
        }
        if ($ch -eq '"') {
            [void]$sb.Append('\', (2 * $slashes + 1))
        } elseif ($slashes -gt 0) {
            [void]$sb.Append('\', $slashes)
        }
        $slashes = 0
        [void]$sb.Append($ch)
    }
    if ($slashes -gt 0) { [void]$sb.Append('\', (2 * $slashes)) }
    [void]$sb.Append('"')
    return $sb.ToString()
}

function New-ToolProcess {
    # A System.Diagnostics.Process for a tool path passed in by the MCP. An
    # .dll is run as `dotnet <dll>` (research R-03). stdin is redirected so
    # it can be closed at once: a tool never waits on the console.
    param([string]$ToolPath, [string[]]$Arguments, [string]$WorkingDirectory)
    $argv = @()
    $file = [System.IO.Path]::GetFullPath($ToolPath)
    if ($file -match '\.dll$') {
        $argv += $file
        $file = 'dotnet'
    }
    $argv += $Arguments
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $file
    $psi.Arguments = (($argv | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' ')
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    if (-not [string]::IsNullOrWhiteSpace($WorkingDirectory)) {
        $psi.WorkingDirectory = $WorkingDirectory
    }
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    return $proc
}

function Stop-ProcessTree {
    # taskkill /T /F, run as a process (not a native call, so its output and
    # any localised message never reach this console), then Kill() as a
    # fallback for the root.
    param([System.Diagnostics.Process]$Process)
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = 'taskkill.exe'
        $psi.Arguments = '/T /F /PID ' + $Process.Id
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $kill = [System.Diagnostics.Process]::Start($psi)
        [void]$kill.StandardOutput.ReadToEnd()
        [void]$kill.StandardError.ReadToEnd()
        [void]$kill.WaitForExit(15000)
    } catch {
        Write-HcLog ('taskkill failed: ' + $_.Exception.Message)
    }
    try {
        if (-not $Process.HasExited) { $Process.Kill() }
    } catch { }
    try { [void]$Process.WaitForExit(15000) } catch { }
}

function Remove-WithRetry {
    # Delete one file or directory tree; retry a sharing violation 3 times,
    # 200 ms apart (research R-11). Returns $true when it is gone.
    param([string]$Path)
    for ($attempt = 0; $attempt -lt 4; $attempt++) {
        try {
            if (Test-Path -LiteralPath $Path) {
                Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            }
            return $true
        } catch {
            if ($attempt -lt 3) { Start-Sleep -Milliseconds 200 }
        }
    }
    return (-not (Test-Path -LiteralPath $Path))
}

function Clear-WorkDir {
    # FR-011: remove everything in -WorkDir except the MCP's marker.
    $ok = $true
    if (-not (Test-Path -LiteralPath $WorkDir -PathType Container)) { return $true }
    foreach ($child in @(Get-ChildItem -LiteralPath $WorkDir -Force)) {
        if ($child.Name -eq $script:WorkMarker) { continue }
        if (-not (Remove-WithRetry -Path $child.FullName)) { $ok = $false }
    }
    return $ok
}

function Copy-FileShared {
    # Copy a file that FieldWorks may hold open: read with FileShare.ReadWrite.
    param([string]$Source, [string]$Destination)
    $in = [System.IO.File]::Open($Source, [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try {
        $out = [System.IO.File]::Open($Destination, [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        try { $in.CopyTo($out) } finally { $out.Dispose() }
    } finally {
        $in.Dispose()
    }
    return (New-Object System.IO.FileInfo($Destination)).Length
}

function Copy-Allowlist {
    # FR-008 / R-11: the copy is an allowlist, `<name>.fwdata` plus
    # `WritingSystemStore\**`. The lock marker, .hg, LinkedFiles, Backups and
    # everything else are left behind by construction. Returns the bytes
    # copied and the copied .fwdata path.
    $source = [System.IO.Path]::GetFullPath($FwData)
    $projectDir = [System.IO.Path]::GetDirectoryName($source)
    $name = [System.IO.Path]::GetFileNameWithoutExtension($source)
    $destDir = Join-Path $WorkDir $name
    [void](New-Item -ItemType Directory -Path $destDir -Force)
    $copied = Join-Path $destDir ([System.IO.Path]::GetFileName($source))
    $bytes = [int64](Copy-FileShared -Source $source -Destination $copied)

    $wsSource = Join-Path $projectDir 'WritingSystemStore'
    if (Test-Path -LiteralPath $wsSource -PathType Container) {
        $wsDest = Join-Path $destDir 'WritingSystemStore'
        [void](New-Item -ItemType Directory -Path $wsDest -Force)
        $prefix = (Get-Item -LiteralPath $wsSource).FullName.TrimEnd('\') + '\'
        foreach ($item in @(Get-ChildItem -LiteralPath $wsSource -Recurse -Force)) {
            $rel = $item.FullName.Substring($prefix.Length)
            $target = Join-Path $wsDest $rel
            if ($item.PSIsContainer) {
                [void](New-Item -ItemType Directory -Path $target -Force)
            } elseif ($item.Name -notlike '*.lock') {
                $parent = [System.IO.Path]::GetDirectoryName($target)
                if (-not (Test-Path -LiteralPath $parent)) {
                    [void](New-Item -ItemType Directory -Path $parent -Force)
                }
                $bytes += [int64](Copy-FileShared -Source $item.FullName -Destination $target)
            }
        }
    }
    return @{ bytes = $bytes; fwdata = $copied }
}

# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

function Invoke-GenerateMode {
    # Copy the allowlist into -WorkDir, run the generator on the copy under
    # -GenerateTimeoutSeconds with its output logged verbatim, judge it by
    # R-05's three conditions, clear -WorkDir in finally. Exit codes 0, 4, 6.
    $script:Run.generate = [ordered]@{
        exit_code         = $null
        timed_out         = $false
        config_bytes      = 0
        writing_completed = $false
    }
    $script:Run.copy = [ordered]@{ bytes = 0; deleted = $false }
    $logPath = Join-Path $RunDir 'generate-config.log'
    $configFull = [System.IO.Path]::GetFullPath($ConfigOut)
    try {
        $copy = $null
        try {
            $copy = Copy-Allowlist
        } catch {
            Stop-Hcparse -Code 4 -Message ('Could not copy the project: ' + $_.Exception.Message)
        }
        $script:Run.copy.bytes = $copy.bytes
        Write-HcLog ('copied ' + $copy.bytes + ' bytes; running the generator')

        $proc = New-ToolProcess -ToolPath $GenerateHCConfigPath `
            -Arguments @($copy.fwdata, $configFull) -WorkingDirectory $WorkDir
        $outBuf = New-Object System.IO.MemoryStream
        $errBuf = New-Object System.IO.MemoryStream
        try {
            [void]$proc.Start()
        } catch {
            Write-Utf8Text -Path $logPath -Text ''
            Stop-Hcparse -Code 4 -Message ('The generator did not start: ' + $_.Exception.Message)
        }
        $timedOut = $false
        try {
            $proc.StandardInput.Close()
            # Raw bytes: the log is the generator's output verbatim (FR-009).
            $outTask = $proc.StandardOutput.BaseStream.CopyToAsync($outBuf)
            $errTask = $proc.StandardError.BaseStream.CopyToAsync($errBuf)
            $timedOut = -not $proc.WaitForExit($script:GenerateTimeout * 1000)
            if ($timedOut) {
                Write-HcLog ('the generator timed out after ' + $script:GenerateTimeout + ' s; killing it')
                Stop-ProcessTree -Process $proc
            } else {
                $proc.WaitForExit()
            }
            [void][System.Threading.Tasks.Task]::WaitAll(
                [System.Threading.Tasks.Task[]]@($outTask, $errTask), 15000)
        } finally {
            $outBytes = $outBuf.ToArray()
            $errBytes = $errBuf.ToArray()
            $stream = [System.IO.File]::Open($logPath, [System.IO.FileMode]::Create)
            try {
                $stream.Write($outBytes, 0, $outBytes.Length)
                if ($errBytes.Length -gt 0) {
                    if ($outBytes.Length -gt 0 -and $outBytes[$outBytes.Length - 1] -ne 10) {
                        $nl = [byte[]](13, 10)
                        $stream.Write($nl, 0, 2)
                    }
                    $stream.Write($errBytes, 0, $errBytes.Length)
                }
            } finally {
                $stream.Dispose()
            }
        }

        $text = (Get-Utf8NoBom).GetString($outBytes)
        $completed = $false
        foreach ($line in ($text -split "\r\n|\r|\n")) {
            if ($line.Trim() -eq 'Writing completed.') { $completed = $true }
        }
        $configBytes = [int64]0
        if (Test-Path -LiteralPath $configFull -PathType Leaf) {
            $configBytes = [int64](Get-Item -LiteralPath $configFull).Length
        }
        $script:Run.generate.timed_out = $timedOut
        $script:Run.generate.writing_completed = $completed
        $script:Run.generate.config_bytes = $configBytes
        if ($timedOut) {
            Stop-Hcparse -Code 6 -Message ('The generator was killed after ' + $script:GenerateTimeout + ' s.')
        }
        $script:Run.generate.exit_code = $proc.ExitCode
        if ($proc.ExitCode -ne 0 -or $configBytes -le 0 -or -not $completed) {
            Stop-Hcparse -Code 4 -Message ('Generation failed (exit ' + $proc.ExitCode +
                '); see generate-config.log.')
        }
        Write-HcLog ('generation completed: ' + $configBytes + ' bytes')
    } finally {
        $script:Run.copy.deleted = (Clear-WorkDir)
    }
}

function Get-WordFault {
    # R-09's not-expressible rule for a word: the reason, or $null.
    param([string]$Word)
    if ($Word.Length -eq 0) { return 'empty' }
    if ($Word -match "[`t`r`n]") { return 'control_character' }
    if ($Word.Contains('"') -and $Word.Contains("'")) { return 'both_quote_characters' }
    return $null
}

function ConvertTo-HcWord {
    # R-09's quoting, so hc's SplitCommandLine yields exactly the word: a
    # word with `"` is single-quoted, any other word double-quoted.
    param([string]$Word)
    if ($Word.Contains('"')) { return "'" + $Word + "'" }
    return '"' + $Word + '"'
}

function New-DispatchItem {
    # $Line and $Reason are untyped: a [string] parameter turns $null into ''.
    param([int]$Index, [string]$Word, $Line, $Reason)
    $flags = @()
    if ($null -ne $Line -and $Word.StartsWith('-')) {
        # [LIVE L-2]: sent, and flagged until confirmed.
        $flags = @('leading_dash_unverified')
    }
    return [ordered]@{
        index  = $Index
        word   = $Word
        sent   = ($null -ne $Line)
        line   = $Line
        reason = $Reason
        flags  = $flags
    }
}

function Get-DispatchItem {
    # One Parse-mode item: `parse <quoted word>`, or not expressible.
    param([int]$Index, [string]$Word)
    $reason = Get-WordFault -Word $Word
    $line = $null
    if ($null -eq $reason) { $line = 'parse ' + (ConvertTo-HcWord -Word $Word) }
    return (New-DispatchItem -Index $Index -Word $Word -Line $line -Reason $reason)
}

function Get-ExpectationFault {
    # FR-027 / F-5 for one form or gloss: the reason, or $null. A backslash
    # is refused because hc's Split loops forever on `\` before a delimiter.
    param([string]$Text)
    if ($Text -match '[|:\\]') { return 'delimiter_in_expectation' }
    if ($Text -match "['`"\s]") { return 'quote_or_space_in_expectation' }
    return $null
}

function Get-TestItem {
    # One Test-mode item: `test -p f:g|f:g [-p ...] [--] <quoted word>`.
    # Every morph is `form:gloss` (F-5); an empty gloss is `?` (F-7). An
    # assertion with no expected parse is `test <quoted word>` with no -p,
    # which hc passes only when the word has no parse.
    param([int]$Index, $Assertion)
    $word = $Assertion.word
    $reason = Get-WordFault -Word $word
    $parts = New-Object System.Collections.Generic.List[string]
    $parts.Add('test')
    if ($null -eq $reason) {
        foreach ($parse in $Assertion.parses) {
            if ($parse.Count -eq 0) { $reason = 'empty_expected_parse'; break }
            $morphs = New-Object System.Collections.Generic.List[string]
            foreach ($morph in $parse) {
                foreach ($text in @($morph.form, $morph.gloss)) {
                    if ($null -eq $reason) { $reason = Get-ExpectationFault -Text $text }
                }
                $gloss = $morph.gloss
                if ($gloss.Length -eq 0) { $gloss = '?' }
                $morphs.Add($morph.form + ':' + $gloss)
            }
            if ($null -ne $reason) { break }
            $parts.Add('-p')
            $parts.Add(($morphs.ToArray() -join '|'))
        }
    }
    $line = $null
    if ($null -eq $reason) {
        if ($word.StartsWith('-')) { $parts.Add('--') }
        $parts.Add((ConvertTo-HcWord -Word $word))
        $line = $parts.ToArray() -join ' '
    }
    return (New-DispatchItem -Index $Index -Word $word -Line $line -Reason $reason)
}

function Test-JsonObject {
    param($Value)
    return ($Value -is [System.Management.Automation.PSCustomObject])
}

function Get-JsonProperty {
    # A property of a ConvertFrom-Json object, or $null (StrictMode-safe).
    param($Object, [string]$Name)
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $null }
    return , $prop.Value
}

function Read-Corpus {
    # The corpus JSON (data-model section 5), checked structurally. Python
    # validates it before the run; any fault here is exit 2, before anything
    # is written. Returns a list of @{word; parses = list of list of
    # @{form; gloss}} in file order.
    $bad = { param($what) Stop-Hcparse -Code 2 -Message ("-AssertionFile is not a valid corpus: $what") }
    $doc = $null
    try {
        $text = [System.IO.File]::ReadAllText($AssertionFile, [System.Text.Encoding]::UTF8)
        $doc = ConvertFrom-Json -InputObject $text
    } catch {
        & $bad 'unreadable JSON'
    }
    if (-not (Test-JsonObject $doc)) { & $bad 'not a JSON object' }
    if ((Get-JsonProperty $doc 'schema') -ne 'flextoolsmcp.hc-corpus/1') { & $bad 'unknown schema' }
    $assertions = Get-JsonProperty $doc 'assertions'
    if ($assertions -isnot [System.Array]) { & $bad 'assertions is not a list' }
    $result = New-Object System.Collections.ArrayList
    $i = 0
    foreach ($a in $assertions) {
        $where = "assertions[$i]"
        if (-not (Test-JsonObject $a)) { & $bad "$where is not an object" }
        $word = Get-JsonProperty $a 'word'
        if ($word -isnot [string]) { & $bad "$where.word is not a string" }
        $expected = Get-JsonProperty $a 'expected'
        if ($expected -isnot [System.Array]) { & $bad "$where.expected is not a list" }
        $parses = New-Object System.Collections.ArrayList
        $j = 0
        foreach ($parse in $expected) {
            if ($parse -isnot [System.Array]) { & $bad "$where.expected[$j] is not a list" }
            $morphs = New-Object System.Collections.ArrayList
            foreach ($morph in $parse) {
                if (-not (Test-JsonObject $morph)) { & $bad "$where.expected[$j] holds a non-object" }
                $form = Get-JsonProperty $morph 'form'
                $gloss = Get-JsonProperty $morph 'gloss'
                if ($form -isnot [string] -or $gloss -isnot [string]) {
                    & $bad "$where.expected[$j] holds a morph without a string form and gloss"
                }
                [void]$morphs.Add(@{ form = $form; gloss = $gloss })
            }
            [void]$parses.Add($morphs)
            $j++
        }
        [void]$result.Add(@{ word = $word; parses = $parses })
        $i++
    }
    return , $result
}

function Read-ParseWords {
    # H11 verbatim: Get-Content -Encoding UTF8 for -WordFile; -Words split
    # on [,\s]+. Order is kept; nothing is de-duplicated (Python ordered it).
    $list = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($WordFile)) {
        foreach ($raw in @(Get-Content -LiteralPath $WordFile -Encoding UTF8)) {
            # ToString() drops the provider properties Get-Content attaches,
            # which ConvertTo-Json would otherwise serialise.
            $list.Add($raw.ToString())
        }
    } else {
        foreach ($word in (($Words -join ',') -split '[,\s]+')) {
            if ($word.Length -gt 0) { $list.Add($word) }
        }
    }
    return , $list
}

function Invoke-HcRun {
    # Run hc over -Config with the given script lines. hc's UTF-16LE stdout
    # (F-1) is decoded line by line into an AutoFlush UTF-8 hc-stdout.txt, so
    # every pre-kill line survives (FR-020). Fills $script:Run.hc. Exit codes
    # 5 (start failure) and 6 (timeout); otherwise returns.
    # $HeaderPattern matches a word's header line (`Parsing "` / `Testing "`),
    # counted to name the word in flight at a kill.
    param(
        [string[]]$ScriptLines,
        [System.Collections.ArrayList]$SentItems,
        [string]$HeaderPattern
    )
    $script:Run.hc = [ordered]@{
        exit_code       = $null
        timed_out       = $false
        killed          = $false
        in_flight_index = $null
        stdout_bom      = $false
    }
    $runFull = [System.IO.Path]::GetFullPath($RunDir)
    $scriptPath = Join-Path $runFull 'hc-script.txt'
    Write-Utf8Lines -Path $scriptPath -Lines $ScriptLines
    $configFull = [System.IO.Path]::GetFullPath($Config)

    $utf8 = Get-Utf8NoBom
    $outWriter = New-Object System.IO.StreamWriter((Join-Path $runFull 'hc-stdout.txt'), $false, $utf8)
    $outWriter.AutoFlush = $true
    $errWriter = New-Object System.IO.StreamWriter((Join-Path $runFull 'hc-stderr.txt'), $false, $utf8)
    $errWriter.AutoFlush = $true
    try {
        $proc = New-ToolProcess -ToolPath $HcPath -Arguments @('-i', $configFull, '-s', $scriptPath)
        $proc.StartInfo.StandardOutputEncoding = [System.Text.Encoding]::Unicode
        $proc.StartInfo.StandardErrorEncoding = $utf8
        try {
            [void]$proc.Start()
        } catch {
            $errWriter.WriteLine('hc did not start: ' + $_.Exception.Message)
            Stop-Hcparse -Code 5 -Message ('hc did not start: ' + $_.Exception.Message)
        }
        $proc.StandardInput.Close()
        # Our own reader over the raw stream, with BOM detection off, so a
        # UTF-16 BOM is seen (and recorded) rather than silently eaten.
        $outReader = New-Object System.IO.StreamReader($proc.StandardOutput.BaseStream,
            (New-Object System.Text.UnicodeEncoding($false, $false)), $false)
        $errReader = $proc.StandardError

        $clock = [System.Diagnostics.Stopwatch]::StartNew()
        $limitMs = [int64]$script:HcTimeout * 1000
        $timedOut = $false
        $firstLine = $true
        $headers = 0
        $inFlight = $false
        $drainUntil = -1
        $outTask = $outReader.ReadLineAsync()
        $errTask = $errReader.ReadLineAsync()
        while ($null -ne $outTask -or $null -ne $errTask) {
            $pending = New-Object System.Collections.Generic.List[System.Threading.Tasks.Task]
            if ($null -ne $outTask) { $pending.Add($outTask) }
            if ($null -ne $errTask) { $pending.Add($errTask) }
            [void][System.Threading.Tasks.Task]::WaitAny($pending.ToArray(), 100)
            if ($null -ne $outTask -and $outTask.IsCompleted) {
                $line = $outTask.Result
                if ($null -eq $line) {
                    $outTask = $null
                } else {
                    if ($firstLine) {
                        $firstLine = $false
                        if ($line.Length -gt 0 -and $line[0] -eq [char]0xFEFF) {
                            $script:Run.hc.stdout_bom = $true
                            $line = $line.Substring(1)
                        }
                    }
                    $outWriter.WriteLine($line)
                    if ($line -match $HeaderPattern) {
                        $headers++
                        $inFlight = $true
                    } elseif ($line.Length -eq 0) {
                        $inFlight = $false
                    }
                    $outTask = $outReader.ReadLineAsync()
                }
            }
            if ($null -ne $errTask -and $errTask.IsCompleted) {
                $line = $errTask.Result
                if ($null -eq $line) {
                    $errTask = $null
                } else {
                    $errWriter.WriteLine($line)
                    $errTask = $errReader.ReadLineAsync()
                }
            }
            if ((-not $timedOut) -and $clock.ElapsedMilliseconds -gt $limitMs -and (-not $proc.HasExited)) {
                $timedOut = $true
                Write-HcLog ('hc timed out after ' + $script:HcTimeout + ' s; killing its process tree')
                Stop-ProcessTree -Process $proc
                $drainUntil = $clock.ElapsedMilliseconds + 10000
            }
            if ($drainUntil -ge 0 -and $clock.ElapsedMilliseconds -gt $drainUntil) {
                break
            }
        }

        if ($timedOut) {
            $script:Run.hc.timed_out = $true
            $script:Run.hc.killed = $true
            if ($inFlight -and $headers -ge 1 -and $headers -le $SentItems.Count) {
                $script:Run.hc.in_flight_index = $SentItems[$headers - 1].index
            }
            Stop-Hcparse -Code 6 -Message ('hc was killed after ' + $script:HcTimeout + ' s.')
        }
        $proc.WaitForExit()
        $script:Run.hc.exit_code = $proc.ExitCode
        if ($proc.ExitCode -eq -1) {
            Stop-Hcparse -Code 5 -Message 'hc failed to start (exit -1); its message is in hc-stdout.txt.'
        }
    } finally {
        $outWriter.Dispose()
        $errWriter.Dispose()
    }
}

function Invoke-ParseMode {
    # Read the words, build the dispatch items (dispatch.json is written
    # before hc starts), write hc-script.txt ending in `stats -p`, run hc.
    # Exit codes 0, 5, 6.
    $wordList = Read-ParseWords
    $items = New-Object System.Collections.ArrayList
    for ($i = 0; $i -lt $wordList.Count; $i++) {
        [void]$items.Add((Get-DispatchItem -Index $i -Word $wordList[$i]))
    }
    Invoke-DispatchAndRun -Mode 'parse' -Items $items -StatsLine 'stats -p' -HeaderPattern '^Parsing "'
}

function Invoke-DispatchAndRun {
    # Shared by Parse and Test: record the items, write dispatch.json before
    # hc starts, then run hc over the sent lines plus the stats line.
    param(
        [string]$Mode,
        [System.Collections.ArrayList]$Items,
        [string]$StatsLine,
        [string]$HeaderPattern
    )
    $sent = New-Object System.Collections.ArrayList
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($item in $Items) {
        if ($item.sent) {
            [void]$sent.Add($item)
            $lines.Add($item.line)
        }
    }
    $lines.Add($StatsLine)
    $script:Run.items = $Items
    $dispatch = [ordered]@{
        schema = 'flextoolsmcp.hc-dispatch/1'
        mode   = $Mode
        items  = $Items
    }
    Write-Utf8Text -Path (Join-Path $RunDir 'dispatch.json') -Text (ConvertTo-Json -InputObject $dispatch -Depth 10)
    Write-HcLog ('' + $Items.Count + ' items, ' + $sent.Count + ' sent; running hc')

    Invoke-HcRun -ScriptLines $lines.ToArray() -SentItems $sent -HeaderPattern $HeaderPattern
    Write-HcLog 'hc completed'
}

function Invoke-TestMode {
    # The corpus was read and checked in Assert-Parameters. Apply FR-027,
    # write dispatch.json before hc starts, write hc-script.txt ending in
    # `stats -t`, run hc as in Parse mode. Exit codes 0, 5, 6.
    Invoke-DispatchAndRun -Mode 'test' -Items (Get-TestItems) -StatsLine 'stats -t' -HeaderPattern '^Testing "'
}

function Get-TestItems {
    $items = New-Object System.Collections.ArrayList
    for ($i = 0; $i -lt $script:Corpus.Count; $i++) {
        [void]$items.Add((Get-TestItem -Index $i -Assertion $script:Corpus[$i]))
    }
    return , $items
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Validation writes nothing, so exit 2 and 3 leave no run.json behind.
try {
    Assert-Parameters
} catch {
    if (-not $script:Stopped) { $script:ExitCode = 2 }
    Write-HcError $_.Exception.Message
    exit $script:ExitCode
}

$script:StartedAt = [DateTime]::UtcNow
Write-HcLog ("version $script:HCPARSE_VERSION, mode $Mode")

try {
    switch ($Mode) {
        'Generate' { Invoke-GenerateMode }
        'Parse'    { Invoke-ParseMode }
        'Test'     { Invoke-TestMode }
    }
} catch {
    if (-not $script:Stopped) { $script:ExitCode = 1 }
    $script:Run.error = $_.Exception.Message
    Write-HcError $_.Exception.Message
} finally {
    try {
        Write-RunJson
    } catch {
        Write-HcError ('could not write run.json: ' + $_.Exception.Message)
        if ($script:ExitCode -eq 0) { $script:ExitCode = 1 }
    }
}

exit $script:ExitCode
