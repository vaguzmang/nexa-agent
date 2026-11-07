$ErrorActionPreference = "Stop"
$env:PYTHONUNBUFFERED = "1"

Write-Host "=== NEXA S4 TEST 100 ==="
python s4_prepare_workload.py --units 100 --output data\S4_WORKLOAD_100.jsonl
python s4_load_runner.py `
  --run-id s4-test100 `
  --workload data\S4_WORKLOAD_100.jsonl `
  --db data\s4_test100.db `
  --workers 3 `
  --duration-hours 0 `
  --target-completed 100 `
  --rate-per-hour 300

python s4_report.py --run-id s4-test100 --db data\s4_test100.db
