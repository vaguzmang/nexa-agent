# S3 REAL DOMAIN ICFES V2

Corrige la observación de S3 usando preguntas oficiales liberadas de Saber 11.

## Fuentes
- Matemáticas Saber 11 2026 — Icfes.
- Ciencias Naturales Saber 11 2025 — Icfes.

El repositorio conserva solo el manifiesto con fuente, número de pregunta y clave oficial. El texto se descarga localmente desde los PDF oficiales.

## Preparación
```powershell
pip install -r requirements-s3-realdata.txt
python s3_icfes_prepare.py
python s3_icfes_run_batch.py --list
```

## Costo real del gateway
Antes del lote:
```powershell
python s3_gateway_cost.py snapshot --label before --requests <PANEL_REQUESTS> --cost <PANEL_USD>
```

Primera prueba:
```powershell
python s3_icfes_run_batch.py --count 3
```

Luego el resto:
```powershell
python s3_icfes_run_batch.py --from-case ICFES-04
```

Después del lote:
```powershell
python s3_gateway_cost.py snapshot --label after --requests <PANEL_REQUESTS> --cost <PANEL_USD>
python s3_gateway_cost.py report
python s3_icfes_report.py
```
