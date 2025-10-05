import os
import re
import requests
import csv
import psycopg2
from datetime import datetime

from bs4 import BeautifulSoup

# mybigpoint email
EMAIL = os.getenv("TENNIS_EMAIL")
# mybigpoint password
PASSWORD = os.getenv("TENNIS_PASSWORD")
LOGIN_URL = "https://spieler.tennis.de/home"
TARGET_URL = "https://spieler.tennis.de/group/guest"

GET_PARAMS = {
    "p_p_id": "com_liferay_login_web_portlet_LoginPortlet_INSTANCE_pmcalogin",
    "p_p_lifecycle": "0",
    "p_p_state": "normal",
    "p_p_mode": "view",
    "_com_liferay_login_web_portlet_LoginPortlet_INSTANCE_pmcalogin_mvcRenderCommandName": "/login/login"
}
POST_PARAMS = {
    "p_p_id": "com_liferay_login_web_portlet_LoginPortlet_INSTANCE_pmcalogin",
    "p_p_lifecycle": "1",
    "p_p_state": "normal",
    "p_p_mode": "view",
    "_com_liferay_login_web_portlet_LoginPortlet_INSTANCE_pmcalogin_javax.portlet.action": "/login/login",
    "_com_liferay_login_web_portlet_LoginPortlet_INSTANCE_pmcalogin_mvcRenderCommandName": "/login/login"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded",
}

DB_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": os.getenv("PG_PORT", "5432"),
    "database": os.getenv("PG_DB", "tennis"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "1234"),
}

DISCORD_WEBHOOK = "discord_webhook_url"

def db_connect():
    return psycopg2.connect(**DB_CONFIG)

def extract_form_date(html: str) -> str:
    m = re.search(r'name="[^"]*_formDate"[^>]*value="(\d+)"', html)
    return m.group(1) if m else ""

def safe_print(s):
    try:
        print(s)
    except UnicodeEncodeError:
        print(s.encode("utf-8", errors="replace").decode("utf-8"))

def login_and_get(session, email, password, target_url):
    r = session.get(LOGIN_URL, params=GET_PARAMS)
    formDate = extract_form_date(r.text)
    if not formDate:
        safe_print("⚠️ Kein formDate gefunden")
        return None
    payload = {
        "_com_liferay_login_web_portlet_LoginPortlet_INSTANCE_pmcalogin_formDate": formDate,
        "_com_liferay_login_web_portlet_LoginPortlet_INSTANCE_pmcalogin_login": email,
        "_com_liferay_login_web_portlet_LoginPortlet_INSTANCE_pmcalogin_password": password,
        "_com_liferay_login_web_portlet_LoginPortlet_INSTANCE_pmcalogin_saveLastPath": "false",
        "_com_liferay_login_web_portlet_LoginPortlet_INSTANCE_pmcalogin_redirect": "",
        "_com_liferay_login_web_portlet_LoginPortlet_INSTANCE_pmcalogin_doActionAfterLogin": "false",
        "_com_liferay_login_web_portlet_LoginPortlet_INSTANCE_pmcalogin_checkboxNames": "rememberMe",
        "p_auth": ""
    }
    r2 = session.post(LOGIN_URL, params=POST_PARAMS, data=payload)
    r3 = session.get(target_url)
    with open("output.html", "w", encoding="utf-8") as f:
        f.write(r3.text)
    safe_print("Die komplette Antwort wurde in output.html gespeichert.")
    if "Philipp" not in r3.text:
        safe_print("⚠️ Login vermutlich fehlgeschlagen")
        return None
    return r3.text

def extract_current_lk(html):
    soup = BeautifulSoup(html, "html.parser")
    # Suche nach der ersten performance-value in der performance-class
    perf = soup.select_one(".performance-class .performance-value")
    if perf:
        return perf.text.strip()
    # Fallback: Suche nach erstem player-lk außerhalb Aktivitäten
    lk = soup.find("span", class_="player-lk")
    if lk:
        return lk.text.strip().replace("LK:\xa0", "LK: ")
    return ""

