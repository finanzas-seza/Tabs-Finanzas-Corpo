#!/usr/bin/env python3
"""
Concentrador de cobranza · Grupo SEZA

Lee el CSV más reciente de cada empresa en data/fuentes/ (AAAAMMDD_cobranza_<EMP>.csv),
valida el contrato, junta todo con data/config.json y escribe data/cobranza.js,
que es lo único que lee el tablero.

Uso (desde la raíz del repo):
    python scripts/concentrar.py            # genera data/cobranza.js
    python scripts/concentrar.py --check    # solo valida, no escribe

Solo usa la biblioteca estándar de Python 3.9+.
"""
import csv, json, re, sys, datetime as dt
from collections import defaultdict, Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = RAIZ / "data" / "fuentes"
CONFIG = RAIZ / "data" / "config.json"
SALIDA = RAIZ / "data" / "cobranza.js"

FUERA = "FUERA DE PERIODO"
ESTATUS = ["Pagada", "Pendiente de pago", "Pendiente de validación",
           "Cancelada con sustitución", "Cancelada sin sustitución",
           "Intercompañía", "No es factura por cobrar"]
# Se muestran aparte y no suman en facturado, pagado ni pendiente
FUERA_DE_CARTERA = {"Intercompañía", "No es factura por cobrar"}
# Equivalencias con el estatus de la cartera (skill de ingesta)
EQUIV = {"Pagado": "Pagada", "Vigente": "Pendiente de pago", "Pendiente": "Pendiente de pago",
         "Por revisar": "Pendiente de validación", "En aclaración": "Pendiente de validación"}
MESES_ES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO",
            "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
OBLIGATORIAS = ["empresa", "folio", "fecha_emision", "cliente", "subtotal", "estatus"]

errores, avisos = [], []


def fecha(txt, campo, ctx):
    """Acepta AAAA-MM-DD o DD/MM/AAAA; regresa date o None."""
    txt = (txt or "").strip()
    if not txt:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(txt, fmt).date()
        except ValueError:
            pass
    errores.append(f"{ctx}: {campo} con fecha inválida '{txt}'")
    return None


def numero(txt, ctx):
    txt = (txt or "").replace(",", "").replace("$", "").strip()
    try:
        return float(txt) if txt else 0.0
    except ValueError:
        errores.append(f"{ctx}: subtotal no numérico '{txt}'")
        return 0.0


def ultimo_csv(emp):
    arch = sorted(FUENTES.glob(f"*_cobranza_{emp}.csv"))
    return arch[-1] if arch else None


