# EVLädeQueue

Vollstaendige Webanwendung (Backend + Frontend) fuer die Verwaltung von
EV-Ladepunkten mit Warteschlangen-Funktion und Parkplatz-Tauschangebot.

- **Backend**: REST-API mit FastAPI, nutzbar von Web- und Mobile-Clients
- **Frontend**: Eingebautes Web-Interface (reines HTML/CSS/JavaScript, kein
  Build-Tooling notwendig), wird direkt vom Backend unter `/` ausgeliefert

## Lokale Entwicklung

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env mit echten Secrets befuellen (siehe Abschnitt "Secrets generieren")
uvicorn app.main:app --reload --no-server-header
```

### Windows

Auf Windows gibt es zwei gaengige Wege: **PowerShell mit lokalem Python** oder
**WSL2** (empfohlen, da naeher am Produktionsverhalten unter Linux).

#### Variante A: PowerShell (natives Windows)

Voraussetzung: [Python 3.12](https://www.python.org/downloads/windows/) ist
installiert und beim Setup wurde "Add python.exe to PATH" aktiviert.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# .env mit echten Secrets befuellen (siehe Abschnitt "Secrets generieren")
uvicorn app.main:app --reload --no-server-header
```

Falls PowerShell die Aktivierung mit einer Fehlermeldung zu
"Ausfuehrung von Skripts deaktiviert" blockiert, einmalig folgendes ausfuehren
(nur fuer den aktuellen Nutzer, keine Admin-Rechte notwendig):

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Alternativ in der klassischen `cmd.exe` (Eingabeaufforderung) statt PowerShell:

```cmd
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --no-server-header
```

#### Variante B: WSL2 (empfohlen)

Falls [WSL2](https://learn.microsoft.com/windows/wsl/install) mit einer
Ubuntu-Distribution installiert ist, im WSL-Terminal genau wie unter Linux
vorgehen (siehe Abschnitt "macOS / Linux" oben). Das ist besonders sinnvoll,
wenn du spaeter auch Docker unter Windows nutzen willst, da Docker Desktop auf
Windows standardmaessig den WSL2-Backend verwendet.

Die API ist in beiden Faellen danach unter http://localhost:8000/api/v1/docs
erreichbar.

## Deployment mit Docker

Voraussetzung fuer Windows: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
mit aktiviertem WSL2-Backend (Standardeinstellung bei aktuellen Versionen).

### macOS / Linux / WSL2 (Terminal)

```bash
cp .env.example .env
# .env mit echten Secrets befuellen (siehe unten)
docker compose up -d --build
```

### Windows (PowerShell, ohne WSL2)

```powershell
Copy-Item .env.example .env
# .env mit echten Secrets befuellen (siehe unten)
docker compose up -d --build
```

Die API laeuft danach unter http://localhost:8000, persistente Daten liegen im
Docker-Volume `ladeplatz-data`. Docker Desktop muss dafuer im Hintergrund
laufen (Symbol in der Windows-Taskleiste pruefen).

### Secrets generieren

**macOS / Linux / WSL2:**

```bash
openssl rand -hex 32   # fuer APP_SECRET_KEY
openssl rand -hex 32   # fuer JWT_SECRET_KEY
```

**Windows (PowerShell, ohne WSL2):**

OpenSSL ist auf Windows meist nicht vorinstalliert. Alternativ mit PowerShell
selbst einen kryptographisch sicheren 32-Byte-Hexwert erzeugen:

```powershell
-join ((1..32) | ForEach-Object { "{0:x2}" -f (Get-Random -Minimum 0 -Maximum 256) })
```

Den Befehl zweimal ausfuehren (einmal fuer `APP_SECRET_KEY`, einmal fuer
`JWT_SECRET_KEY`) und die Ausgaben in die `.env`-Datei eintragen. Wer Git fuer
Windows installiert hat, kann alternativ auch Git Bash oeffnen und dort ganz
normal den `openssl`-Befehl von oben verwenden, da Git Bash OpenSSL mitliefert.

Beide Werte muessen sich unterscheiden und in der `.env`-Datei eingetragen werden,
niemals in Git committen (siehe `.gitignore`).

### Hinweis fuer Windows: Zeilenenden und Pfade

- Falls Git auf Windows automatisch CRLF-Zeilenenden erzeugt, kann das bei
  `.sh`-Skripten oder innerhalb von Docker-Containern zu Problemen fuehren.
  Empfehlung: In der Datei `.gitattributes` (falls genutzt) `* text=auto eol=lf`
  setzen, oder Git mit `git config --global core.autocrlf input` konfigurieren.
- Der Datenbankpfad in `.env` (`DATABASE_URL=sqlite:///./data/ladeplatz.db`)
  ist ein relativer Unix-Stil-Pfad und funktioniert unter Windows (PowerShell/cmd)
  genauso wie unter Linux/macOS, da SQLAlchemy die Pfadtrennung intern uebernimmt.
  Es muss nichts angepasst werden.

### Wichtige Umgebungsvariablen

| Variable | Beschreibung |
|---|---|
| `APP_SECRET_KEY` / `JWT_SECRET_KEY` | Kryptographische Secrets, je 32 Byte |
| `DATABASE_URL` | Standardmaessig SQLite, fuer Produktion ggf. PostgreSQL |
| `SMTP_*` | Zugangsdaten fuer den E-Mail-Versand bei Warteschlangen-Benachrichtigungen |
| `CORS_ALLOWED_ORIGINS` | Kommagetrennte Liste erlaubter Frontend/App-Origins |
| `ADMIN_BOOTSTRAP_EMAIL` / `ADMIN_BOOTSTRAP_PASSWORD` | Wird nur beim allerersten Start verwendet, um einen Admin-Account anzulegen |

## Sicherheitshinweise

Siehe `SECURITY.md` fuer die Ergebnisse der Schwachstellenanalyse (AP7) und
wichtige Betriebsvorgaben (z. B. `--no-server-header`-Flag).

## Frontend nutzen

Nach dem Start (lokal oder via Docker) ist das Web-Frontend direkt unter
`http://localhost:8000/` erreichbar. Dort koennen sich Mitglieder registrieren,
Standorte und Ladepunkte einsehen, einchecken, sich in Warteschlangen eintragen
und den Abstoepsel-Workflow durchfuehren. Admins sehen zusaetzlich einen
"Verwaltung"-Reiter zum Anlegen von Standorten und Ladepunkten.

Das Frontend liegt unter `app/templates/index.html` und `app/static/` und wird
automatisch mit demselben Uvicorn-Prozess wie die API ausgeliefert – es ist
kein separater Webserver oder zusaetzlicher Container notwendig.

## API-Dokumentation

- Swagger UI: `/api/v1/docs`
- ReDoc: `/api/v1/redoc`
- OpenAPI-Schema: `/api/v1/openapi.json`

## Healthcheck

`GET /api/v1/health` liefert `{"status": "ok"}` bei erfolgreichem Betrieb und wird
sowohl vom Docker-Healthcheck als auch von docker-compose verwendet.