def parse_activities(html):
    soup = BeautifulSoup(html, "html.parser")
    activities = []
    for activity in soup.select("li.mbp-activity"):
        # Typ (z.B. Mannschaftsspiel)
        typ = activity.select_one(".mbp-activity-info a.label")
        typ = typ.text.strip() if typ else ""
        # Titelzeile
        title = activity.select_one(".mbp-activity-title")
        title = title.text.strip() if title else ""
        # Link zum Spielbericht
        link = activity.select_one(".mbp-activity-link a")
        link = link["href"] if link else ""
        # Zeitstempel
        timestamp = activity.select_one(".mbp-activity-timestamp")
        date = ""
        time = ""
        if timestamp:
            spans = timestamp.find_all("span")
            if len(spans) >= 2:
                date = spans[0].text.strip()
                time = spans[1].text.strip()
        # Spieler und LKs (alle activity-player in activity-row.mb-activity-body)
        players = []
        for player in activity.select(".activity-row.mbp-activity-body .activity-player"):
            name = ""
            lk = ""
            name_tag = player.select_one(".player-name a")
            if name_tag:
                name = name_tag.text.strip()
            lk_tag = player.select_one(".player-lk")
            if lk_tag:
                lk = lk_tag.text.strip().replace("LK:\xa0", "LK: ")
            players.append({"name": name, "lk": lk})
        activities.append({
            "typ": typ,
            "title": title,
            "link": link,
            "date": date,
            "time": time,
            "players": players
        })
    return activities

def save_to_csv(current_lk, activities, filename="activities.csv"):
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        # Schreibe aktuelle LK als erste Zeile
        writer.writerow(["Aktuelle LK", current_lk])
        # Schreibe Header
        writer.writerow([
            "Typ", "Titel", "Datum", "Uhrzeit", "Link",
            "Spieler 1", "LK 1", "Spieler 2", "LK 2",
            "Spieler 3", "LK 3", "Spieler 4", "LK 4"
        ])
        for a in activities:
            row = [
                a["typ"], a["title"], a["date"], a["time"], a["link"]
            ]
            # Bis zu 4 Spieler/LKs (für Doppel)
            for i in range(4):
                if i < len(a["players"]):
                    row.append(a["players"][i]["name"])
                    row.append(a["players"][i]["lk"])
                else:
                    row.append("")
                    row.append("")
            writer.writerow(row)
    safe_print(f"CSV gespeichert als {filename}")

