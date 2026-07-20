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
    $scraperExitCode = $LASTEXITCODE

    if ($scraperExitCode -ne 0) {
        Write-Host "Scraper failed with exit code $scraperExitCode. Skip git sync."
        exit $scraperExitCode
    }

    git add -A

    $hasChanges = git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "No file changes detected. Skip commit/push."
        exit 0
    }

    $commitDate = Get-Date -Format 'yyyy-MM-dd'
    $commitMessage = "daily scraper update: $commitDate"
    git commit -m $commitMessage | Tee-Object -FilePath $logFile -Append

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Commit failed."
        exit $LASTEXITCODE
    }

    git push origin main | Tee-Object -FilePath $logFile -Append
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
