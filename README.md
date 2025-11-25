# mybigpoint-scraper

Dieses Projekt scraped Tennis-Daten von mybigpoint, speichert sie in einer PostgreSQL-Datenbank und kann Discord-Benachrichtigungen senden (zum Beispiel bei einem neuen Match oder einer LK-Änderung).

## Voraussetzungen

- Python 3.10+
- Python librarys: requests, beautifulsoup4, psycopg2-binary
- postgresql-Datenbank installiert

## Nutzung

Passe die Umgebungsvariablen in `scraper.py` an.

## Docker

Es gibt jetzt eine Dockerfile, damit das Skript in einem Container ausgeführt werden kann.

Builden des Images (im Projektroot):

```zsh
docker build -t mybigpoint-scraper:latest .
```

Container lokal starten (Umgebungsvariablen setzen):

```zsh
docker run --rm \
	-e TENNIS_EMAIL=meine@email.de \
	-e TENNIS_PASSWORD=meinpasswort \
	-e PG_HOST=host.docker.internal \
	-e PG_PORT=5432 \
	-e PG_DB=tennis \
	-e PG_USER=postgres \
	-e PG_PASSWORD=1234 \
	mybigpoint-scraper:latest
```

Hinweis:

- Wenn die PostgreSQL-Datenbank lokal auf dem Mac läuft, kann `host.docker.internal` als `PG_HOST` verwendet werden, sonst den Host oder Netzwerk entsprechend anpassen.
- Alternativ kann ein Docker-Netzwerk mit einem Postgres-Container erstellt werden.
