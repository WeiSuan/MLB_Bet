param(
    [switch]$InstallSchedule,
    [switch]$RunNow,
    [string]$ScheduleTime = '05:00',
    [string]$TaskName = 'PlaywrightMCP_DailyScraper',
    [string]$PythonExe = ''
)

$ErrorActionPreference = 'Stop'

$scriptPath = if ($PSCommandPath) { $PSCommandPath } else { $MyInvocation.MyCommand.Path }
$scriptDir = Split-Path -Parent $scriptPath
$projectRoot = Split-Path -Parent $scriptDir
$logDir = Join-Path $projectRoot 'runtime/logs'

if (-not (Test-Path $logDir)) {
    New-Item -Path $logDir -ItemType Directory | Out-Null
}

$pythonCandidates = @(
    $PythonExe,
    (Join-Path $projectRoot '.venv/Scripts/python.exe'),
    'C:/Users/Weihsuan/AppData/Local/Programs/Python/Python313/python.exe'
) | Where-Object { $_ -and $_.Trim() -ne '' }

$pythonExeResolved = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        $pythonExeResolved = (Resolve-Path $candidate).Path
        break
    }
}

if (-not $pythonExeResolved) {
    throw "Python executable not found. Checked: $($pythonCandidates -join ', ')"
}

$steps = @(
    @{
        Name = 'MLB Roster Scraper'
        Path = Join-Path $projectRoot 'src/scrapers/mlb_playwright_scraper.py'
    },
    @{
        Name = 'Sports Lottery Bet Scraper'
        Path = Join-Path $projectRoot 'src/scrapers/sportslottery_baseball_bet_scraper.py'
    },
    @{
        Name = 'Roster Player Data Enricher'
        Path = Join-Path $projectRoot 'src/enrichers/roster_player_data_enricher.py'
    }
)

foreach ($step in $steps) {
    if (-not (Test-Path $step.Path)) {
        throw "Script not found: $($step.Path)"
    }
}

if ($InstallSchedule) {
    $powershellExe = (Get-Command 'powershell.exe').Source
    $resolvedScriptPath = (Resolve-Path $scriptPath).Path
    $taskArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$resolvedScriptPath`""

    $trigger = New-ScheduledTaskTrigger -Daily -At $ScheduleTime
    $action = New-ScheduledTaskAction -Execute $powershellExe -Argument $taskArgs
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description 'Run PlaywrightMCP daily scraper pipeline (roster -> bet -> enrich -> git sync)' `
        -Force | Out-Null

    Write-Host "Scheduled task installed/updated: $TaskName at $ScheduleTime daily."

    if (-not $RunNow) {
        exit 0
    }
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$logFile = Join-Path $logDir "daily_scraper_pipeline_$timestamp.log"

Push-Location $projectRoot
try {
    foreach ($step in $steps) {
        Write-Host "Running: $($step.Name)"
        & $pythonExeResolved $step.Path *>&1 | Tee-Object -FilePath $logFile -Append
        $stepExitCode = $LASTEXITCODE

        if ($stepExitCode -ne 0) {
            Write-Host "Step failed: $($step.Name) (exit code: $stepExitCode). Skip git sync."
            exit $stepExitCode
        }
    }

    git add -A
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'No file changes detected. Skip commit/push.'
        exit 0
    }

    $commitDate = Get-Date -Format 'yyyy-MM-dd'
    $commitMessage = "daily scraper update: $commitDate"
    git commit -m $commitMessage | Tee-Object -FilePath $logFile -Append

    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Commit failed.'
        exit $LASTEXITCODE
    }

    git push origin main | Tee-Object -FilePath $logFile -Append
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
