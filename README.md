# Trading-Tool

Webanwendung mit Live-Chart (BTC, ETH, SOL, Gold via PAXG), Login, Beispiel-Strategie
(SMA-Crossover) mit Signalen im Chart und einfachem Backtest.

```
Browser ──HTTPS──▶ Caddy (Zertifikat automatisch) ──▶ FastAPI ──▶ Binance (REST + WebSocket)
```

- `backend/` FastAPI: Login, Marktdaten, Live-Relay, Strategien (`strategies.py`)
- `frontend/` Chart mit TradingView Lightweight Charts
- `docker-compose.yml` App + Caddy, `.github/workflows/deploy.yml` Auto-Deploy bei Push auf `main`

## Lokal testen

```bash
cd backend
pip install -r requirements.txt
python test_strategies.py                      # Strategie-Check, gibt "OK" aus
mkdir -p static && cp ../frontend/* static/
APP_PASSWORD=testtest1 APP_SECRET=irgendeinlangergeheimer COOKIE_SECURE=0 \
  uvicorn main:app --reload
```

Dann http://localhost:8000 öffnen.

## Einrichtung auf Hetzner (einmalig)

1. **Server anlegen:** Cloud-Server mit Ubuntu 24.04 (z. B. CX22), SSH-Key hinterlegen.
2. **Docker installieren und Firewall setzen** (als root auf dem Server):
   ```bash
   curl -fsSL https://get.docker.com | sh
   ufw allow OpenSSH && ufw allow 80,443/tcp && ufw enable
   ```
   Zusätzlich in der Hetzner-Cloud-Firewall nur Ports 22, 80 und 443 freigeben.
3. **Repo auf den Server holen:** privates GitHub-Repo anlegen, Code hochladen. Auf dem
   Server einen Deploy-Key erzeugen (`ssh-keygen -t ed25519 -f ~/.ssh/gh_deploy -N ""`), den
   öffentlichen Teil im Repo unter *Settings → Deploy keys* eintragen (nur Lesen), dann:
   ```bash
   git clone git@github.com:DEIN-NAME/DEIN-REPO.git /opt/tradingtool
   ```
   (Falls nötig `~/.ssh/config` so setzen, dass `gh_deploy` für github.com verwendet wird.)
4. **Konfiguration:**
   ```bash
   cd /opt/tradingtool
   cp .env.example .env
   nano .env      # DOMAIN, APP_PASSWORD, APP_SECRET (openssl rand -hex 32)
   docker compose up -d --build
   ```
   Ohne eigene Domain funktioniert `DOMAIN=<IP-mit-Bindestrichen>.sslip.io`
   (z. B. `203-0-113-10.sslip.io`); Caddy holt dafür ein echtes Zertifikat.
5. **Test:** `https://<DOMAIN>` öffnen, anmelden, Chart muss live laufen.

## Auto-Deploy über GitHub Actions

Im Repo unter *Settings → Secrets and variables → Actions* anlegen:

| Secret | Inhalt |
|---|---|
| `SERVER_HOST` | IP oder Domain des Servers |
| `SERVER_USER` | SSH-Benutzer (z. B. `root` oder ein eigener Deploy-User mit Docker-Rechten) |
| `SERVER_SSH_KEY` | privater SSH-Schlüssel nur für Deployments (`ssh-keygen -t ed25519 -f deploy_key`, öffentlichen Teil in `~/.ssh/authorized_keys` des Servers) |
| `SERVER_KNOWN_HOSTS` | Ausgabe von `ssh-keyscan <SERVER_HOST>` |

Danach aktualisiert jeder Push auf `main` den Server automatisch.

## Strategien erweitern

In `backend/strategies.py` eine neue Funktion schreiben, die Signale
`{"time", "side", "price"}` liefert, und in `main.py` im Endpunkt `/api/data` einhängen.
`backtest()` bewertet jede Signalliste gleich.

## Wichtige Hinweise

- **Gold:** Binance hat kein XAU/USD. PAXG ist tokenisiertes Gold (1 Token = 1 Feinunze),
  folgt dem Goldpreis eng, ist aber kein offizieller Spotpreis und handelt rund um die Uhr,
  auch am Wochenende. Für echte XAU/USD-Daten später einen Datenanbieter (z. B. Twelve Data)
  im Backend ergänzen.
- **Binance-Erreichbarkeit:** Von Hetzner-Servern in Deutschland ist die Binance-API
  erreichbar; aus einzelnen Ländern (z. B. USA) ist sie gesperrt.
- **Backtest-Grenzen:** Nur die letzten 1000 Kerzen, keine Slippage, vereinfachte
  Ausführung zum Schlusskurs. Gute Backtest-Zahlen sind keine Garantie für die Zukunft.
- **Echte Orders** sind bewusst nicht enthalten. Erst Paper-Trading, dann kleine Beträge,
  API-Keys nur mit Handelsrechten und ohne Auszahlungsrechte.
- Keine Anlageberatung.
