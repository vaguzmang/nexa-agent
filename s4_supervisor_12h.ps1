param(
  [string]$RunId = ("s4-" + (Get-Date -Format "yyyyMMdd-HHmm")),
  [double]$DurationHours = 12.25,
  [int]$TargetCompleted = 1100,
  [int]$Workers = 3,
  [double]$RatePerHour = 105,
  [int]$MaxProcessRestarts = 4
)
$ErrorActionPreference = "Continue"
$env:PYTHONUNBUFFERED = "1"
$restart = 0
Write-Host "NEXA S4 unattended supervisor"
Write-Host "RunId=$RunId"
while ($true) {
  python s4_load_runner.py --run-id $RunId --duration-hours $DurationHours --target-completed $TargetCompleted --workers $Workers --rate-per-hour $RatePerHour
  $code=$LASTEXITCODE
  if ($code -eq 0) {
    Write-Host "Runner finalizó correctamente."
    exit 0
  }
  $restart++
  if ($restart -gt $MaxProcessRestarts) {
    Write-Host "Se alcanzó MaxProcessRestarts=$MaxProcessRestarts."
    exit $code
  }
  Write-Host "Runner salió con código $code. Reinicio automático $restart/$MaxProcessRestarts en 30s..."
  Start-Sleep -Seconds 30
}