def leer_empresa(emp, cfg):
    ruta = ultimo_csv(emp)
    if not ruta:
        errores.append(f"{emp}: no hay archivo *_cobranza_{emp}.csv en data/fuentes")
        return [], None
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    faltan = [c for c in OBLIGATORIAS if filas and c not in filas[0]]
    if faltan:
        errores.append(f"{ruta.name}: faltan columnas {faltan}")
        return [], ruta
    seg_cfg = cfg.get("segmentos", {}).get(emp)
    meses, anio = cfg["meses"], cfg["anio"]
    det, vistos = [], Counter()
    for i, r in enumerate(filas, start=2):
        ctx = f"{ruta.name} renglón {i}"
        if r["empresa"].strip() != emp:
            errores.append(f"{ctx}: empresa '{r['empresa']}' no corresponde al archivo")
        folio = r["folio"].strip()
        vistos[folio] += 1
        est = EQUIV.get(r["estatus"].strip(), r["estatus"].strip())
        if est == "Cancelado":
            est = "Cancelada con sustitución" if r.get("folio_sustitucion", "").strip() else "Cancelada sin sustitución"
        if est not in ESTATUS:
            errores.append(f"{ctx}: estatus '{r['estatus']}' no reconocido")
        fe = fecha(r["fecha_emision"], "fecha_emision", ctx)
        fp = fecha(r.get("fecha_pago"), "fecha_pago", ctx)
        ft = fecha(r.get("fecha_pago_tentativa"), "fecha_pago_tentativa", ctx)
        if est == "Pagada" and not fp:
            avisos.append(f"{ctx}: folio {folio} Pagada sin fecha_pago")
        # Mes = mes de la fecha de emisión (misma regla del tablero original).
        # Va a "fuera de periodo" si el mes no está en config.meses o si la ingesta lo
        # marcó con la validación "Fecha de factura fuera del periodo".
        mes = MESES_ES[fe.month - 1] if fe else FUERA
        if mes not in meses or "fuera del periodo" in (r.get("validacion") or "").lower():
            mes = FUERA
        if fe and fe.year != anio and mes != FUERA:
            avisos.append(f"{ctx}: folio {folio} con fecha {fe.isoformat()} (año distinto a {anio}); "
                          f"cuenta en {mes}. Revisar captura")
        cli = r["cliente"].strip()
        if seg_cfg:
            seg = (r.get("segmento") or "").strip() or seg_cfg.get(cli, seg_cfg.get("*", emp))
        else:
            seg = (r.get("segmento") or "").strip() or emp
        es_fac = (r.get("es_por_cobrar") or "Sí").strip() or "Sí"
        es_fac = "Sí" if es_fac.lower() in ("sí", "si", "s", "1", "true") else "No"
        if est.startswith("Cancelada") or est == "No es factura por cobrar":
            es_fac = "No"   # canceladas y documentos que no son factura no suman en facturado
        val = (r.get("validacion") or "").strip()
        if est == "Pendiente de pago" and not val:
            val = "Sin pago en la fuente"
        det.append([emp, seg, mes, est, folio,
                    fe.strftime("%d/%m/%Y") if fe else "",
                    cli, round(numero(r["subtotal"], ctx), 2), val, es_fac,
                    ft.isoformat() if ft else "", fp.isoformat() if fp else "",
                    (r.get("periodo_walmart") or "").strip(),
                    (r.get("calendario_fuente") or "").strip()])
    dup = [f for f, n in vistos.items() if n > 1]
    if dup:
        avisos.append(f"{ruta.name}: {len(dup)} folios repetidos (ej. {dup[:5]})")
    return det, ruta


def agrega(det, llave, filtro=None):
    """[n registros, n facturas por cobrar, subtotal de facturas por cobrar] por llave."""
    m = defaultdict(lambda: [0, 0, 0.0])
    for r in det:
        if filtro and not filtro(r):
            continue
        a = m[llave(r)]
        a[0] += 1
        if r[9] == "Sí":
            a[1] += 1
            a[2] += r[7]
    return [list(k) + [v[0], v[1], round(v[2], 2)] for k, v in sorted(m.items())]


def acciones(det, cfg, empresas):
    out, usadas = [], set()
    for a in cfg.get("acciones", []):
        vals = set(a.get("validacion", []))
        pref = tuple(a.get("validacion_empieza", []))
        ests = set(a.get("estatus", []))
        def ok(r):
            return (r[8] in vals) or (pref and r[8].startswith(pref)) or (r[3] in ests)
        cuenta = [sum(1 for r in det if r[0] == e and ok(r)) for e in empresas]
        usadas |= {r[8] for r in det if ok(r)}
        out.append([a["que"], a["accion"], cuenta])
    sin = Counter(r[8] for r in det if r[3] == "Pendiente de validación" and r[8] not in usadas)
    for v, n in sin.items():
        avisos.append(f"Validación sin acción asignada en config.json: '{v}' ({n} registros)")
    return out


