param(
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [string[]]$ReadRoot = @(),
    [string]$BlendFile,
    [string]$Blender = 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe',
    [switch]$Visible,
    [switch]$AllowPython
)
$ErrorActionPreference = 'Stop'
$bridgeRepo = Split-Path -Parent $PSScriptRoot
$bridgeLaunch = Join-Path $PSScriptRoot 'launch_runtime.py'
$bridgeOutput = [System.IO.Path]::GetFullPath($OutputRoot)
if (-not (Test-Path -LiteralPath $Blender -PathType Leaf)) { throw 'Blender executable not found; supply -Blender.' }
if ($BlendFile -and -not (Test-Path -LiteralPath $BlendFile -PathType Leaf)) { throw 'BlendFile not found.' }
New-Item -ItemType Directory -Path $bridgeOutput -Force | Out-Null
$bridgeLog = Join-Path $bridgeOutput '.bridge'
New-Item -ItemType Directory -Path $bridgeLog -Force | Out-Null
$bridgeArgs = @()
if (-not $Visible) { $bridgeArgs += '--background' }
if ($BlendFile) { $bridgeArgs += [System.IO.Path]::GetFullPath($BlendFile) } else { $bridgeArgs += '--factory-startup' }
$bridgeArgs += @('--python', $bridgeLaunch, '--', '--output-root', $bridgeOutput)
foreach ($bridgeRead in $ReadRoot) { $bridgeArgs += @('--read-root', [System.IO.Path]::GetFullPath($bridgeRead)) }
if ($AllowPython) { $bridgeArgs += '--allow-python' }
foreach ($bridgeArg in $bridgeArgs) { if ($bridgeArg.Contains('"')) { throw 'Arguments cannot contain a double quote.' } }
$bridgeQuoted = ($bridgeArgs | ForEach-Object { '"' + $_ + '"' }) -join ' '
$bridgeStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$bridgeStyle = if ($Visible) { 'Normal' } else { 'Hidden' }
$bridgeProcess = Start-Process -FilePath $Blender -ArgumentList $bridgeQuoted -WindowStyle $bridgeStyle -PassThru -RedirectStandardOutput (Join-Path $bridgeLog "$bridgeStamp-stdout.log") -RedirectStandardError (Join-Path $bridgeLog "$bridgeStamp-stderr.log")
[pscustomobject]@{ pid=$bridgeProcess.Id; started=$bridgeProcess.StartTime; output_root=$bridgeOutput; background=(-not $Visible) } | ConvertTo-Json

