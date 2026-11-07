$ErrorActionPreference = "Stop"
$env:PYTHONUNBUFFERED = "1"

Write-Host "=== NEXA S4 TEST 20 ==="
python s4_prepare_workload.py --units 20 --output data\S4_WORKLOAD_20.jsonl
python s4_load_runner.py `
  --run-id s4-test20 `
  --workload data\S4_WORKLOAD_20.jsonl `
  --db data\s4_test20.db `
  --workers 2 `
  --duration-hours 0 `
  --target-completed 20 `
  --rate-per-hour 240

python s4_report.py --run-id s4-test20 --db data\s4_test20.db
