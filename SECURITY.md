# Sicherheitshinweise (AP7 - Schwachstellenanalyse)

## Wichtig fuer den Produktivstart
Der Server MUSS mit dem Flag `--no-server-header` gestartet werden, um den
"Server: uvicorn"-Header zu unterdruecken (Framework-Fingerprinting-Schutz):

    uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-server-header

Dies wird im finalen Dockerfile (AP8) als CMD-Standard hinterlegt.

## Durchgefuehrte Pruefungen und Ergebnisse

| Kategorie | Test | Ergebnis |
|---|---|---|
| SQL Injection | Payload in Login/Pfad-Parametern | Abgewehrt durch ORM + Pydantic-Validierung |
| Broken Access Control | Checkout/Queue-Aktionen fuer fremde Ressourcen | 403/404, korrekt blockiert |
| JWT-Manipulation | alg=none, falsches Secret, Rolle im Payload gefaelscht | 401, Signaturpruefung greift zuverlaessig |
| IDOR | Fremde Queue-Eintraege/Geraete ueber ID loeschen | 403 Forbidden |
| Mass Assignment | role=admin, id, is_verified im Register-Payload | Ignoriert, da explizite Pydantic-Schemas ohne diese Felder |
| User Enumeration | Login- und Registrierungs-Fehlermeldungen | Generisch, kein Unterschied zwischen "falsches Passwort" und "User existiert nicht" |
| Refresh-Token-Reuse | Bereits verwendetes/rotiertes Token erneut nutzen | 401, Token-Rotation mit Revocation korrekt implementiert |
| Rate Limiting | Brute-Force auf /auth/login | 429 nach ueberschrittenem Limit |
| Security Header | X-Content-Type-Options, X-Frame-Options, etc. | Nachgeruestet via Middleware (siehe app/main.py) |
| DoS durch grosse Payloads | Sehr lange Strings in name/full_name/password | Laengenbegrenzungen in allen Schemas ergaenzt (verhindert u.a. teures Argon2-Hashing bei ueberlangen Passwoertern) |
| Server-Header-Leak | "Server: uvicorn" in jeder Response | Behoben durch Start-Flag --no-server-header |
| Directory Traversal | Pfad-Manipulation in URL | 404, kein Dateisystemzugriff moeglich (kein Static-File-Serving von sensiblen Pfaden) |

## Bekannte Limitierungen (bewusst nicht behoben, da ausserhalb des Scopes)
- Kein Content-Security-Policy-Header gesetzt, da diese API reines JSON liefert und von einer separaten Frontend/Mobile-App konsumiert wird (CSP macht dort primaer im Frontend selbst Sinn).
- Passwort-Reset-Endpunkt gibt bewusst immer eine 202-Erfolgsmeldung zurueck, unabhaengig davon ob die E-Mail existiert (Anti-Enumeration), das Reset-Token selbst wird aktuell nicht per E-Mail versendet (TODO fuer produktiven E-Mail-Versand, Platzhalter vorhanden).
