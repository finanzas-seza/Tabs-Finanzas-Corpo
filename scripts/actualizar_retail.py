#!/usr/bin/env python3
"""
Actualiza los pagos de Walmart con los Retail que Tesorería deja en
  <carpeta_retail>/<EMPRESA>/<subcarpeta Retail>/   (ver "retail" en data/config.json)

Toma el CSV más reciente de cada empresa en data/fuentes/, busca en el Retail las facturas
de Walmart que siguen "Pendiente de pago" o "Pago no localizado en Retail" (pendiente de validación) y, si
encuentra el pago, las marca Pagada con la fecha del Retail. Escribe un CSV nuevo
AAAAMMDD_cobranza_<EMP>.csv (fecha de hoy) y deja el anterior intacto.

Reglas de cruce (las mismas de la skill de ingesta):
  - Folio exacto, o folio + 1 a 4 caracteres del UUID (Walmart los agrega: 758049321, 5971A).
  - El monto del Retail debe cuadrar (±$2) con subtotal × 1.16, × 1.12 (neto de retención) o el subtotal.
  - "Descuentos manuales" no cuentan como pago.

Uso (desde la raíz del repo):
    python scripts/actualizar_retail.py               # todas las empresas
    python scripts/actualizar_retail.py SEZA GSG      # solo algunas
    python scripts/actualizar_retail.py --check       # muestra qué cambiaría, no escribe
Después correr:  python scripts/concentrar.py

Requiere: pip install pandas lxml openpyxl
"""
import json, re, sys, unicodedata, datetime as dt
from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = RAIZ / "data" / "fuentes"
CFG = json.loads((RAIZ / "data" / "config.json").read_text(encoding="utf-8"))

COLS = {'fecha de factura': 'fecha_factura', 'invoice date': 'fecha_factura',
        'numero de factura': 'num', 'invoice number': 'num',
        'monto de la factura': 'monto', 'invoice amount': 'monto',
        'fecha de pago': 'fecha_pago', 'paid date': 'fecha_pago',
        'numero de documento': 'doc', 'document number': 'doc',
        'tipo de docto': 'tipo', 'docto type': 'tipo'}
REVISAR = {"Sin pago en la fuente", "Pagado en Registro sin pago en Retail",
           "Pago no localizado en Retail (Registro dice pagada)"}


def _col(c):
    c = str(c[-1] if isinstance(c, tuple) else c)
    try:
        c = c.encode("latin-1").decode("utf-8")      # encabezados "NÃºmero" del portal
    except Exception:
        pass
    c = unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode().strip().lower()
    return COLS.get(c)


def _norm(df):
    df = df.rename(columns={c: _col(c) for c in df.columns})
    df = df[[c for c in df.columns if c]]
    return df.loc[:, ~df.columns.duplicated()]


def leer_retail(f: Path):
    if f.suffix.lower() == ".xlsx":
        raw = pd.read_excel(f, header=None)
        h = next(i for i in range(15) if any(_col(v) == "fecha_pago" for v in raw.iloc[i]))
        df = raw.iloc[h + 1:].copy()
        df.columns = raw.iloc[h]
        df = _norm(df)
    else:  # .xls del portal = HTML con tablas anidadas: concatenar las internas
        t = pd.read_html(f)
        df = pd.concat([_norm(x) for x in (t[1:] if len(t) > 1 else t)], ignore_index=True)
    df = df[df["num"].notna()].copy()
    df["num"] = df["num"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    df["fecha_pago"] = pd.to_datetime(df["fecha_pago"], errors="coerce")
    df["monto"] = pd.to_numeric(df["monto"], errors="coerce")
    df["tipo"] = df["tipo"].astype(str)
    df["archivo"] = f.name
    return df


def cruza(folio, subtotal, P):
    d = re.sub(r"\D", "", folio)
    if not d:
        return None
    c = P[P["num"].str.startswith(d)]
    c = c[c["num"].str.len() - len(d) <= 4]
    if c.empty:
        return None
    ok = c[c["monto"].map(lambda m: any(abs(m - subtotal * k) <= 2 for k in (1.16, 1.12, 1.0)))]
    return ok if not ok.empty else None


def main():
    rcfg = CFG["retail"]
    base = Path(rcfg["carpeta"])
    empresas = [a for a in sys.argv[1:] if not a.startswith("--")] or list(rcfg["subcarpetas"])
    check = "--check" in sys.argv
    hoy = dt.date.today().strftime("%Y%m%d")
    for emp in empresas:
        carpeta = base / rcfg["subcarpetas"][emp]
        archivos = sorted(p for p in carpeta.rglob("*") if p.suffix.lower() in (".xls", ".xlsx") and not p.name.startswith("~$"))
        if not archivos:
            print(f"{emp}: no hay archivos de Retail en {carpeta}")
            continue
        P = pd.concat([leer_retail(f) for f in archivos], ignore_index=True)
        P = P[~P["tipo"].str.contains("Descuento", case=False) & P["fecha_pago"].notna()]
        P = P.drop_duplicates(["num", "doc", "fecha_pago", "monto"])
        corte = P["fecha_pago"].max().strftime("%Y-%m-%d")

        previo = sorted(FUENTES.glob(f"*_cobranza_{emp}.csv"))[-1]
        d = pd.read_csv(previo, dtype=str, keep_default_na=False)
        clientes = set(rcfg["clientes"][emp])
        n, imp = 0, 0.0
        for i, x in d.iterrows():
            if x["cliente"] not in clientes or x["estatus"] not in ("Pendiente de pago", "Pendiente de validación", "En aclaración", "Por revisar") or x["validacion"] not in REVISAR:
                continue
            m = cruza(x["folio"], float(x["subtotal"] or 0), P)
            if m is None:
                continue
            u = m.sort_values("fecha_pago").iloc[-1]
            d.loc[i, ["estatus", "validacion", "fecha_pago", "fuente_pago", "referencia_pago"]] = [
                "Pagada", "", u["fecha_pago"].strftime("%Y-%m-%d"), "Retail Walmart", f"Retail #{u['num']} | Doc {u['doc']}"]
            n += 1
            imp += float(x["subtotal"])
        d.loc[d["cliente"].isin(clientes), "fecha_corte"] = corte
        pend = d[(d["estatus"] == "Pendiente de pago") & d["cliente"].isin(clientes)]
        print(f"{emp}: {len(archivos)} archivos de Retail, pagos hasta {corte} · base {previo.name}")
        print(f"   {n} facturas pasan a Pagada (${imp:,.2f}) · siguen pendientes de Walmart: {len(pend)} (${pend['subtotal'].astype(float).sum():,.2f})")
        if not check and n:
            salida = FUENTES / f"{hoy}_cobranza_{emp}.csv"
            d.to_csv(salida, index=False, encoding="utf-8")
            print(f"   Escrito {salida.relative_to(RAIZ)}. Actualiza cortes.{emp} = {corte} en data/config.json")
    if not check:
        print("\nSiguiente paso: python scripts/concentrar.py")


if __name__ == "__main__":
    main()
