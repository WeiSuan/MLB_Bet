$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = 'C:/Users/Weihsuan/AppData/Local/Programs/Python/Python313/python.exe'
$scraperScript = Join-Path $projectRoot 'mlb_playwright_scraper.py'
$logDir = Join-Path $projectRoot 'logs'

if (-not (Test-Path $logDir)) {
    New-Item -Path $logDir -ItemType Directory | Out-Null
}

if (-not (Test-Path $scraperScript)) {
    throw "Scraper script not found: $scraperScript"
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$logFile = Join-Path $logDir "mlb_scraper_$timestamp.log"

Push-Location $projectRoot
try {
    & $pythonExe $scraperScript *>&1 | Tee-Object -FilePath $logFile
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
