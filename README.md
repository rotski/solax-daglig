# solax-data

Automatisk insamling av daglig solcellsdata via [SolaX Developer Open API](https://developer.solaxcloud.com/).

Körs varje dag kl 22:00 via GitHub Actions. Data sparas i `solax_data.csv` och en HTML-rapport genereras på GitHub Pages.

## Filer

| Fil | Syfte |
|-----|-------|
| `solax_daglig.py` | Hämtar data och genererar rapport |
| `solax_data.csv` | All historisk data |
| `docs/index.html` | HTML-rapport (GitHub Pages) |
| `.github/workflows/daglig.yml` | Schemalagd körning |

## Kör lokalt

```bash
pip install requests
python solax_daglig.py --test    # testa utan att spara
python solax_daglig.py           # hämta och spara
python solax_daglig.py --debug   # visa rådata
```

## GitHub Secrets

Lägg till dessa under Settings → Secrets → Actions:

| Secret | Värde |
|--------|-------|
| `SOLAX_CLIENT_ID` | Client ID från developer.solaxcloud.com |
| `SOLAX_CLIENT_SECRET` | Client Secret |
| `SOLAX_SN` | Inverternas serienummer |
