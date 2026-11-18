"""Rekent alle opgeslagen matches om naar data/stats.json voor het dashboard.

Per speler en per match komt er één rij met ruwe tellingen. Het dashboard telt
die rijen zelf op, zodat je kunt filteren op bijvoorbeeld de laatste 10 matches.
"""
import json
import math
import pathlib
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
MATCH_DIR = ROOT / "data" / "matches"
OUT = ROOT / "data" / "stats.json"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

TRADE_MS = 5000          # een death telt als getraded als de killer binnen 5 s valt
EARLY_S = 20             # deaths in de eerste 20 s van een ronde
ALONE_UNITS = 1500       # verder dan dit van de dichtstbijzijnde teamgenoot = alleen gestorven


def key(name, tag):
    return f"{name}#{tag}".lower()


FRIENDS = {key(p["name"], p["tag"]): p for p in CONFIG["players"]}


def buy_type(round_idx, loadout):
    if round_idx in (0, 12):
        return "pistol"
    if loadout < 1500:
        return "eco"
    if loadout < 3600:
        return "force"
    return "full"


def first_half_attacker(m):
    """Bepaal welk team in de eerste helft aanviel, op basis van wie er plantte."""
    c = Counter()
    for i, r in enumerate(m["rounds"]):
        pl = r.get("plant")
        if pl and pl.get("player"):
            team = pl["player"].get("team")
            c[team if i < 12 or (i >= 24 and (i - 24) % 2 == 0) else ("Blue" if team == "Red" else "Red")] += 1
    return c.most_common(1)[0][0] if c else "Red"


def is_attacker(team, idx, fha):
    first_half_sides = idx < 12 or (idx >= 24 and (idx - 24) % 2 == 0)
    return (team == fha) == first_half_sides


