param(
    [string]$Model = 'qwen2.5:3b',
    [string]$Version = '0.40.4'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localRoot = Join-Path $projectRoot '.local'
$runtimeRoot = Join-Path $localRoot "ollama-$Version"
$modelRoot = Join-Path $localRoot 'models'
$logRoot = Join-Path $localRoot 'logs'
$archivePath = Join-Path $localRoot "ollama-$Version.zip"
$ollamaExecutable = Join-Path $runtimeRoot 'ollama.exe'
New-Item -ItemType Directory -Path $localRoot, $runtimeRoot, $modelRoot, $logRoot -Force | Out-Null

if (-not (Test-Path -LiteralPath $ollamaExecutable)) {
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/ollama/ollama/releases/tags/v$Version"
    $asset = $release.assets | Where-Object { $_.name -eq 'ollama-windows-amd64.zip' }
    if (-not $asset -or -not $asset.digest.StartsWith('sha256:')) {
        throw 'The official release must provide a SHA-256 digest.'
    }
    if (-not (Test-Path -LiteralPath $archivePath)) {
        Write-Output "Downloading official Ollama v$Version portable runtime to .local (about 1.4 GB)."
        & curl.exe --fail --location --silent --show-error --output $archivePath $asset.browser_download_url
        if ($LASTEXITCODE -ne 0) { throw 'Ollama runtime download failed.' }
    }
    $expectedHash = $asset.digest.Substring(7)
    if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -ne $expectedHash) {
        throw "SHA-256 mismatch. Remove the incomplete archive at $archivePath before retrying."
    }
    Write-Output 'Extracting verified Ollama runtime.'
    Expand-Archive -LiteralPath $archivePath -DestinationPath $runtimeRoot -Force
}

$previousHost = $env:OLLAMA_HOST
$previousModels = $env:OLLAMA_MODELS
$previousCloud = $env:OLLAMA_NO_CLOUD
try {
    $env:OLLAMA_HOST = '127.0.0.1:11434'
    $env:OLLAMA_MODELS = $modelRoot
    $env:OLLAMA_NO_CLOUD = '1'
    $running = $false
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
        $running = $true
    } catch { }
    if ($running) {
        # Avoid pulling into another Ollama instance's model directory.
        $ownedPidPath = Join-Path $localRoot 'ollama.pid'
        $ownedProcess = if (Test-Path -LiteralPath $ownedPidPath) {
            Get-Process -Id ([int](Get-Content -LiteralPath $ownedPidPath)) -ErrorAction SilentlyContinue
        }
        if (-not $ownedProcess -or $ownedProcess.Path -ne $ollamaExecutable) {
            throw 'Port 11434 is already in use by another Ollama server. Quit it before starting the project runtime.'
        }
    } else {
        Write-Output 'Starting project-local Ollama server on 127.0.0.1:11434.'
        $serverProcess = Start-Process -FilePath $ollamaExecutable -ArgumentList 'serve' -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $logRoot 'ollama-out.log') `
            -RedirectStandardError (Join-Path $logRoot 'ollama-error.log')
        $serverProcess.Id | Set-Content -LiteralPath (Join-Path $localRoot 'ollama.pid')
        $ready = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            try {
                $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
                $ready = $true
                break
            } catch { Start-Sleep -Milliseconds 500 }
        }
        if (-not $ready) { throw "Ollama did not start. Check $logRoot." }
    }
    Write-Output "Pulling local model $Model into .local/models (qwen2.5:3b is about 1.9 GB)."
    $pullProcess = Start-Process -FilePath $ollamaExecutable -ArgumentList @('pull', $Model) `
        -WindowStyle Hidden -PassThru -Wait `
        -RedirectStandardOutput (Join-Path $logRoot 'model-pull-out.log') `
        -RedirectStandardError (Join-Path $logRoot 'model-pull-error.log')
    if ($pullProcess.ExitCode -ne 0) { throw "Model pull failed. Check $logRoot and run this script again to resume." }
    Write-Output 'Ollama is ready. The Python wrapper sets num_gpu=0 for every generation request.'
} finally {
    $env:OLLAMA_HOST = $previousHost
    $env:OLLAMA_MODELS = $previousModels
    $env:OLLAMA_NO_CLOUD = $previousCloud
}
