param([string]$OutputRoot = 'C:/dev/BlenderBridge/artifacts/native-modeling')
$ErrorActionPreference = 'Stop'
$bridgeRepo = Split-Path -Parent $PSScriptRoot
$bridgePython = Join-Path $bridgeRepo '.venv/Scripts/python.exe'
$bridgeOutput = [System.IO.Path]::GetFullPath($OutputRoot)
$bridgeLogs = Join-Path $bridgeOutput '.bridge/host'
New-Item -ItemType Directory -Path $bridgeLogs -Force | Out-Null
$bridgeStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$bridgeArguments = '-m blender_bridge.host.broker --root "' + $bridgeOutput + '"'
$bridgeProcess = Start-Process -FilePath $bridgePython -ArgumentList $bridgeArguments -WorkingDirectory $bridgeRepo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $bridgeLogs ($bridgeStamp + '-broker-stdout.log')) -RedirectStandardError (Join-Path $bridgeLogs ($bridgeStamp + '-broker-stderr.log'))
[pscustomobject]@{pid=$bridgeProcess.Id;started=$bridgeProcess.StartTime;output_root=$bridgeOutput;role='blender_bridge_host_broker'} | ConvertTo-Json
