"""Haalt Valorant-matches op via de HenrikDev API en slaat ze op in data/matches/.

Twee bronnen, zodat je zo ver mogelijk terug komt:
1. De live matchgeschiedenis (v4): pagina voor pagina, tot er niets meer komt.
2. De opgeslagen matches van HenrikDev (stored-matches): soms ouder dan de live
   geschiedenis. Van elke match die we nog niet hebben halen we de details op.

Gebruik:
    HENRIK_API_KEY=HDEV-xxxx python scripts/fetch.py

De API-sleutel komt uit een omgevingsvariabele (in GitHub: een repository secret),
zodat hij nooit in de code of op de website terechtkomt.
"""
import http.client
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("HENRIK_BASE", "https://api.henrikdev.xyz")
ROOT = pathlib.Path(__file__).resolve().parent.parent
MATCH_DIR = ROOT / "data" / "matches"
FAILED_FILE = ROOT / "data" / "failed.json"
STATE_FILE = ROOT / "data" / "state.json"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
KEY = os.environ.get("HENRIK_API_KEY", "").strip()
PAUSE = float(os.environ.get("HENRIK_PAUSE", "1.5"))  # pauze tussen verzoeken
MAX_RUN_SECONDS = int(os.environ.get("MAX_RUN_SECONDS", "3000"))  # max ~50 min per run; de volgende run gaat verder
START = time.time()


class NotFound(Exception):
    pass