def dist(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def analyse(m):
    md = m["metadata"]
    players = m["players"]
    team_of = {p["puuid"]: p["team_id"] for p in players}
    teams = {t["team_id"]: t for t in m["teams"]}
    rounds = m["rounds"]
    n_rounds = len(rounds) or 1
    fha = first_half_attacker(m)

    kills = m.get("kills") or []
    # rondenummers kunnen 0- of 1-gebaseerd zijn; normaliseer naar 0-gebaseerd
    offset = 0 if (any(k["round"] == 0 for k in kills) or (rounds and rounds[0].get("id") == 0)) else 1
    by_round = defaultdict(list)
    for k in kills:
        by_round[k["round"] - offset].append(k)
    for lst in by_round.values():
        lst.sort(key=lambda k: k["time_in_round_in_ms"])

    rows = {}
    for p in players:
        kk = key(p["name"], p["tag"])
        if kk not in FRIENDS:
            continue
        pu, team = p["puuid"], p["team_id"]
        st = p["stats"]
        my_team = teams.get(team, {})
        other = next((t for tid, t in teams.items() if tid != team), {})
        won = bool(my_team.get("won"))
        draw = not my_team.get("won") and not other.get("won")
        row = dict(
            match=md["match_id"], date=md["started_at"], map=(md.get("map") or {}).get("name"),
            mode=(md.get("queue") or {}).get("name") or (md.get("queue") or {}).get("id"),
            season=(md.get("season") or {}).get("short"),
            with_=sorted(key(q["name"], q["tag"]) for q in players
                         if q["team_id"] == team and q["puuid"] != pu and key(q["name"], q["tag"]) in FRIENDS),
            agent=(p.get("agent") or {}).get("name"), tier=(p.get("tier") or {}).get("name"),
            result="D" if draw else ("W" if won else "L"),
            score=f'{my_team.get("rounds", {}).get("won", 0)}-{my_team.get("rounds", {}).get("lost", 0)}',
            rounds=n_rounds, k=st["kills"], d=st["deaths"], a=st["assists"], acs_sum=st["score"],
            dmg=st["damage"]["dealt"], dmg_recv=st["damage"]["received"],
            hs=st["headshots"], bs=st["bodyshots"], ls=st["legshots"],
            kast=0, fb=0, fd=0, mk2=0, mk3=0, mk4=0, mk5=0, clutch_w=0, clutch_a=0,
            plants=0, defuses=0, trade_k=0, traded_d=0, early_d=0, death_time_sum=0.0,
            deaths_known_team=0, alone_d=0,
            atk_rounds=0, atk_won=0, atk_k=0, atk_d=0, def_rounds=0, def_won=0, def_k=0, def_d=0,
            buy={t: [0, 0] for t in ("pistol", "eco", "force", "full")},
            util=sum((p.get("ability_casts") or {}).get(k) or 0 for k in ("ability1", "ability2", "grenade")),
            ults=(p.get("ability_casts") or {}).get("ultimate") or 0,
            weapons={}, loadout_sum=0, hero_n=0, hero_w=0,
        )
        weapons = Counter()

        for idx, r in enumerate(rounds):
            rk = by_round.get(idx, [])
            atk = is_attacker(team, idx, fha)
            round_won = r.get("winning_team") == team
            side = "atk" if atk else "def"
            row[f"{side}_rounds"] += 1
            row[f"{side}_won"] += int(round_won)

            # economie
            ps = next((s for s in r.get("stats", []) if s["player"]["puuid"] == pu), None)
            if ps:
                lv = (ps.get("economy") or {}).get("loadout_value") or 0
                row["loadout_sum"] += lv
                bt = buy_type(idx, lv)
                row["buy"][bt][1] += 1
                row["buy"][bt][0] += int(round_won)
                def buys(st2):
                    e2 = st2.get("economy") or {}
                    wn = (e2.get("weapon") or {}).get("name")
                    return bool((e2.get("loadout_value") or 0) >= 2000 or (wn and wn not in PISTOLS))
                if idx not in (0, 12) and buys(ps):
                    mates = [buys(s2) for s2 in r.get("stats", [])
                             if s2["player"]["puuid"] != pu and team_of.get(s2["player"]["puuid"]) == team]
                    if mates and sum(mates) <= 1:
                        row["hero_n"] += 1
                        row["hero_w"] += int(round_won)

            if (r.get("plant") or {}).get("player", {}).get("puuid") == pu:
                row["plants"] += 1
            if (r.get("defuse") or {}).get("player", {}).get("puuid") == pu:
                row["defuses"] += 1

            my_kills = [k for k in rk if k["killer"]["puuid"] == pu and team_of.get(k["victim"]["puuid"]) != team]
            assisted = any(pu in [a["puuid"] for a in k.get("assistants", [])] for k in rk)
            death = next((k for k in rk if k["victim"]["puuid"] == pu), None)
            row[f"{side}_k"] += len(my_kills)
            for k in my_kills:
                weapons[(k.get("weapon") or {}).get("name") or "Ability/overig"] += 1
            n = len(my_kills)
            if n >= 2:
                row[f"mk{min(n, 5)}"] += 1

            traded = False
            if death:
                row[f"{side}_d"] += 1
                t = death["time_in_round_in_ms"]
                row["death_time_sum"] += t / 1000
                if t / 1000 <= EARLY_S:
                    row["early_d"] += 1
                killer = death["killer"]["puuid"]
                traded = any(k["victim"]["puuid"] == killer and team_of.get(k["killer"]["puuid"]) == team
                             and 0 <= k["time_in_round_in_ms"] - t <= TRADE_MS for k in rk)
                row["traded_d"] += int(traded)
                # stond er een teamgenoot in de buurt?
                loc = death.get("location")
                mates = [pl for pl in death.get("player_locations", [])
                         if pl["player"]["puuid"] != pu and team_of.get(pl["player"]["puuid"]) == team]
                if loc and mates:
                    row["deaths_known_team"] += 1
                    if min(dist(loc, pl["location"]) for pl in mates) > ALONE_UNITS:
                        row["alone_d"] += 1

            # trade-kills: jij doodt iemand die net een teamgenoot doodde
            for k in my_kills:
                v = k["victim"]["puuid"]
                if any(e["killer"]["puuid"] == v and team_of.get(e["victim"]["puuid"]) == team
                       and 0 <= k["time_in_round_in_ms"] - e["time_in_round_in_ms"] <= TRADE_MS for e in rk):
                    row["trade_k"] += 1

            if rk:
                f = rk[0]
                if f["killer"]["puuid"] == pu:
                    row["fb"] += 1
                if f["victim"]["puuid"] == pu:
                    row["fd"] += 1

            if my_kills or assisted or not death or traded:
                row["kast"] += 1

            # clutch: jij bent de laatste levende van je team en er leeft nog minstens één tegenstander
            alive = {q["puuid"] for q in players}
            clutch_n = 0
            for k in rk:
                alive.discard(k["victim"]["puuid"])
                mine = [q for q in alive if team_of.get(q) == team]
                theirs = [q for q in alive if team_of.get(q) != team]
                if not clutch_n and mine == [pu] and theirs:
                    clutch_n = len(theirs)
            if clutch_n:
                row["clutch_a"] += 1
                row["clutch_w"] += int(round_won)

        row["weapons"] = dict(weapons)
        row["with"] = row.pop("with_")
        rows[kk] = row
    return rows


MAPS_FILE = ROOT / "data" / "maps.json"


def load_maps():
    """Kaartgegevens (minimap, coördinaten-omrekening, callouts) van valorant-api.com, met cache."""
    import urllib.request
    cache = json.loads(MAPS_FILE.read_text(encoding="utf-8")) if MAPS_FILE.exists() else {}
    try:
        req = urllib.request.Request("https://valorant-api.com/v1/maps", headers={"User-Agent": "valo-squad-tracker"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)["data"]
        maps = {}
        for mp in data:
            if mp.get("xMultiplier") is None or not mp.get("displayIcon"):
                continue
            maps[mp["uuid"]] = dict(
                name=mp["displayName"], icon=mp["displayIcon"],
                xm=mp["xMultiplier"], ym=mp["yMultiplier"], xa=mp["xScalarToAdd"], ya=mp["yScalarToAdd"],
                callouts=[[c.get("superRegionName"), c.get("regionName"), round(c["location"]["x"]), round(c["location"]["y"])]
                          for c in (mp.get("callouts") or []) if c.get("location")])
        if maps:
            MAPS_FILE.write_text(json.dumps(maps, ensure_ascii=False), encoding="utf-8")
            return maps
    except Exception as e:
        print(f"Kaartgegevens niet opgehaald ({e}), cache gebruikt.")
    return cache


BUY_MIN = 2000           # loadout vanaf ¤2.000 telt als "kopen" in de ronde na een verloren pistolronde
PISTOLS = {"Classic", "Shorty", "Frenzy", "Ghost", "Sheriff"}


def after_pistol(m):
    """Rondes direct na een verloren pistolronde (ronde 2 en 14): wie kocht, wie spaarde, en hoe liep het af."""
    players = m["players"]
    team_of = {p["puuid"]: p["team_id"] for p in players}
    rounds = m["rounds"]
    kills = m.get("kills") or []
    offset = 0 if (any(k["round"] == 0 for k in kills) or (rounds and rounds[0].get("id") == 0)) else 1
    out = {}
    for p in players:
        kk = key(p["name"], p["tag"])
        if kk not in FRIENDS:
            continue
        team, pu = p["team_id"], p["puuid"]
        for pistol in (0, 12):
            nxt = pistol + 1
            if len(rounds) <= nxt or rounds[pistol].get("winning_team") == team:
                continue
            r = rounds[nxt]
            eco = {s["player"]["puuid"]: s.get("economy") or {} for s in r.get("stats", [])}
            me = eco.get(pu, {})
            mates = [eco.get(q["puuid"], {}) for q in players if q["team_id"] == team and q["puuid"] != pu]
            mates_lv = sorted((e.get("loadout_value") or 0) for e in mates)
            mine = me.get("loadout_value") or 0
            weapon = (me.get("weapon") or {}).get("name")
            rk = [k for k in kills if k["round"] - offset == nxt]
            my_k = sum(1 for k in rk if k["killer"]["puuid"] == pu and team_of.get(k["victim"]["puuid"]) != team)
            team_k = sum(1 for k in rk if team_of.get(k["killer"]["puuid"]) == team and team_of.get(k["victim"]["puuid"]) != team)
            death = next((k for k in rk if k["victim"]["puuid"] == pu), None)
            nxt2 = rounds[nxt + 1] if len(rounds) > nxt + 1 else None
            out.setdefault(kk, []).append(dict(
                match=m["metadata"]["match_id"], date=m["metadata"]["started_at"],
                map=(m["metadata"].get("map") or {}).get("name"),
                mode=(m["metadata"].get("queue") or {}).get("name"),
                round=nxt + 1, weapon=weapon, armor=(me.get("armor") or {}).get("name"),
                loadout=mine, mates=mates_lv, mates_buy=sum(1 for v in mates_lv if v >= BUY_MIN),
                bought=mine >= BUY_MIN or (weapon and weapon not in PISTOLS),
                win=r.get("winning_team") == team, k=my_k, team_k=team_k,
                died=bool(death), death_t=round(death["time_in_round_in_ms"] / 1000) if death else None,
                next_win=(nxt2.get("winning_team") == team) if nxt2 else None,
            ))
    return out


def region_of(mp, x, y):
    """Dichtstbijzijnde callout: (superregio, naam)."""
    if not mp or x is None or not mp.get("callouts"):
        return None
    best = min(mp["callouts"], key=lambda c: (c[2] - x) ** 2 + (c[3] - y) ** 2)
    return best[0], best[1]


def team_behaviour(m, mp):
    """Per speler (alle 10): hoe vaak alleen, mee naar de site, trades. Voor vergelijking met de lobby."""
    players = m["players"]
    team_of = {p["puuid"]: p["team_id"] for p in players}
    rounds = m["rounds"]
    kills = m.get("kills") or []
    offset = 0 if (any(k["round"] == 0 for k in kills) or (rounds and rounds[0].get("id") == 0)) else 1
    by_round = defaultdict(list)
    for k in kills:
        by_round[k["round"] - offset].append(k)
    fha = first_half_attacker(m)
    out = {p["puuid"]: dict(iso_a=0, iso_t=0, site_w=0, site_a=0, site_d=0, trk=0, trd=0) for p in players}
    for i, r in enumerate(rounds):
        rk = sorted(by_round.get(i, []), key=lambda k: k["time_in_round_in_ms"])
        # alleen of bij het team, op elk moment dat iemand sterft
        for k in rk:
            locs = {q["player"]["puuid"]: q["location"] for q in k.get("player_locations", [])}
            for pu, loc in locs.items():
                mates = [l for q, l in locs.items() if q != pu and team_of.get(q) == team_of.get(pu)]
                if not mates or pu not in out:
                    continue
                out[pu]["iso_t"] += 1
                if min(dist(loc, l) for l in mates) > ALONE_UNITS:
                    out[pu]["iso_a"] += 1
        # trades
        for k in rk:
            v, kl, t = k["victim"]["puuid"], k["killer"]["puuid"], k["time_in_round_in_ms"]
            if team_of.get(v) == team_of.get(kl):
                continue
            for e in rk:
                if e["victim"]["puuid"] == kl and team_of.get(e["killer"]["puuid"]) == team_of.get(v) and 0 <= e["time_in_round_in_ms"] - t <= TRADE_MS:
                    if v in out:
                        out[v]["trd"] += 1
                    if e["killer"]["puuid"] in out:
                        out[e["killer"]["puuid"]]["trk"] += 1
                    break
        # mee naar de site: aanvallers op het moment van de plant
        pt = r.get("plant") or {}
        site, t_pl = pt.get("site"), pt.get("round_time_in_ms")
        if not site or t_pl is None or not mp:
            continue
        att = (pt.get("player") or {}).get("team")
        if not att:
            continue
        died_before = {k["victim"]["puuid"] for k in rk if k["time_in_round_in_ms"] <= t_pl}
        for p in players:
            pu = p["puuid"]
            if team_of[pu] != att:
                continue
            if pu in died_before:
                out[pu]["site_d"] += 1
                continue
            snap = None
            for k in rk:  # positie zo dicht mogelijk bij het plantmoment (max 15 s ervoor of erna)
                if abs(k["time_in_round_in_ms"] - t_pl) > 15000:
                    continue
                loc = next((q["location"] for q in k.get("player_locations", []) if q["player"]["puuid"] == pu), None)
                if loc and (snap is None or abs(k["time_in_round_in_ms"] - t_pl) < snap[0]):
                    snap = (abs(k["time_in_round_in_ms"] - t_pl), loc)
            if pu == (pt.get("player") or {}).get("puuid"):
                out[pu]["site_w"] += 1
                continue
            if not snap:
                continue
            reg = region_of(mp, snap[1]["x"], snap[1]["y"])
            if reg and reg[0] == site:
                out[pu]["site_w"] += 1
            else:
                out[pu]["site_a"] += 1
    return out


TIERS_FILE = ROOT / "data" / "tiers.json"
MMR_DIR = ROOT / "data" / "mmr"


def load_tiers():
    """Ranknamen, kleuren en iconen van valorant-api.com (nieuwste episode), met cache."""
    import urllib.request
    cache = json.loads(TIERS_FILE.read_text(encoding="utf-8")) if TIERS_FILE.exists() else {}
    try:
        req = urllib.request.Request("https://valorant-api.com/v1/competitivetiers", headers={"User-Agent": "valo-squad-tracker"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)["data"]
        latest = data[-1]
        tiers = {}
        for t in latest["tiers"]:
            if t.get("largeIcon") or t["tier"] == 0:
                tiers[str(t["tier"])] = dict(name=t["tierName"].title(), division=(t.get("divisionName") or "").title(),
                                             color="#" + (t.get("color") or "8696a7ff")[:6], icon=t.get("largeIcon") or t.get("smallIcon"))
        if tiers:
            TIERS_FILE.write_text(json.dumps(tiers, ensure_ascii=False), encoding="utf-8")
            return tiers
    except Exception as e:
        print(f"Rank-iconen niet opgehaald ({e}), cache gebruikt.")
    return cache


def slug_of(p):
    return "".join(c if c.isalnum() else "_" for c in f"{p['name']}_{p['tag']}".lower())


def load_mmr(per_player):
    out = {}
    for p in CONFIG["players"]:
        k = key(p["name"], p["tag"])
        f = MMR_DIR / f"{slug_of(p)}.json"
        if not f.exists():
            continue
        st = json.loads(f.read_text(encoding="utf-8"))
        rows = {r["match"]: r for r in per_player.get(k, [])}
        hist = []
        for mid, h in st.get("history", {}).items():
            r = rows.get(mid)
            hist.append(dict(
                match=mid, date=h.get("date"), tier=(h.get("tier") or {}).get("id"), tier_name=(h.get("tier") or {}).get("name"),
                rr=h.get("rr"), change=h.get("last_change"), elo=h.get("elo"), map=(h.get("map") or {}).get("name"),
                season=(h.get("season") or {}).get("short"), refunded=h.get("refunded_rr") or 0,
                protected=bool(h.get("was_derank_protected")), bonus=h.get("rr_performance_bonus"),
                afk=h.get("afk_penalty"), penalty=h.get("rr_penalty"), placement=h.get("is_placement_match"),
                movement=h.get("competitive_movement"), forgiven=h.get("new_map_incentive_rr_forgiven"),
                tier_before=(h.get("tier_before_update") or {}).get("id"), rr_before=h.get("rr_before_update"),
                agent=r["agent"] if r else None, result=r["result"] if r else None, score=r["score"] if r else None,
                k=r["k"] if r else None, d=r["d"] if r else None, a=r["a"] if r else None,
                acs=round(r["acs_sum"] / r["rounds"]) if r else None, with_=r.get("with") if r else None))
        hist.sort(key=lambda x: x["date"] or "")
        out[k] = dict(current=st.get("current"), current_at=st.get("current_at"), history=hist)
    return out


def short_weapon(w):
    n = (w or {}).get("name")
    return n or "Ability"


def detail(m, maps=None):
    """Compacte versie van één match voor het matchverslag op de site."""
    md = m["metadata"]
    players = m["players"]
    idx = {p["puuid"]: i for i, p in enumerate(players)}
    team_of = {p["puuid"]: p["team_id"] for p in players}
    rounds = m["rounds"]
    n = len(rounds) or 1
    kills = m.get("kills") or []
    offset = 0 if (any(k["round"] == 0 for k in kills) or (rounds and rounds[0].get("id") == 0)) else 1
    by_round = defaultdict(list)
    for k in kills:
        by_round[k["round"] - offset].append(k)
    friend_idx = [i for i, p in enumerate(players) if key(p["name"], p["tag"]) in FRIENDS]
    mp = (maps or {}).get((md.get("map") or {}).get("id")) or next((v for v in (maps or {}).values() if v.get("name") == (md.get("map") or {}).get("name")), None)
    tb = team_behaviour(m, mp)
    pl = []
    for p in players:
        st = p["stats"]
        shots = st["headshots"] + st["bodyshots"] + st["legshots"]
        kk = key(p["name"], p["tag"])
        pl.append(dict(n=p["name"], t=p["tag"], tm=p["team_id"], ag=(p.get("agent") or {}).get("name"),
                       fk=kk if kk in FRIENDS else None, tier=(p.get("tier") or {}).get("name"),
                       k=st["kills"], d=st["deaths"], a=st["assists"],
                       acs=round(st["score"] / n), adr=round(st["damage"]["dealt"] / n),
                       hs=round(100 * st["headshots"] / shots) if shots else 0,
                       ut=round(sum((p.get("ability_casts") or {}).get(k) or 0 for k in ("ability1", "ability2", "grenade")) / n, 2),
                       ult=(p.get("ability_casts") or {}).get("ultimate") or 0, **tb.get(p["puuid"], {})))
    rr = []
    for i, r in enumerate(rounds):
        ev = []
        for k in sorted(by_round.get(i, []), key=lambda k: k["time_in_round_in_ms"]):
            ki, vi = idx.get(k["killer"]["puuid"]), idx.get(k["victim"]["puuid"])
            if vi is None:
                continue
            alone = None
            if vi in friend_idx:
                loc = k.get("location")
                mates = [q for q in k.get("player_locations", [])
                         if q["player"]["puuid"] != k["victim"]["puuid"] and team_of.get(q["player"]["puuid"]) == team_of[k["victim"]["puuid"]]]
                if loc and mates:
                    alone = round(min(dist(loc, q["location"]) for q in mates))
            loc = k.get("location") or {}
            kpos = next((q["location"] for q in k.get("player_locations", []) if q["player"]["puuid"] == k["killer"]["puuid"]), None) or {}
            fpos = [[idx[q["player"]["puuid"]], round(q["location"]["x"]), round(q["location"]["y"])]
                    for q in k.get("player_locations", [])
                    if idx.get(q["player"]["puuid"]) in friend_idx and q["player"]["puuid"] != k["victim"]["puuid"]]
            ev.append([round(k["time_in_round_in_ms"] / 1000, 1), ki, vi, short_weapon(k.get("weapon")),
                       [idx[a["puuid"]] for a in k.get("assistants", []) if a["puuid"] in idx], alone,
                       loc.get("x"), loc.get("y"), kpos.get("x"), kpos.get("y"), fpos])
        eco = {}
        for stt in r.get("stats", []):
            pi = idx.get(stt["player"]["puuid"])
            if pi in friend_idx:
                e = stt.get("economy") or {}
                eco[pi] = [e.get("loadout_value") or 0, (e.get("weapon") or {}).get("name"),
                           (e.get("armor") or {}).get("name"), (stt.get("stats") or {}).get("headshots", 0)]
        pt = r.get("plant") or {}
        rr.append(dict(w=r.get("winning_team"), res=r.get("result"),
                       pl=pt.get("site"), plt=round(pt["round_time_in_ms"] / 1000) if pt.get("round_time_in_ms") else None,
                       plp=idx.get((pt.get("player") or {}).get("puuid")),
                       df=bool(r.get("defuse")), ev=ev, eco=eco))
    return dict(id=md["match_id"], date=md["started_at"], map=(md.get("map") or {}).get("name"),
                map_id=(md.get("map") or {}).get("id"),
                mode=(md.get("queue") or {}).get("name") or (md.get("queue") or {}).get("id"),
                season=(md.get("season") or {}).get("short"), fha=first_half_attacker(m),
                teams={t["team_id"]: [t["rounds"]["won"], t["rounds"]["lost"], bool(t.get("won"))] for t in m["teams"]},
                players=pl, rounds=rr)


def main():
    per_player = {k: [] for k in FRIENDS}
    shared = []
    details = {}
    pistol_loss = {k: [] for k in FRIENDS}
    files = sorted(MATCH_DIR.glob("*.json"))
    maps = load_maps()
    for f in files:
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
            rows = analyse(m)
        except Exception as e:
            print(f"Overgeslagen {f.name}: {e}")
            continue
        for k, r in rows.items():
            per_player[k].append(r)
        try:
            for k, evs in after_pistol(m).items():
                pistol_loss[k].extend(evs)
        except Exception as e:
            print(f"Pistolanalyse overgeslagen voor {f.name}: {e}")
        if rows:
            try:
                det = detail(m, maps)
                details[m["metadata"]["match_id"]] = det
                for q in det["players"]:
                    if q.get("fk") in rows:
                        for kk in ("iso_a", "iso_t", "site_w", "site_a", "site_d", "trk", "trd"):
                            rows[q["fk"]][kk] = q.get(kk, 0)
            except Exception as e:
                print(f"Geen matchverslag voor {f.name}: {e}")
        teams_of_friends = Counter(r_team for r_team in (
            next(p["team_id"] for p in m["players"] if key(p["name"], p["tag"]) == k) for k in rows))
        if teams_of_friends and teams_of_friends.most_common(1)[0][1] >= 2:
            shared.append(dict(match=m["metadata"]["match_id"], date=m["metadata"]["started_at"],
                               map=(m["metadata"].get("map") or {}).get("name"),
                               rows={k: r for k, r in rows.items()}))
    for lst in per_player.values():
        lst.sort(key=lambda r: r["date"], reverse=True)
    shared.sort(key=lambda s: s["date"], reverse=True)
    out = dict(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        players=[dict(key=key(p["name"], p["tag"]), name=p["name"], tag=p["tag"],
                      label=p.get("label", p["name"]), color=p.get("color", "#ff4655")) for p in CONFIG["players"]],
        matches=per_player, shared=shared, details=details, maps=maps, pistol_loss=pistol_loss, mmr=load_mmr(per_player), tiers=load_tiers(),
        settings=dict(trade_ms=TRADE_MS, early_s=EARLY_S, alone_units=ALONE_UNITS),
    )
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"stats.json geschreven: {len(files)} matches, {len(shared)} samen gespeeld.")


if __name__ == "__main__":
    main()
