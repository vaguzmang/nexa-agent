param(
  [string]$RunId = ("s4-" + (Get-Date -Format "yyyyMMdd-HHmm")),
  [double]$DurationHours = 12.25,
  [int]$TargetCompleted = 1100,
  [int]$Workers = 3,
  [double]$RatePerHour = 105
)
$ErrorActionPreference = "Stop"
$env:PYTHONUNBUFFERED = "1"
Write-Host "NEXA S4 official unattended run"
Write-Host "RunId=$RunId"
python s4_load_runner.py --run-id $RunId --duration-hours $DurationHours --target-completed $TargetCompleted --workers $Workers --rate-per-hour $RatePerHour
exit $LASTEXITCODE