def lote_siguiente(det, cal):
    """Walmart paga por lotes. Si la factura se emitió después de la carga de su periodo
    (martes posterior a la prefactura), no alcanza ese lote: su pago tentativo es el del
    primer lote cuya carga sea igual o posterior a la emisión. Agrega al renglón:
    r[14] = 1 si se recorrió, r[15] = pago tentativo original del periodo."""
    per = {c[0]: c for c in cal}
    cargas = sorted((c[7], c[8]) for c in cal)          # (carga, pago)
    n = 0
    for r in det:
        r += [0, ""]
        if not (r[12] in per and r[10] and r[5]):
            continue
        fe = "-".join(r[5].split("/")[::-1])
        if fe <= per[r[12]][7]:
            continue
        sig = [p for c, p in cargas if c >= fe]
        if sig:
            nuevo = max(r[10], min(sig))
            if nuevo != r[10]:
                r[15], r[10], r[14] = r[10], nuevo, 1
                n += 1
    return n


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    empresas = cfg["empresas"]
    det, archivos = [], {}
    for e in empresas:
        d, ruta = leer_empresa(e, cfg)
        det += d
        if ruta:
            archivos[e] = ruta.name

    cal = cfg["calendario_walmart"]["periodos"]
    ids_cal = {c[0] for c in cal}
    n_lote = lote_siguiente(det, cal)
    sin_cal = Counter(r[12] for r in det if r[12] and r[12] not in ids_cal)
    if sin_cal:
        avisos.append(f"Periodos Walmart que no están en el calendario de config.json: {dict(sin_cal)}")

    D = {
        "meta": {
            "generado": dt.datetime.now().isoformat(timespec="seconds"),
            "archivos": archivos,
            "titulo_actualizacion": cfg.get("titulo_actualizacion", ""),
            "meses": cfg["meses"],
            "empresas": empresas,
            "avisos": cfg.get("avisos", []),
            "notas": cfg.get("notas", {}),
        },
        "rows": agrega(det, lambda r: (r[0], r[1], r[2], r[3])),
        "cli": agrega(det, lambda r: (r[0], r[6], r[2], r[3])),
        "pend": [x[:3] + [x[3], x[5]] for x in
                 agrega(det, lambda r: (r[0], r[6], r[2]), lambda r: r[3] == "Pendiente de pago")],
        # Calendario: solo clientes que pagan por calendario Walmart (plazos[...].cal = 1)
        "calag": agrega(det, lambda r: (r[12] or "Sin asignación", r[0], r[3]),
                        lambda r: cfg["plazos"].get(f"{r[0]}|{r[6]}", {}).get("cal") and r[3] not in FUERA_DE_CARTERA),
        "acc": acciones(det, cfg, empresas),
        "cal": cal,
        "cfg": {k: cfg[k] for k in ("cortes", "diasProximo", "gracia", "congelamientos", "plazos")},
        "det": det,
    }

    # Resumen
    print(f"Facturas leídas: {len(det):,}")
    for e in empresas:
        de = [r for r in det if r[0] == e]
        c = Counter(r[3] for r in de)
        imp = sum(r[7] for r in de if r[9] == "Sí")
        print(f"  {e:5} {archivos.get(e, '—'):32} {len(de):6,} reg.  ${imp:,.2f}  " +
              " · ".join(f"{k}: {c[k]}" for k in ESTATUS if c[k]))
    print(f"Facturas recorridas al lote siguiente (emitidas después de la carga): {n_lote:,}")
    for a in avisos:
        print("AVISO:", a)
    for x in errores[:50]:
        print("ERROR:", x)
    if errores:
        print(f"\n{len(errores)} errores. No se escribió data/cobranza.js.")
        sys.exit(1)
    if "--check" in sys.argv:
        print("\nValidación correcta (modo --check, no se escribió nada).")
        return
    js = ("// GENERADO por scripts/concentrar.py. No editar a mano.\n"
          "window.COBRANZA = " + json.dumps(D, ensure_ascii=False, separators=(",", ":")) + ";\n")
    SALIDA.write_text(js, encoding="utf-8")
    print(f"\nEscrito {SALIDA.relative_to(RAIZ)} ({SALIDA.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