def remove_duplicates_from_csv(filename="activities.csv"):
    seen = set()
    rows = []
    with open(filename, newline='', encoding="utf-8") as f:
        reader = list(csv.reader(f))
        header = reader[:2]  # Die ersten beiden Zeilen (LK und Spaltenüberschriften) immer behalten
        for row in reader[2:]:
            row_tuple = tuple(row)
            if row_tuple not in seen:
                seen.add(row_tuple)
                rows.append(row)
    with open(filename, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        for h in header:
            writer.writerow(h)
        for row in rows:
            writer.writerow(row)
    safe_print(f"Doppelte Einträge entfernt und in {filename} gespeichert.")

def save_lk_and_matches(current_lk, activities):
    conn = db_connect()
    cur = conn.cursor()
    safe_print("Datenbankverbindung hergestellt.")
    # Tabellen anlegen, falls nicht vorhanden
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lk_history (
            id SERIAL PRIMARY KEY,
            scraped_at TIMESTAMP,
            lk VARCHAR(20)
        );
        CREATE TABLE IF NOT EXISTS matches (
            id SERIAL PRIMARY KEY,
            typ VARCHAR(50),
            titel TEXT,
            date VARCHAR(20),
            time VARCHAR(20),
            link TEXT,
            player1 VARCHAR(100), lk1 VARCHAR(20),
            player2 VARCHAR(100), lk2 VARCHAR(20),
            player3 VARCHAR(100), lk3 VARCHAR(20),
            player4 VARCHAR(100), lk4 VARCHAR(20)
        );
    """)
    safe_print("Tabellen geprüft/erstellt.")
    # LK speichern
    cur.execute("INSERT INTO lk_history (scraped_at, lk) VALUES (%s, %s)", (datetime.now(), current_lk))
    safe_print(f"Aktuelle LK '{current_lk}' in lk_history gespeichert.")
    # Spiele speichern
    for a in activities:
        row = [
            a["typ"], a["title"], a["date"], a["time"], a["link"]
        ]
        for i in range(4):
            if i < len(a["players"]):
                name = a["players"][i]["name"]
                lk = a["players"][i]["lk"]
                lk_clean = re.sub(r"[^0-9,\.]", "", lk)
                row.append(name)
                row.append(lk_clean)
            else:
                row.append("")
                row.append("")
        # Prüfen, ob Match schon existiert (nach titel, date, time)
        cur.execute(
            "SELECT 1 FROM matches WHERE titel=%s AND date=%s AND time=%s",
            (a["title"], a["date"], a["time"])
        )
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO matches (typ, titel, date, time, link,
                    player1, lk1, player2, lk2, player3, lk3, player4, lk4)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, row)
            safe_print(f"Neues Match gespeichert: {a['title']} ({a['date']} {a['time']})")
            # Discord-Nachricht für neues Match
            msg = f""":tennis: **{a["typ"]}**
**Typ:** {a["typ"]}
**Titel:** {a["title"]}
**Datum:** {a["date"]} {a["time"]}
**Link:** {a["link"]}
"""
            for i, p in enumerate(a["players"], 1):
                msg += f"**Spieler {i}:** {p['name']} (LK: {re.sub(r'[^0-9,\.]', '', p['lk'])})\n"
            safe_print("Sende Discord-Nachricht für neues Match...")
            send_discord_message(msg)
        else:
            safe_print(f"Match bereits vorhanden: {a['title']} ({a['date']} {a['time']})")
    conn.commit()
    safe_print("Alle Änderungen gespeichert.")
    notify_if_lk_changed(conn, current_lk)
    cur.close()
    conn.close()
    safe_print("Datenbankverbindung geschlossen.")

def send_discord_message(content):
    if not DISCORD_WEBHOOK:
        safe_print("Kein Discord Webhook gesetzt. Nachricht nicht gesendet.")
        return
    try:
        response = requests.post(DISCORD_WEBHOOK, json={"content": content})
        if response.status_code == 204:
            safe_print("Discord-Nachricht erfolgreich gesendet.")
        else:
            safe_print(f"Discord-Fehler: {response.status_code} {response.text}")
    except Exception as e:
        safe_print(f"Fehler beim Senden an Discord: {e}")

def notify_if_lk_changed(conn, current_lk):
    cur = conn.cursor()
    cur.execute("SELECT lk FROM lk_history ORDER BY id DESC LIMIT 2")
    last_two = cur.fetchall()
    if len(last_two) == 2:
        latest, previous = last_two[0][0], last_two[1][0]
        # Nur die Zahl extrahieren (z.B. "17,5")
        try:
            latest_num = float(latest.replace(",", "."))
            previous_num = float(previous.replace(",", "."))
            diff = latest_num - previous_num
            diff_str = f"{diff:+.1f}"
        except Exception as e:
            safe_print(f"Fehler beim Berechnen der LK-Differenz: {e}")
            diff_str = "?"
        if latest != previous:
            safe_print(f"LK hat sich geändert: alt={previous}, neu={latest} (Differenz: {diff_str}). Sende Discord-Nachricht...")
            send_discord_message(
                f":tennis: **Neue LK:** {latest} (vorher: {previous}, Veränderung: {diff_str})"
            )
        else:
            safe_print("LK hat sich nicht geändert.")
    else:
        safe_print("Nicht genug Einträge für LK-Vergleich.")
    cur.close()

def main():
    session = requests.Session()
    session.headers.update(HEADERS)
    html = login_and_get(session, EMAIL, PASSWORD, TARGET_URL)
    if html:
        current_lk = extract_current_lk(html)
        activities = parse_activities(html)
        # save_to_csv(current_lk, activities)
        # remove_duplicates_from_csv("activities.csv")
        save_lk_and_matches(current_lk, activities)

if __name__ == "__main__":
    main()