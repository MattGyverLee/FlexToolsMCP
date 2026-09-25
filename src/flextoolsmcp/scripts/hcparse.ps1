<#
.SYNOPSIS
  Export a project's HermitCrab configuration for the FLExTools MCP sandbox spine.

.DESCRIPTION
  Packaged driver for the parser-check CP5 sandbox spine. The interface between
  the MCP and this script is specs/parser-check-cp5/contracts/hcparse.md; keep
  the two in step.

  One mode:
    Generate  Copy the allowlisted project files into -WorkDir, run
              GenerateHCConfig on the copy, write the config to -ConfigOut.

  Parse and Test were retired in the CP5 re-plan (2026-09-24): the sandbox now
  parses in-process, in the parse worker's `--sandbox` mode, calling
  FieldWorks' own bundled HermitCrab engine (contracts/sandbox-worker.md).
  There is no `hc` console tool to drive any more. -Mode Parse and -Mode Test
  are refused with exit 2.

  Targets Windows PowerShell 5.1. Do not use PowerShell 7 syntax here: no
  null-coalescing, no null-conditional member access, no ternary, and no
  pipeline chain operators.

  The script never opens the project through LCM and never writes inside a
  project folder. The GenerateHCConfig path is passed in by the MCP; it is not
  hard-coded here (FR-002).

  Console output is ASCII-only progress prose for a human (FR-021). The MCP
  never parses it (FR-023): the outcome of an invocation is in run.json.

.NOTES
  Invocation (the MCP builds this as an argv list, never a command string,
  with stdin closed):

    powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <hcparse.ps1> <params>

  Exit codes (the script's own, not the generator's):

    0  The invocation completed. The outcome is in run.json.
    1  Unexpected script error (not part of the contract; run.json is still
       written when the invocation got past parameter validation).
    2  A bad parameter, a missing input file, or a retired mode. No run.json
       is written.
    3  -ConfigOut was refused (under a sandboxes directory). Nothing is written.
    4  Generation failed (details in run.json).
    6  Timeout (the generator was killed).

  (Exit 5, "hc failed to start", was Parse/Test's and is retired with them.)
#>
[CmdletBinding()]
param(
    # Generate (the only mode). Validated in Assert-Parameters rather than
    # with [ValidateSet()]: a binding failure under `-File` exits 1, and the
    # contract wants 2 for a bad parameter. The same goes for the [string]
    # timeout below.
    [string]$Mode,

    # The GenerateHCConfig executable.
    [string]$GenerateHCConfigPath,

    # Absolute path to the live .fwdata. It is only read.
    [string]$FwData,

    # Created by the MCP, holds the marker. Emptied in finally.
    [string]$WorkDir,

    # The output config path. Refused (exit 3) under `sandboxes`.
    [string]$ConfigOut,

    # Destination for this invocation's files.
    [string]$RunDir,

    # Wall clock for the generator (covers the SLDR start-up).
    [string]$GenerateTimeoutSeconds = '600'
)

$script:HCPARSE_VERSION = '6.0.0'

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

# run.json sections. Invoke-GenerateMode fills these; Write-RunJson serialises them.
$script:Run = [ordered]@{
    generate = $null
    copy     = $null
    error    = $null
}
$script:StartedAt = $null
# The validated timeout as an int, set by Assert-Parameters.
$script:GenerateTimeout = 0

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
        Stop-Hcparse -Code 2 -Message '-Mode is required: Generate.'
    }
    if ($Mode -ieq 'Parse' -or $Mode -ieq 'Test') {
        Stop-Hcparse -Code 2 -Message ("-Mode $Mode is retired: the sandbox parses in the parse worker now. Use -Mode Generate.")
    }
    if (-not ($Mode -ieq 'Generate')) {
        Stop-Hcparse -Code 2 -Message ("-Mode must be Generate, not: $Mode")
    }
    $script:Mode = 'Generate'

    Assert-Required -Name 'RunDir' -Value $RunDir
    Assert-DirectoryExists -Name 'RunDir' -Path $RunDir
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

# ---------------------------------------------------------------------------
# run.json (contracts/hcparse.md section 5)
# ---------------------------------------------------------------------------

function Get-RunInputs {
    $inputs = [ordered]@{}
    $inputs.fwdata = $FwData
    $inputs.config_out = $ConfigOut
    $inputs.timeout_seconds = $script:GenerateTimeout
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
    $doc.generate = $script:Run.generate
    $doc.copy = $script:Run.copy
    if ($null -ne $script:Run.error) {
        $doc.error = $script:Run.error
    }
    $json = $doc | ConvertTo-Json -Depth 10
    Write-Utf8Text -Path (Join-Path $RunDir 'run.json') -Text $json
}

# ---------------------------------------------------------------------------
# Process helpers
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
    # A System.Diagnostics.Process for a tool path passed in by the MCP.
    # stdin is redirected so it can be closed at once: a tool never waits on
    # the console.
    param([string]$ToolPath, [string[]]$Arguments, [string]$WorkingDirectory)
    $argv = @($Arguments)
    $file = [System.IO.Path]::GetFullPath($ToolPath)
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
# Generate mode
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
    Invoke-GenerateMode
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
