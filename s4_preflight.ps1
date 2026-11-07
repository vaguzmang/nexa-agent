$ErrorActionPreference = "Continue"
Write-Host "=== NEXA S4 PREFLIGHT ==="

if (-not $env:VIRTUAL_ENV) { Write-Warning "No se detecta .venv activo." } else { Write-Host "OK venv: $env:VIRTUAL_ENV" }
if (-not (Test-Path ".env")) { Write-Warning "No existe .env local." } else { Write-Host "OK .env presente" }
if (-not (Test-Path "data\S3_REAL_DOMAIN_ICFES_V2.jsonl")) { Write-Warning "Falta dataset ICFES local; ejecutar s3_icfes_prepare.py" } else { Write-Host "OK dataset ICFES" }
if (-not (Test-Path "data\S4_WORKLOAD.jsonl")) { Write-Warning "Falta workload S4; ejecutar s4_prepare_workload.py --units 1300" } else {
  $count = (Get-Content "data\S4_WORKLOAD.jsonl" | Measure-Object -Line).Lines
  if ($count -lt 1200) { Write-Warning "Workload tiene solo $count unidades" } else { Write-Host "OK workload unidades=$count" }
}

$drive = Get-PSDrive -Name C
Write-Host ("Disco libre C: {0:N1} GB" -f ($drive.Free/1GB))

try {
  $ping = Test-Connection -ComputerName "reto.pltk.mx" -Count 1 -Quiet
  Write-Host "Conectividad reto.pltk.mx: $ping"
} catch { Write-Warning "No fue posible comprobar red: $_" }

Write-Host "\nConfiguración de energía activa:"
powercfg /getactivescheme
Write-Host "IMPORTANTE: confirmar suspensión automática desactivada y equipo conectado a corriente."
Write-Host "\nAntes de la corrida oficial: tomar captura y snapshot BEFORE del panel del gateway."
