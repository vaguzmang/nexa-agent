param(
  [string]$RunId = ("s4-official-" + (Get-Date -Format "yyyyMMdd-HHmm"))
)

$ErrorActionPreference = "Stop"
$env:PYTHONUNBUFFERED = "1"

Write-Host "=== NEXA S4 CORRIDA OFICIAL ==="
Write-Host "RunId=$RunId"
Write-Host "REQUISITOS: corriente, suspensión desactivada, Internet estable, no cerrar PowerShell ni reiniciar manualmente."

python s4_prepare_workload.py --units 1300 --output data\S4_WORKLOAD.jsonl

.\s4_supervisor_12h.ps1 `
  -RunId $RunId `
  -DurationHours 12.25 `
  -TargetCompleted 1100 `
  -Workers 3 `
  -RatePerHour 105 `
  -MaxProcessRestarts 4