def get(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(8):
        req = urllib.request.Request(url, headers={
            "Authorization": KEY,
            "Accept": "application/json",
            "User-Agent": "valo-squad-tracker/2.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                time.sleep(PAUSE)
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = e.headers.get("Retry-After") or e.headers.get("X-RateLimit-Reset") or "30"
                wait = int(float(wait)) + 1
                print(f"  limiet bereikt, {wait}s wachten...")
                time.sleep(wait)
                continue
            if e.code == 404:
                body = e.read().decode("utf-8", "replace")[:300]
                raise NotFound(f"{url} -> {body}")
            if e.code in (500, 502, 503, 504):
                time.sleep(5 * (attempt + 1))
                continue
            body = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"HTTP {e.code} voor {url}: {body}") from None
        except (urllib.error.URLError, ConnectionError, TimeoutError, http.client.HTTPException):
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Geen antwoord na meerdere pogingen: {url}")


def out_of_time():
    return time.time() - START > MAX_RUN_SECONDS


def compact(match):
    """Gooi velden weg die het dashboard niet gebruikt, zodat de repo klein blijft."""
    for p in match.get("players", []):
        p.pop("customization", None)
    for r in match.get("rounds", []):
        for st in r.get("stats", []):
            st.pop("damage_events", None)
            st.pop("ability_casts", None)
        for ev in ("plant", "defuse"):
            if r.get(ev):
                r[ev].pop("player_locations", None)
    match.pop("observers", None)
    match.pop("coaches", None)
    return match


def save(m, known):
    mid = m["metadata"]["match_id"]
    if mid in known or not m["metadata"].get("is_completed", True):
        return False
    (MATCH_DIR / f"{mid}.json").write_text(
        json.dumps(compact(m), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    known.add(mid)
    return True


def quote(s):
    return urllib.parse.quote(s, safe="")


def live_history(player, mode, known, full):
    """Live geschiedenis, nieuwste eerst. Bij full=True tot er niets meer komt."""
    if player.get("puuid"):
        path = "/valorant/v4/by-puuid/matches/{}/{}/{}".format(CONFIG["region"], CONFIG["platform"], player["puuid"])
    else:
        path = "/valorant/v4/matches/{}/{}/{}/{}".format(
            CONFIG["region"], CONFIG["platform"], quote(player["name"]), quote(player["tag"]))
    new = 0
    for page in range(CONFIG.get("max_pages", 100)):
        if out_of_time():
            return new, False
        res = get(path, {"mode": mode, "size": 10, "start": page * 10})
        matches = res.get("data") or []
        if not matches:
            return new, True
        seen_old = False
        for m in matches:
            if m["metadata"]["match_id"] in known:
                seen_old = True
            elif save(m, known):
                new += 1
        if seen_old and not full:
            return new, False  # bij een gewone run: alles hierna hebben we al
    return new, True


def stored_history(player, mode, known, failed):
    """Lijst van opgeslagen matches bij HenrikDev; ontbrekende details los ophalen."""
    if player.get("puuid"):
        path = "/valorant/v1/by-puuid/stored-matches/{}/{}".format(CONFIG["region"], player["puuid"])
    else:
        path = "/valorant/v1/stored-matches/{}/{}/{}".format(
            CONFIG["region"], quote(player["name"]), quote(player["tag"]))
    try:
        res = get(path, {"mode": mode})
    except NotFound:
        return 0
    ids = [d["meta"]["id"] for d in res.get("data") or [] if d.get("meta", {}).get("id")]
    new = 0
    for mid in ids:
        if out_of_time():
            break
        if mid in known or failed.get(mid, 0) >= 3:
            continue
        try:
            m = get(f"/valorant/v4/match/{CONFIG['region']}/{mid}").get("data")
            if m and save(m, known):
                new += 1
        except Exception as e:
            failed[mid] = failed.get(mid, 0) + 1
            print(f"  details van {mid} niet gelukt: {e}")
    return new


def find_puuid(player):
    """Zoek de vaste account-ID van een speler op in matches die we al hebben."""
    want = (player["name"].lower(), player["tag"].lower())
    for f in MATCH_DIR.glob("*.json"):
        try:
            for p in json.loads(f.read_text(encoding="utf-8")).get("players", []):
                if (p["name"].lower(), p["tag"].lower()) == want:
                    return p["puuid"]
        except Exception:
            pass
    return None


def main():
    if not KEY:
        sys.exit("HENRIK_API_KEY ontbreekt. Zet hem als omgevingsvariabele of GitHub secret.")
    MATCH_DIR.mkdir(parents=True, exist_ok=True)
    known = {p.stem for p in MATCH_DIR.glob("*.json")}
    failed = json.loads(FAILED_FILE.read_text()) if FAILED_FILE.exists() else {}
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    daily_gap_check = time.gmtime().tm_hour == 3 or os.environ.get("FULL_HISTORY") == "1"
    total, errors = 0, 0
    for player in CONFIG["players"]:
        for mode in CONFIG.get("modes", ["competitive"]):
            sk = f"{player['name']}#{player['tag']}|{mode}".lower()
            backfill = not state.get(sk, {}).get("done")
            try:
                n, reached_end = live_history(player, mode, known, full=backfill)
                if backfill or daily_gap_check:
                    try:
                        n += stored_history(player, mode, known, failed)
                    except Exception as e:
                        print(f"  opgeslagen matches overgeslagen: {e}")
                if backfill and reached_end and not out_of_time():
                    state[sk] = {"done": True, "at": time.strftime("%Y-%m-%d %H:%M", time.gmtime())}
                total += n
                label = "hele historie" if backfill else "nieuwe matches"
                print(f"{player['name']}#{player['tag']} [{mode}, {label}]: {n} nieuw")
            except NotFound as nf:
                if '"code":24' in str(nf):
                    print(f"{player['name']}#{player['tag']}: de API kent dit account pas weer als de speler een potje speelt (mag ook deathmatch). Daarna gaat het vanzelf.")
                    break
                print(f"  API-antwoord: {nf}")
                pu = None if player.get("puuid") else find_puuid(player)
                if pu:
                    print(f"{player['name']}#{player['tag']} niet gevonden op naam, nu via account-ID {pu}.")
                    player["puuid"] = pu
                    try:
                        n, _ = live_history(player, mode, known, full=backfill)
                        n += stored_history(player, mode, known, failed)
                        total += n
                        print(f"{player['name']}#{player['tag']} [{mode}, via account-ID]: {n} nieuw")
                        continue
                    except Exception as e:
                        print(f"  ook via account-ID niet gelukt: {e}")
                errors += 1
                print(f"FOUT: {player['name']}#{player['tag']} niet gevonden. Klopt de naam en tag in config.json?")
            except Exception as e:
                errors += 1
                print(f"FOUT bij {player['name']}#{player['tag']} [{mode}]: {e}")
            if out_of_time():
                break
        if out_of_time():
            print("Tijdslimiet bijna bereikt. De volgende run gaat verder waar deze stopte.")
            break
    FAILED_FILE.write_text(json.dumps(failed))
    STATE_FILE.write_text(json.dumps(state, indent=1))
    print(f"Klaar: {total} nieuwe matches, {len(known)} in totaal.")
    if errors and not known:
        sys.exit(1)


if __name__ == "__main__":
    main()
