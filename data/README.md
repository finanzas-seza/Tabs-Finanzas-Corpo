# Tablero de Cobranza · cómo se actualiza

Los datos del tablero viven fuera del HTML y los genera un concentrador.

```
Tablero_Cobranza_Calendario_VF.html   ← el tablero (solo código y diseño, ya no trae datos)
data/
  fuentes/
    AAAAMMDD_cobranza_SEZA.csv        ← un CSV por empresa (lo entrega la skill de ingesta). NO se sube a Git
    AAAAMMDD_cobranza_SHIP.csv
    AAAAMMDD_cobranza_GSG.csv
  config.json                         ← parámetros: meses, cortes, plazos, calendario Walmart, avisos, acciones
  cobranza.js                         ← GENERADO: lo único que lee el tablero (no editar a mano)
scripts/concentrar.py                 ← el concentrador
.vscode/tasks.json                    ← botón para correr el concentrador en VS Code
```

## Actualizar (cada corte)

0. **Pagos de Walmart (Retail).** Tesorería deja los Retail en
   `J:\Mi unidad\SEZA\00_Gestión de proyectos\03_Tesoreria\Comprobaciones\<EMPRESA>\Retail` (SEZA: `RETAIL WALMART`).
   Correr `python scripts/actualizar_retail.py` (o `--check` para ver antes qué cambiaría). Toma el CSV más reciente de
   cada empresa, marca Pagada lo que ya aparece en el Retail (folio + monto) y escribe un CSV nuevo con fecha de hoy.
   Después actualizar `cortes` en `config.json` con la fecha que indica el script. Requiere `pip install pandas lxml openpyxl`.
1. Si hubo ingesta completa (facturas nuevas, bancos, Cob), copiar el CSV nuevo de la empresa a `data/fuentes/`. El concentrador toma el de fecha más reciente
   de cada empresa. **Esta carpeta está en `.gitignore`**: el sitio es público en GitHub Pages y el detalle
   de cartera no debe quedar en el repositorio. Respaldar los CSV en la carpeta *Cartera cobranza* de cada empresa.
2. Si cambió el corte, ajustar en `data/config.json`: `cortes`, `titulo_actualizacion` y, si entra un mes
   nuevo, `meses` (y los periodos nuevos en `calendario_walmart`).
3. En VS Code: `Ctrl+Shift+B` (o *Terminal → Ejecutar tarea → Cobranza: concentrar*).
   Equivale a `python scripts/concentrar.py`.
4. Leer el resumen de la terminal. Si hay `ERROR`, no se escribe nada; corregir el CSV y repetir.
   Los `AVISO` no bloquean, pero hay que revisarlos.
5. Abrir el HTML (doble clic funciona, no requiere servidor) y revisar.
6. Commit (solo cambian `data/cobranza.js` y, si aplica, `data/config.json`) con mensaje tipo
   `Cobranza corte 2026-10-13: SEZA y GSG`, y push.

## Contrato del CSV (una fila por factura, UTF-8)

Obligatorias: `empresa, folio, fecha_emision, cliente, subtotal, estatus`.

| Columna | Valores |
|---|---|
| `fecha_emision`, `fecha_pago`, `fecha_pago_tentativa` | `AAAA-MM-DD` (también acepta `DD/MM/AAAA`) |
| `estatus` | `Pagada`, `Pendiente de pago`, `Por revisar`, `Cancelada con sustitución`, `Cancelada sin sustitución` (también acepta `Pagado`, `Vigente`, `Cancelado` de la cartera) |
| `subtotal` | número, sin IVA (el tablero trabaja en subtotal) |
| `es_por_cobrar` | `Sí` / `No` (notas de crédito, complementos y cartas porte = `No`). Vacío = `Sí` |
| `validacion` | motivo de *Por revisar* o nota de estatus; debe coincidir con alguna regla de `acciones` en config.json |
| `periodo_walmart`, `calendario_fuente` | periodo del calendario Walmart (`2026-08-P1`) y `O`/`R`/`P` |
| `segmento` | opcional; si viene vacío se calcula con `segmentos` de config.json |

Las demás columnas de la skill (`uuid, iva, total, fuente_pago, referencia_pago, confianza, tienda, formato,
determinante, folio_sustitucion, observaciones, fecha_corte`, …) se aceptan y quedan para trazabilidad.

El mes es el de la fecha de emisión. Va a *Fuera de periodo* si el mes no está en `meses` o si `validacion` = *Fecha de factura fuera del periodo*. Una fecha con año distinto al de `anio` genera aviso para revisar la captura.

## Reglas

- Nunca editar `data/cobranza.js` a mano: se regenera.
- Los cambios de datos se hacen en el CSV o en `config.json`; los de diseño, en el HTML.
- `data/cobranza.js` sí se publica: contiene el mismo detalle que antes iba incrustado en el HTML. El sitio es público (el `noindex` solo evita buscadores).
- Requiere Python 3.9+ en la computadora (solo biblioteca estándar).
