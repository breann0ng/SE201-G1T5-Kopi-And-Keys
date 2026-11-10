param(
    [Parameter(Mandatory=$true)][string]$Step,
    [Parameter(Mandatory=$true)][string[]]$PythonArgs,
    [ValidateSet('cpu','gpu')][string]$Mode = 'gpu'
)
. (Join-Path $PSScriptRoot 'final-env.ps1')
$env:KOPI_OLLAMA_DEVICE = $Mode
$attempt = 1
while (Test-Path -LiteralPath (Join-Path $FinalRunReports "$Step-attempt-$attempt.meta.json")) { $attempt++ }
$logPath = Join-Path $FinalRunReports "$Step-attempt-$attempt.txt"
$metaPath = Join-Path $FinalRunReports "$Step-attempt-$attempt.meta.json"
$began = Get-Date
$before = @(Get-ChildItem -LiteralPath (Join-Path $FinalRunRoot 'data\evaluation-data\results') -File | Select-Object -ExpandProperty Name)
$meta = [ordered]@{step=$Step;attempt=$attempt;status='running';started_utc=$began.ToUniversalTime().ToString('o');python_args=$PythonArgs;device=$Mode;log=$logPath}
$meta | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $metaPath -Encoding UTF8
& $FinalRunPython @PythonArgs 2>&1 | Tee-Object -FilePath $logPath
$stepExit = $LASTEXITCODE
$ended = Get-Date
$after = @(Get-ChildItem -LiteralPath (Join-Path $FinalRunRoot 'data\evaluation-data\results') -File | Select-Object -ExpandProperty Name)
$meta.status = 'finished'
$meta['exit_code'] = $stepExit
$meta['finished_utc'] = $ended.ToUniversalTime().ToString('o')
$meta['elapsed_seconds'] = [Math]::Round(($ended-$began).TotalSeconds, 3)
$meta['new_result_files'] = @($after | Where-Object {$_ -notin $before})
$meta | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $metaPath -Encoding UTF8
exit $stepExit
