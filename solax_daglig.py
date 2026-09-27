#!/usr/bin/env python3
"""
solax_daglig.py – Hämtar daglig SolaX-data via Developer Open API och sparar till CSV + HTML.

Kör dagligen via GitHub Actions (triggas av cron-job.org).
Kräver: pip install requests

Användning:
  python solax_daglig.py            # hämtar och sparar dagens data
  python solax_daglig.py --test     # visa realtidsdata utan att spara
  python solax_daglig.py --debug    # visa rådata från API
"""

import argparse, csv, json, os, sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

# ── Konfiguration ──────────────────────────────────────────────────────────────
CLIENT_ID     = os.environ.get("SOLAX_CLIENT_ID",     "3a607fc3578e4175bc243d17557ed0a6")
CLIENT_SECRET = os.environ.get("SOLAX_CLIENT_SECRET", "_JE20igE9KhhAvJu9dttlXeruL8AYqC0hQFw4YH5L60")
SN            = os.environ.get("SOLAX_SN",            "H35F15L1418008")
BASE_URL      = "https://openapi-eu.solaxcloud.com"

CSV_FILE  = Path(__file__).parent / "solax_data.csv"
HTML_FILE = Path(__file__).parent / "docs" / "index.html"

CSV_FIELDS = [
    "datum",
    "pv_kwh",           # PV Yield / dailyYield
    "ac_kwh",           # Inverter output / dailyACOutput
    "export_kwh",       # Exported energy / todayExportEnergy
    "import_kwh",       # Imported energy / todayImportEnergy
    "bat_charge_kwh",   # Battery charge (från Excel-import)
    "bat_discharge_kwh",# Battery discharge (från Excel-import)
]

# ── OAuth2-token ───────────────────────────────────────────────────────────────
_token_cache: dict = {"token": None, "expires": datetime.min}

