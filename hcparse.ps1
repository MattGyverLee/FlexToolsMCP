<#
.SYNOPSIS
  Parse words with HermitCrab from the command line, straight from a FLEx project.

.EXAMPLE
  .\hcparse.ps1 -Project Indonesian-HermitCrab -Words membaca,menulis,mengambil
  .\hcparse.ps1 -Project Indonesian-HermitCrab -WordFile words.txt -Trace
  .\hcparse.ps1 -Config existing-hc.xml -Words membaca      # skip config regeneration
#>
[CmdletBinding()]
param(
    [string]$Project,                 # FLEx project name, or full path to a .fwdata file
    [string]$Config,                  # Reuse an existing HC config instead of generating one
    [string[]]$Words,
    [string]$WordFile,                # One word per line
    [string]$OutFile,
    [switch]$Trace,
    [switch]$KeepConfig
)

$ErrorActionPreference = 'Stop'
$fw      = 'C:\Program Files\SIL\FieldWorks 9'
$hcTool  = Join-Path $env:LOCALAPPDATA 'HermitCrabTool\hc.dll'

if (-not (Test-Path $hcTool)) { throw "HermitCrab tool not found at $hcTool" }

# --- Resolve the HC configuration -------------------------------------------
if ($Config) {
    if (-not (Test-Path $Config)) { throw "Config not found: $Config" }
    $cfg = (Resolve-Path $Config).Path
} else {
    if (-not $Project) { throw 'Supply either -Project or -Config.' }

    if ($Project -like '*.fwdata') {
        $fwdata = (Resolve-Path $Project).Path
    } else {
        $fwdata = "C:\ProgramData\SIL\FieldWorks\Projects\$Project\$Project.fwdata"
        if (-not (Test-Path $fwdata)) { throw "Project not found: $fwdata" }
    }

    # Work on a copy so a FLEx instance holding the project can't be disturbed.
    $work = Join-Path $env:TEMP ("hcparse_" + [guid]::NewGuid().ToString('N').Substring(0,8))
    New-Item -ItemType Directory -Path $work | Out-Null
    Write-Host "Copying project..." -ForegroundColor DarkGray
    Copy-Item (Split-Path $fwdata) -Destination $work -Recurse
    $copied = Get-ChildItem $work -Recurse -Filter *.fwdata | Select-Object -First 1

    $cfg = Join-Path $work 'hc-config.xml'
    Write-Host "Generating HermitCrab configuration..." -ForegroundColor DarkGray
    Push-Location $fw
    try   { & .\GenerateHCConfig.exe $copied.FullName $cfg | Out-Null }
    finally { Pop-Location }
    if (-not (Test-Path $cfg)) { throw 'GenerateHCConfig produced no output.' }
    if ($KeepConfig) { Write-Host "Config kept at: $cfg" -ForegroundColor DarkGray }
}

# --- Assemble the word list --------------------------------------------------
$list = @()
# When invoked via `powershell -File`, a comma-separated list arrives as one
# string, so split on commas (and whitespace) regardless of how it was passed.
if ($Words)    { $list += $Words | ForEach-Object { $_ -split '[,\s]+' } }
# -Encoding UTF8 is essential: PS 5.1's Get-Content defaults to the ANSI code
# page for a BOM-less file, which turns any non-Latin word list into mojibake
# and makes HermitCrab report "invalid segment at position 1" for every word.
if ($WordFile) { $list += Get-Content $WordFile -Encoding UTF8 | Where-Object { $_.Trim() } }
if (-not $list) { throw 'No words supplied. Use -Words or -WordFile.' }

$script = [System.IO.Path]::GetTempFileName()
$lines  = @()
if ($Trace) { $lines += 'tracing on' }
$lines += $list | ForEach-Object { "parse $($_.Trim())" }
$lines += 'stats -p'
# HC reads the script as UTF-8; write it without a BOM.
[System.IO.File]::WriteAllLines($script, $lines, (New-Object System.Text.UTF8Encoding($false)))

$out = if ($OutFile) { $OutFile } else { [System.IO.Path]::GetTempFileName() }

Push-Location (Split-Path $hcTool)
try   { & dotnet $hcTool -i $cfg -s $script -o $out | Out-Null }
finally { Pop-Location }

Get-Content $out -Encoding UTF8
if (-not $OutFile) { Remove-Item $out -Force }
Remove-Item $script -Force
