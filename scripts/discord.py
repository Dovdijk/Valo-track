"""Stuurt elke maandagochtend een weekoverzicht naar jullie Discord-kanaal.

Werkt alleen als het GitHub secret DISCORD_WEBHOOK is ingesteld. Zonder webhook doet
dit script niets. Met FORCE_DISCORD=true stuur je meteen een overzicht van de
afgelopen 7 dagen (handig om te testen).
"""
import json
import os
import pathlib
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Amsterdam")
except Exception:  # pragma: no cover
    TZ = timezone(timedelta(hours=1))

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATS = ROOT / "data" / "stats.json"
STATE = ROOT / "data" / "discord_state.json"
HOOK = os.environ.get("DISCORD_WEBHOOK", "").strip()
FORCE = os.environ.get("FORCE_DISCORD", "").lower() in ("1", "true", "yes", "ja")


def site_url():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return None


def summarize(rows):
    if not rows:
        return None
    R = sum(r["rounds"] for r in rows) or 1
    k, d, a = (sum(r[x] for r in rows) for x in ("k", "d", "a"))
    shots = sum(r["hs"] + r["bs"] + r["ls"] for r in rows) or 1
    w = sum(r["result"] == "W" for r in rows)
    best = max(rows, key=lambda r: r["acs_sum"] / r["rounds"])
    return dict(m=len(rows), w=w, l=len(rows) - w, wr=w / len(rows), kd=k / max(1, d), k=k, d=d, a=a,
                acs=sum(r["acs_sum"] for r in rows) / R, adr=sum(r["dmg"] for r in rows) / R,
                hs=sum(r["hs"] for r in rows) / shots, fb=sum(r["fb"] for r in rows),
                best=best)


def main():
    if not HOOK:
        print("Geen DISCORD_WEBHOOK ingesteld, Discord-samenvatting overgeslagen.")
        return
    now = datetime.now(TZ)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    week_id = now.strftime("%G-W%V")
    if not FORCE:
        if now.weekday() != 0 or now.hour < 9:
            print("Geen maandagochtend, niets verstuurd.")
            return
        if state.get("last_week") == week_id:
            print("Deze week al verstuurd.")
            return
    start = now - timedelta(days=7)
    data = json.loads(STATS.read_text(encoding="utf-8"))
    fields, mvp = [], None
    for p in data["players"]:
        rows = [r for r in data["matches"].get(p["key"], [])
                if datetime.fromisoformat(r["date"].replace("Z", "+00:00")) >= start]
        s = summarize(rows)
        if not s:
            fields.append(dict(name=p["name"], value="Geen matches deze week.", inline=False))
            continue
        b = s["best"]
        fields.append(dict(name=f"{p['name']}  ·  {s['w']}W {s['l']}L", inline=False, value=(
            f"**{s['m']}** matches · winrate **{round(s['wr'] * 100)}%**\n"
            f"K/D **{s['kd']:.2f}** ({s['k']}/{s['d']}/{s['a']}) · ACS **{round(s['acs'])}** · ADR {round(s['adr'])} · HS {round(s['hs'] * 100)}%\n"
            f"Beste match: {b['map']} als {b['agent']}, {b['k']}/{b['d']}/{b['a']}, ACS {round(b['acs_sum'] / b['rounds'])}")))
        if s["m"] >= 3 and (not mvp or s["acs"] > mvp[1]):
            mvp = (p["name"], s["acs"])
    together = [x for x in data.get("shared", [])
                if datetime.fromisoformat(x["date"].replace("Z", "+00:00")) >= start]
    if together:
        tw = sum(next(iter(x["rows"].values()))["result"] == "W" for x in together)
        fields.append(dict(name="Samen gespeeld", inline=False,
                           value=f"{len(together)} matches samen, **{tw}** gewonnen ({round(tw / len(together) * 100)}%)"))
    desc = f"Overzicht van {start.strftime('%d-%m')} t/m {now.strftime('%d-%m-%Y')}."
    if mvp:
        desc += f"\n🏆 MVP van de week: **{mvp[0]}** met een ACS van {round(mvp[1])}."
    embed = dict(title=f"Squad Tracker · week {now.strftime('%V')}", description=desc, color=0xFF4655,
                 fields=fields[:25], footer=dict(text="Data via HenrikDev API · niet van of goedgekeurd door Riot Games"))
    url = site_url()
    if url:
        embed["url"] = url
    body = json.dumps(dict(username="Squad Tracker", embeds=[embed])).encode()
    req = urllib.request.Request(HOOK, data=body, headers={"Content-Type": "application/json", "User-Agent": "valo-squad-tracker"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"Discord-samenvatting verstuurd (HTTP {r.status}).")
    except Exception as e:
        print(f"Discord-samenvatting mislukt: {e}")
        sys.exit(0)  # een mislukte Discord-post mag de rest niet stoppen
    state["last_week"] = week_id
    STATE.write_text(json.dumps(state))


if __name__ == "__main__":
    main()
