$ErrorActionPreference = "Stop"
$env:PYTHONUNBUFFERED = "1"

Write-Host "=== NEXA S4 TEST 1 HORA DESATENDIDA ==="
Write-Host "Desde este comando el equipo debe permanecer encendido, conectado a corriente y sin suspensión durante al menos 1 hora."

python s4_prepare_workload.py --units 180 --output data\S4_WORKLOAD_1H.jsonl
python s4_load_runner.py `
  --run-id s4-test1h `
  --workload data\S4_WORKLOAD_1H.jsonl `
  --db data\s4_test1h.db `
  --workers 3 `
  --duration-hours 1.05 `
  --target-completed 90 `
  --rate-per-hour 100 `
  --heartbeat-seconds 60

python s4_report.py --run-id s4-test1h --db data\s4_test1h.db
