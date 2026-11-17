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
            weapons={}, loadout_sum=0,
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


def short_weapon(w):
    n = (w or {}).get("name")
    return n or "Ability"


def detail(m):
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
    pl = []
    for p in players:
        st = p["stats"]
        shots = st["headshots"] + st["bodyshots"] + st["legshots"]
        kk = key(p["name"], p["tag"])
        pl.append(dict(n=p["name"], t=p["tag"], tm=p["team_id"], ag=(p.get("agent") or {}).get("name"),
                       fk=kk if kk in FRIENDS else None, tier=(p.get("tier") or {}).get("name"),
                       k=st["kills"], d=st["deaths"], a=st["assists"],
                       acs=round(st["score"] / n), adr=round(st["damage"]["dealt"] / n),
                       hs=round(100 * st["headshots"] / shots) if shots else 0))
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
            ev.append([round(k["time_in_round_in_ms"] / 1000, 1), ki, vi, short_weapon(k.get("weapon")),
                       [idx[a["puuid"]] for a in k.get("assistants", []) if a["puuid"] in idx], alone])
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
                mode=(md.get("queue") or {}).get("name") or (md.get("queue") or {}).get("id"),
                season=(md.get("season") or {}).get("short"), fha=first_half_attacker(m),
                teams={t["team_id"]: [t["rounds"]["won"], t["rounds"]["lost"], bool(t.get("won"))] for t in m["teams"]},
                players=pl, rounds=rr)


def main():
    per_player = {k: [] for k in FRIENDS}
    shared = []
    details = {}
    files = sorted(MATCH_DIR.glob("*.json"))
    for f in files:
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
            rows = analyse(m)
        except Exception as e:
            print(f"Overgeslagen {f.name}: {e}")
            continue
        for k, r in rows.items():
            per_player[k].append(r)
        if rows:
            try:
                details[m["metadata"]["match_id"]] = detail(m)
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
        matches=per_player, shared=shared, details=details,
        settings=dict(trade_ms=TRADE_MS, early_s=EARLY_S, alone_units=ALONE_UNITS),
    )
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"stats.json geschreven: {len(files)} matches, {len(shared)} samen gespeeld.")


if __name__ == "__main__":
    main()