def get_token() -> str:
    global _token_cache
    if _token_cache["token"] and datetime.now() < _token_cache["expires"]:
        return _token_cache["token"]
    resp = requests.post(
        f"{BASE_URL}/openapi/auth/oauth/token",
        data={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "client_credentials"},
        headers={"Accept": "*/*", "Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    payload = data.get("result", data)
    token = payload.get("access_token")
    if not token:
        raise ValueError(f"Fick inget access_token: {data}")
    expires_in = int(payload.get("expires_in", 3600))
    _token_cache = {"token": token, "expires": datetime.now() + timedelta(seconds=expires_in - 60)}
    return token

def auth_headers() -> dict:
    return {"Authorization": f"bearer {get_token()}", "Content-Type": "application/json", "Accept": "*/*"}

# ── Realtidsdata ───────────────────────────────────────────────────────────────
def fetch_realtime() -> dict:
    resp = requests.get(
        f"{BASE_URL}/openapi/v2/device/realtime_data",
        params={"snList": SN, "deviceType": "1", "businessType": "1"},
        headers=auth_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    code = data.get("code", -1)
    if code != 10000:
        raise ValueError(f"API-fel {code}: {data.get('message', data)}")
    result = data.get("result", [])
    if not result:
        raise ValueError("API returnerade tomt result")
    return result[0] if isinstance(result, list) else result

def realtime_to_row(r: dict, day: str, existing_row: dict = None) -> dict:
    """
    Bygger daglig rad från realtidsdata.
    Bevarar batterifält från Excel-import om de finns i existing_row.
    """
    row = {
        "datum":            day,
        "pv_kwh":           _f(r.get("dailyYield")),
        "ac_kwh":           _f(r.get("dailyACOutput")),
        "export_kwh":       _f(r.get("todayExportEnergy")),
        "import_kwh":       _f(r.get("todayImportEnergy")),
        "bat_charge_kwh":   "",
        "bat_discharge_kwh": "",
    }
    # Behåll batterivärden från Excel-import om de redan finns
    if existing_row:
        if existing_row.get("bat_charge_kwh"):
            row["bat_charge_kwh"] = existing_row["bat_charge_kwh"]
        if existing_row.get("bat_discharge_kwh"):
            row["bat_discharge_kwh"] = existing_row["bat_discharge_kwh"]
    return row

def _f(v) -> str:
    if v is None or v == "": return ""
    try: return f"{float(v):.2f}"
    except: return str(v)

# ── CSV ────────────────────────────────────────────────────────────────────────
def load_csv() -> dict:
    rows: dict = {}
    if CSV_FILE.exists():
        with open(CSV_FILE, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                for col in CSV_FIELDS:
                    r.setdefault(col, "")
                rows[r["datum"]] = r
    return rows

def save_csv(rows: dict):
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for d in sorted(rows):
            w.writerow(rows[d])
    print(f"✅ CSV sparad: {CSV_FILE}  ({len(rows)} dagar)")

# ── HTML-rapport ───────────────────────────────────────────────────────────────
def generate_html(rows: dict):
    HTML_FILE.parent.mkdir(parents=True, exist_ok=True)
    sorted_rows = sorted(rows.values(), key=lambda r: r["datum"])
    labels    = [r["datum"]                  for r in sorted_rows]
    pv        = [r.get("pv_kwh","")         for r in sorted_rows]
    export_   = [r.get("export_kwh","")     for r in sorted_rows]
    import_   = [r.get("import_kwh","")     for r in sorted_rows]
    bat_ch    = [r.get("bat_charge_kwh","") for r in sorted_rows]
    bat_dis   = [r.get("bat_discharge_kwh","") for r in sorted_rows]

    def js(lst):
        return "[" + ",".join(v if v not in ("", None) else "null" for v in lst) + "]"

    def tot(lst):
        return f"{sum(float(v) for v in lst if v not in ('', None)):.1f}"

    table_rows = ""
    for r in reversed(sorted_rows):
        table_rows += (
            f'<tr>'
            f'<td>{r["datum"]}</td>'
            f'<td>{r.get("pv_kwh","")}</td>'
            f'<td>{r.get("ac_kwh","")}</td>'
            f'<td>{r.get("export_kwh","")}</td>'
            f'<td>{r.get("import_kwh","")}</td>'
            f'<td>{r.get("bat_charge_kwh","")}</td>'
            f'<td>{r.get("bat_discharge_kwh","")}</td>'
            f'</tr>\n'
        )

    last_update = datetime.now().strftime("%Y-%m-%d %H:%M")
    n = len(sorted_rows)

    html = f"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SolaX – Daglig data</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
:root{{
  --bg:#0b0e13;--surface:#131720;--border:#252d3f;
  --gold:#f5c542;--green:#3dd68c;--red:#ff6b6b;--blue:#4ea8de;--purple:#b57bee;
  --muted:#5a6480;--text:#d8dff0;--text2:#8a95b0;
  --mono:'DM Mono',monospace;--sans:'Segoe UI',sans-serif
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:var(--sans);padding:24px 16px}}
h1{{color:var(--gold);font-size:1.3rem;margin-bottom:4px}}
.sub{{color:var(--muted);font-size:.8rem;font-family:var(--mono);margin-bottom:24px}}
.stats{{display:flex;gap:12px;flex-wrap:wrap;max-width:980px;margin-bottom:20px}}
.stat{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 20px;flex:1;min-width:130px}}
.stat .label{{font-size:.65rem;color:var(--muted);font-family:var(--mono);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}}
.stat .val{{font-size:1.35rem;font-family:var(--mono);font-weight:600}}
.gold{{color:var(--gold)}}.green{{color:var(--green)}}.red{{color:var(--red)}}.blue{{color:var(--blue)}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:20px;max-width:980px}}
.card h2{{font-size:.75rem;color:var(--muted);font-family:var(--mono);text-transform:uppercase;letter-spacing:.06em;margin-bottom:14px}}
canvas{{max-height:260px}}
table{{width:100%;border-collapse:collapse;font-size:.78rem}}
th{{text-align:right;color:var(--muted);font-family:var(--mono);font-size:.65rem;text-transform:uppercase;padding:6px 8px;border-bottom:1px solid var(--border)}}
th:first-child{{text-align:left}}
td{{text-align:right;padding:5px 8px;border-bottom:1px solid #1a2030;font-family:var(--mono)}}
td:first-child{{text-align:left;color:var(--text2)}}
tr:hover td{{background:#1a2030}}
</style>
</head>
<body>
<h1>☀️ SolaX – Daglig solcellsdata</h1>
<p class="sub">Uppdaterad {last_update} · {n} dagar loggade</p>

<div class="stats">
  <div class="stat"><div class="label">Total produktion</div><div class="val gold">{tot(pv)} kWh</div></div>
  <div class="stat"><div class="label">Total export</div><div class="val green">{tot(export_)} kWh</div></div>
  <div class="stat"><div class="label">Total import</div><div class="val red">{tot(import_)} kWh</div></div>
  <div class="stat"><div class="label">Bat laddning totalt</div><div class="val blue">{tot(bat_ch)} kWh</div></div>
</div>

<div class="card">
  <h2>Daglig energi (kWh)</h2>
  <canvas id="c1"></canvas>
</div>
<div class="card">
  <h2>Batteri – laddning & urladdning (kWh)</h2>
  <canvas id="c2"></canvas>
</div>

<div class="card">
  <h2>Daglig data</h2>
  <table>
    <thead><tr>
      <th>Datum</th><th>PV (kWh)</th><th>AC-out (kWh)</th>
      <th>Export (kWh)</th><th>Import (kWh)</th>
      <th>Bat laddning</th><th>Bat urladdning</th>
    </tr></thead>
    <tbody>{table_rows}</tbody>
  </table>
</div>

<script>
const L={json.dumps(labels)};
const P={js(pv)},EX={js(export_)},IM={js(import_)},BC={js(bat_ch)},BD={js(bat_dis)};
new Chart('c1',{{
  type:'bar',data:{{labels:L,datasets:[
    {{label:'Produktion',data:P,backgroundColor:'rgba(245,197,66,.8)'}},
    {{label:'Export',data:EX,backgroundColor:'rgba(61,214,140,.7)'}},
    {{label:'Import',data:IM,backgroundColor:'rgba(255,107,107,.6)'}},
  ]}},
  options:{{responsive:true,interaction:{{mode:'index',intersect:false}},
    scales:{{x:{{ticks:{{color:'#5a6480',maxTicksLimit:30,maxRotation:45}},grid:{{color:'#1a2030'}}}},
             y:{{ticks:{{color:'#5a6480'}},grid:{{color:'#1a2030'}}}}}},
    plugins:{{legend:{{labels:{{color:'#d8dff0',font:{{size:11}}}}}}}}}}
}});
new Chart('c2',{{
  type:'bar',data:{{labels:L,datasets:[
    {{label:'Laddning',data:BC,backgroundColor:'rgba(78,168,222,.75)'}},
    {{label:'Urladdning',data:BD,backgroundColor:'rgba(181,123,238,.65)'}},
  ]}},
  options:{{responsive:true,interaction:{{mode:'index',intersect:false}},
    scales:{{x:{{ticks:{{color:'#5a6480',maxTicksLimit:30,maxRotation:45}},grid:{{color:'#1a2030'}}}},
             y:{{ticks:{{color:'#5a6480'}},grid:{{color:'#1a2030'}}}}}},
    plugins:{{legend:{{labels:{{color:'#d8dff0',font:{{size:11}}}}}}}}}}
}});
</script>
</body>
</html>"""
    HTML_FILE.write_text(html, encoding="utf-8")
    print(f"✅ HTML sparad: {HTML_FILE}")

# ── Huvudprogram ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",  action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    existing = load_csv()
    print(f"📂 {len(existing)} dagar i befintlig CSV")
    print("Hämtar realtidsdata …")

    try:
        result = fetch_realtime()
    except Exception as e:
        print(f"❌ {e}")
        sys.exit(1)

    if args.debug:
        print(json.dumps(result, indent=2, ensure_ascii=False))

    today = date.today().isoformat()
    row = realtime_to_row(result, today, existing.get(today))
    print(f"  {row['datum']}  pv={row['pv_kwh']} kWh  export={row['export_kwh']} kWh  import={row['import_kwh']} kWh")

    if args.test:
        print("(--test: ingenting sparades)")
        return

    existing[today] = row
    save_csv(existing)
    generate_html(existing)
    print("🌞 Klart!")

if __name__ == "__main__":
    main()
