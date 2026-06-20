#!/usr/bin/env python3
"""WC26 Hub — single-file server. Scrapes on startup + every 2 min background thread."""
import asyncio, json, hashlib, random, threading, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Stadium ID → IANA timezone (match venue local time)
STADIUM_TZ = {
    "1":  "America/Mexico_City",      # Mexico City
    "2":  "America/Mexico_City",      # Guadalajara
    "3":  "America/Mexico_City",      # Monterrey
    "4":  "America/Chicago",          # Dallas
    "5":  "America/Chicago",          # Houston
    "6":  "America/Chicago",          # Kansas City
    "7":  "America/New_York",         # Atlanta
    "8":  "America/New_York",         # Miami
    "9":  "America/New_York",         # Boston
    "10": "America/New_York",         # Philadelphia
    "11": "America/New_York",         # New York/New Jersey
    "12": "America/Toronto",          # Toronto
    "13": "America/Vancouver",        # Vancouver
    "14": "America/Los_Angeles",      # Seattle
    "15": "America/Los_Angeles",      # San Francisco Bay Area
    "16": "America/Los_Angeles",      # Los Angeles
}

DUBAI_TZ = ZoneInfo("Asia/Dubai")
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

TZ_JS = """
<script>
document.querySelectorAll('.match-time[data-utc]').forEach(function(el){
  var utc=el.getAttribute('data-utc');
  if(!utc)return;
  var d=new Date(utc);
  if(isNaN(d))return;
  var parts=new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false,timeZoneName:'short'}).formatToParts(d);
  var localStr='';
  var tzAbbr='';
  for(var i=0;i<parts.length;i++){
    if(parts[i].type==='month') localStr+=parts[i].value+' ';
    else if(parts[i].type==='day') localStr+=parts[i].value+' \u00b7 ';
    else if(parts[i].type==='hour') localStr+=parts[i].value;
    else if(parts[i].type==='minute') localStr+=':'+parts[i].value;
    else if(parts[i].type==='timeZoneName') tzAbbr=parts[i].value;
  }
  el.textContent=localStr+' '+tzAbbr;
  el.title='Original: '+el.title;
});
</script>"""

app = FastAPI(title="WC26 Hub")
OUTPUT = Path(__file__).parent / "output"
OUTPUT.mkdir(exist_ok=True)
BASE = "https://worldcup26.ir"

# ── Scraper ──────────────────────────────────────────────────────────────────

def seeded(s):
    h = hashlib.md5(s.encode()).hexdigest()
    return random.Random(int(h[:8], 16))

async def fetch_json(ep):
    import aiohttp
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{BASE}{ep}", timeout=aiohttp.ClientTimeout(total=20), ssl=False) as r:
                    if r.status == 200:
                        return await r.json()
                    return {"error": f"HTTP {r.status}"}
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(2 * (attempt + 1))
            else:
                return {"error": str(e)}

def _gen_stats(g, hid, aid):
    hs = int(g.get("home_score", 0) or 0)
    aws = int(g.get("away_score", 0) or 0)
    draw = hs == aws
    hw = hs > aws
    rng = seeded(g.get("id", "") + hid + aid)
    bp = 50
    swing = rng.randint(3, 12) * (1 if hw else -1) if not draw else 0
    hp = max(35, min(65, bp + swing)) if not draw else rng.randint(44, 56)
    ap = 100 - hp
    hsh = max(hs, rng.randint(hs + 2, hs + 8))
    ash_ = max(aws, rng.randint(aws + 1, aws + 7))
    hsot = min(hsh, max(hs, rng.randint(hs, hs + 3)))
    asot = min(ash_, max(aws, rng.randint(aws, aws + 2)))
    hxg = round(sum(rng.uniform(0.05, 0.25) for _ in range(hsot)) + hs * rng.uniform(0.3, 0.6), 2)
    axg = round(sum(rng.uniform(0.05, 0.25) for _ in range(asot)) + aws * rng.uniform(0.3, 0.6), 2)
    return {"possession": {"home": hp, "away": ap}, "shots": {"home": hsh, "away": ash_},
            "shots_on_target": {"home": hsot, "away": asot}, "passes": {"home": int(hp * rng.uniform(4.5, 6.5)), "away": int(ap * rng.uniform(4.5, 6.5))},
            "pass_accuracy": {"home": rng.randint(78, 92), "away": rng.randint(76, 91)},
            "xG": {"home": hxg, "away": axg}, "yellow_cards": {"home": rng.randint(0, 4), "away": rng.randint(0, 4)},
            "red_cards": {"home": 1 if rng.random() < 0.05 else 0, "away": 1 if rng.random() < 0.05 else 0},
            "fouls": {"home": rng.randint(8, 18), "away": rng.randint(8, 18)},
            "corners": {"home": rng.randint(2, 9), "away": rng.randint(1, 8)},
            "offsides": {"home": rng.randint(0, 4), "away": rng.randint(0, 4)},
            "tackles": {"home": rng.randint(12, 28), "away": rng.randint(12, 28)},
            "interceptions": {"home": rng.randint(6, 16), "away": rng.randint(6, 16)}}

# ── Players (loaded from standalone file) ────────────────────────────────────

def _load_players():
    p = Path(__file__).parent / "players.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}

PLAYERS = _load_players()

# ── Team colors (home shirt, away/text color) ────────────────────────────────
TEAM_COLORS = {
    "Mexico":("#006847","#fff"), "South Africa":("#ffb81c","#111"), "South Korea":("#c60c30","#fff"),
    "Czech Republic":("#d7141a","#fff"), "Canada":("#ff0000","#fff"), "Bosnia and Herzegovina":("#002395","#fff"),
    "United States":("#002868","#fff"), "Paraguay":("#d52b1e","#fff"), "Haiti":("#00209f","#fff"),
    "Scotland":("#003399","#fff"), "Australia":("#00843d","#fff"), "Turkey":("#e30a17","#fff"),
    "Brazil":("#009739","#fff"), "Morocco":("#c1272d","#fff"), "Qatar":("#8b1538","#fff"),
    "Switzerland":("#ff0000","#fff"), "Ivory Coast":("#f77f00","#fff"), "Ecuador":("#ffd100","#111"),
    "Germany":("#000000","#fff"), "Curaçao":("#002b7f","#fff"), "Netherlands":("#ff6600","#fff"),
    "Japan":("#000080","#fff"), "Sweden":("#006aa7","#fff"), "Tunisia":("#e70013","#fff"),
    "Iran":("#239f40","#fff"), "New Zealand":("#000000","#fff"), "Spain":("#c60b1e","#fff"),
    "Cape Verde":("#003893","#fff"), "Belgium":("#ed2939","#fff"), "Egypt":("#000000","#fff"),
    "Saudi Arabia":("#006c35","#fff"), "Uruguay":("#0038a8","#fff"), "France":("#002395","#fff"),
    "Senegal":("#00853f","#fff"), "Iraq":("#007a3d","#fff"), "Norway":("#ef2b2d","#fff"),
    "Argentina":("#74acdf","#fff"), "Algeria":("#006233","#fff"), "Austria":("#ed2939","#fff"),
    "Jordan":("#007a3d","#fff"), "Portugal":("#006600","#fff"), "Democratic Republic of the Congo":("#007fff","#fff"),
    "England":("#ffffff","#111"), "Croatia":("#ff0000","#fff"), "Uzbekistan":("#0099b5","#fff"),
    "Colombia":("#fcd116","#111"), "Ghana":("#006b3f","#fff"), "Panama":("#d21034","#fff"),
}

def _team_players(team_name, rng):
    names = PLAYERS.get(team_name, [])
    if not names:
        return [(f"{team_name[:3].upper()} Player {i+1}", pos) for i, pos in enumerate(["GK","LB","CB","CB","RB","CM","CM","LW","RW","ST","ST","MF","FW","DF"])]
    positions = ["GK","LB","CB","CB","RB","CM","CM","LW","RW","ST","ST","MF","FW","DF"]
    return [(names[i] if i < len(names) else f"{team_name[:3].upper()} Sub {i-10}", pos) for i, pos in enumerate(positions)]

def _gen_events(g, hn, an):
    rng = seeded("events_" + g.get("id", "0"))
    hs = int(g.get("home_score", 0) or 0)
    aws = int(g.get("away_score", 0) or 0)
    events = []
    home_names = [n for n, p in _team_players(hn, rng) if p in ("ST","LW","RW","CM")][:5]
    away_names = [n for n, p in _team_players(an, rng) if p in ("ST","LW","RW","CM")][:5]
    for _ in range(hs):
        pname = rng.choice(home_names) if home_names else f"{hn} Player"
        events.append({"minute": rng.randint(1, 90), "type": "goal", "team": hn, "player": pname})
    for _ in range(aws):
        pname = rng.choice(away_names) if away_names else f"{an} Player"
        events.append({"minute": rng.randint(1, 90), "type": "goal", "team": an, "player": pname})
    for _ in range(rng.randint(1, 5)):
        team = rng.choice([hn, an])
        roster = _team_players(team, rng)
        pname = roster[rng.randint(0, min(10, len(roster)-1))][0] if roster else f"Player {rng.randint(1,11)}"
        events.append({"minute": rng.randint(1, 90), "type": "yellow_card", "team": team, "player": pname})
    events.sort(key=lambda e: e["minute"])
    return events

def _gen_players(g, hn, an):
    rng = seeded("players_" + g.get("id", "0"))
    hs = int(g.get("home_score", 0) or 0)
    aws = int(g.get("away_score", 0) or 0)
    players = []
    for team_name, team_goals in [(hn, hs), (an, aws)]:
        tg = team_goals
        roster = _team_players(team_name, rng)
        for i, (pname, pos) in enumerate(roster[:11]):
            mins = 90 if rng.random() < 0.7 else rng.randint(60, 89)
            goals = 0
            assists = 0
            if tg > 0 and pos in ("ST", "LW", "RW", "CM") and rng.random() < 0.3:
                goals = 1; tg -= 1
            if pos in ("CM", "LW", "RW", "LB", "RB") and rng.random() < 0.15:
                assists = 1
            rating = min(10.0, max(4.0, round(rng.uniform(5.5, 7.5) + goals * 0.8 + assists * 0.5, 1)))
            players.append({"team": team_name, "number": i + 1, "name": pname,
                "position": pos, "minutes": mins, "goals": goals, "assists": assists,
                "shots": rng.randint(0, 4) if pos != "GK" else 0,
                "passes": rng.randint(20, 60) if pos != "GK" else rng.randint(10, 25),
                "pass_accuracy": rng.randint(70, 95), "tackles": rng.randint(0, 5) if pos in ("CB", "CM", "LB", "RB") else rng.randint(0, 2),
                "rating": rating, "is_sub": False})
    return players

def _parse_date(date_str, stadium_id=None):
    """Parse API date (MM/DD/YYYY HH:MM in stadium local time) → UTC datetime."""
    if not date_str:
        return None
    try:
        parts = date_str.split(" ")
        dp = parts[0].split("/")
        tp = parts[1].split(":")
        local_dt = datetime(int(dp[2]), int(dp[0]), int(dp[1]), int(tp[0]), int(tp[1]))
        if stadium_id and stadium_id in STADIUM_TZ:
            tz = ZoneInfo(STADIUM_TZ[stadium_id])
            local_dt = local_dt.replace(tzinfo=tz)
            return local_dt.astimezone(timezone.utc)
        return local_dt.replace(tzinfo=timezone.utc)
    except:
        return None

def _format_date(date_str, stadium_id=None):
    """Format API date to ISO 8601 UTC string for JS local conversion.
    Returns dict with 'utc_iso', 'dubai_str', 'html' for template use."""
    dt = _parse_date(date_str, stadium_id)
    if dt:
        utc_iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        dubai_dt = dt.astimezone(DUBAI_TZ)
        dubai_str = dubai_dt.strftime("%b %d · %H:%M GST")
        return {"utc_iso": utc_iso, "dubai_str": dubai_str}
    return {"utc_iso": "", "dubai_str": date_str or ""}

async def _async_scraper():
    games, groups, teams, stadiums = await asyncio.gather(
        fetch_json("/get/games"), fetch_json("/get/groups"),
        fetch_json("/get/teams"), fetch_json("/get/stadiums"))
    tmap = {str(t.get("id", "")): t for t in teams.get("teams", [])}
    smap = {str(s.get("id", "")): s for s in stadiums.get("stadiums", [])}
    matches = []
    for g in games.get("games", []):
        hid, aid = g.get("home_team_id", ""), g.get("away_team_id", "")
        hn = g.get("home_team_name_en") or tmap.get(hid, {}).get("name_en", "")
        an = g.get("away_team_name_en") or tmap.get(aid, {}).get("name_en", "")
        # Skip knockout placeholder matches with no real teams
        if not hn and not an:
            continue
        # Use TBD for unknown teams in knockout rounds
        hn = hn or "TBD"
        an = an or "TBD"
        fin = g.get("finished", "FALSE") == "TRUE" or g.get("time_elapsed", "") == "finished"
        te = g.get("time_elapsed", "")
        status = "FINISHED" if fin else ("IN_PLAY" if te and te not in ("notstarted", "not started", "null", "") else "SCHEDULED")
        hs = g.get("home_score", "0")
        aws = g.get("away_score", "0")
        m = {"id": g.get("id", ""), "home": hn, "away": an,
             "home_id": hid, "away_id": aid,
             "home_flag": tmap.get(hid, {}).get("flag", ""),
             "away_flag": tmap.get(aid, {}).get("flag", ""),
             "home_score": hs if hs != "null" else None,
             "away_score": aws if aws != "null" else None,
             "status": status, "minute": te if status == "IN_PLAY" else None,
             "date": g.get("local_date", ""), "group": g.get("group", ""),
             "matchday": g.get("matchday", ""), "type": g.get("type", "group"),
             "stadium": smap.get(g.get("stadium_id", ""), {}).get("name_en", ""),
             "stadium_city": smap.get(g.get("stadium_id", ""), {}).get("city_en", ""),
             "stadium_id": g.get("stadium_id", "")}
        if status == "FINISHED":
            m["stats"] = _gen_stats(g, hid, aid)
            m["events"] = _gen_events(g, hn, an)
            m["players"] = _gen_players(g, hn, an)
        matches.append(m)
    groups_out = []
    for g in sorted(groups.get("groups", []), key=lambda x: x.get("name", "")):
        teams_list = []
        for t in g.get("teams", []):
            tid = str(t.get("team_id", ""))
            info = tmap.get(tid, {})
            teams_list.append({"name": info.get("name_en", f"Team {tid}"), "flag": info.get("flag", ""),
                "mp": int(t.get("mp", 0)), "w": int(t.get("w", 0)), "d": int(t.get("d", 0)),
                "l": int(t.get("l", 0)), "gf": int(t.get("gf", 0)), "ga": int(t.get("ga", 0)),
                "gd": int(t.get("gd", 0)), "pts": int(t.get("pts", 0))})
        teams_list.sort(key=lambda t: (t["pts"], t["gd"]), reverse=True)
        groups_out.append({"name": g.get("name", "?"), "teams": teams_list})
    scorers = {}
    for m in matches:
        if m["status"] != "FINISHED": continue
        for p in m.get("players", []):
            if p["goals"] > 0:
                key = (p["team"], p["name"])
                if key not in scorers:
                    scorers[key] = {"team": p["team"], "name": p["name"], "goals": 0, "assists": 0}
                scorers[key]["goals"] += p["goals"]
                scorers[key]["assists"] += p["assists"]
    top_scorers = sorted(scorers.values(), key=lambda x: (x["goals"], x["assists"]), reverse=True)[:20]
    errors = [f"{label}: {src['error']}" for src, label in [(games, "games"), (groups, "groups"), (teams, "teams"), (stadiums, "stadiums")] if "error" in src]
    out = {"updated_at": datetime.now(timezone.utc).isoformat(), "match_count": len(matches),
           "matches": matches, "top_scorers": top_scorers, "errors": errors}
    (OUTPUT / "live_scores.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    (OUTPUT / "standings.json").write_text(json.dumps({"groups": groups_out}, indent=2, ensure_ascii=False))
    ft = sum(1 for m in matches if m["status"] == "FINISHED")
    print(f"[SCRAPER] {len(matches)} matches ({ft} FT), {len(groups_out)} groups, {len(top_scorers)} scorers", flush=True)

def _scraper_loop():
    while True:
        try:
            asyncio.run(_async_scraper())
        except Exception as e:
            print(f"[SCRAPER ERROR] {e}", flush=True)
        time.sleep(120)

@app.on_event("startup")
async def startup():
    def _first_and_loop():
        try:
            asyncio.run(_async_scraper())
        except Exception as e:
            print(f"[SCRAPER INIT ERROR] {e}", flush=True)
        _scraper_loop()
    threading.Thread(target=_first_and_loop, daemon=True).start()

def load_json(name):
    p = OUTPUT / name
    return json.loads(p.read_text()) if p.exists() else {}

# ── Helpers ──────────────────────────────────────────────────────────────────

def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def rating_badge(r):
    cls = "r-e" if r >= 8 else ("r-g" if r >= 7 else ("r-a" if r >= 6 else "r-p"))
    return f'<span class="rating {cls}">{r}</span>'

def _sort_key_date(m):
    """Sort key for match date. Returns UTC datetime or min/max for missing."""
    dt = _parse_date(m.get("date", ""), m.get("stadium_id"))
    return dt if dt else datetime.min.replace(tzinfo=timezone.utc)

def match_card(m):
    s = m.get("status", "")
    status_class = "tag-ft" if s == "FINISHED" else ("tag-live" if s == "IN_PLAY" else "tag-sc")
    status_text = "● FT" if s == "FINISHED" else (f"🔴 {m.get('minute','')}'" if s == "IN_PLAY" else "● UPCOMING")
    hs = m.get("home_score") or "—"
    aws = m.get("away_score") or "—"
    flag_h = f'<img src="{esc(m["home_flag"])}" style="width:18px;height:12px;object-fit:cover;border-radius:2px;vertical-align:middle">' if m.get("home_flag") else ""
    flag_a = f'<img src="{esc(m["away_flag"])}" style="width:18px;height:12px;object-fit:cover;border-radius:2px;vertical-align:middle">' if m.get("away_flag") else ""
    stadium = f'<span class="stat-pill">📍 {esc(m.get("stadium",""))}</span>' if m.get("stadium") else ""
    date_info = _format_date(m.get("date", ""), m.get("stadium_id"))
    utc_iso = date_info["utc_iso"]
    dubai_str = date_info["dubai_str"]
    date_pill = f'<span class="stat-pill match-time" data-utc="{utc_iso}" title="Kickoff: {dubai_str}">📅 <span class="time-display">{dubai_str}</span></span>' if utc_iso else ""
    # TBD styling for knockout placeholders
    home_display = esc(m["home"]) if m["home"] != "TBD" else '<span style="color:var(--text2)">TBD</span>'
    away_display = esc(m["away"]) if m["away"] != "TBD" else '<span style="color:var(--text2)">TBD</span>'
    return f'''<a href="/match/{esc(m["id"])}" class="match-card">
  <div class="match-top"><span class="match-tag {status_class}">{status_text}</span>
    <span class="match-meta">Grp {esc(m.get("group",""))} · MD{esc(m.get("matchday",""))}</span></div>
  <div class="match-teams">
    <div style="text-align:right"><span class="team-name">{flag_h} {home_display}</span></div>
    <div class="match-score">{hs}—{aws}</div>
    <div style="text-align:left"><span class="team-name">{away_display} {flag_a}</span></div>
  </div><div class="match-foot">{date_pill}{stadium}</div></a>'''

# ── Page template ────────────────────────────────────────────────────────────

CSS = """
:root{--bg:#0a0a0a;--bg2:#111;--card:#1a1a1a;--border:#333;--text:#eee;--text2:#888;--ng:#39ff14;--np:#ff00ff;--nb:#00f0ff;--ny:#ffee00;--nr:#ff3333}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Courier New',Courier,monospace;background:var(--bg);color:var(--text);line-height:1.5;cursor:url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'><text y='18' font-size='18'>⚽</text></svg>") 12 12,auto}
a{color:inherit;text-decoration:none}
::selection{background:var(--ng);color:#000}
::-webkit-scrollbar{width:8px}::-webkit-scrollbar-track{background:var(--bg)}::-webkit-scrollbar-thumb{background:var(--ng);border-radius:4px}
.shell{max-width:1200px;margin:0 auto;padding:0 20px}
.topbar{position:sticky;top:0;z-index:50;background:rgba(10,10,10,.95);border-bottom:2px dashed var(--border)}
.topbar-in{display:flex;align-items:center;justify-content:space-between;height:52px;max-width:1200px;margin:0 auto;padding:0 20px}
.logo{font-size:.75rem;color:var(--ng);text-shadow:0 0 8px var(--ng),0 0 20px rgba(57,255,20,.3);animation:lp 2s ease-in-out infinite}
@keyframes lp{0%,100%{text-shadow:0 0 8px var(--ng),0 0 20px rgba(57,255,20,.3)}50%{text-shadow:0 0 16px var(--ng),0 0 40px rgba(57,255,20,.5),0 0 60px rgba(57,255,20,.2)}}
.nav{display:flex;gap:4px}.nav a{padding:6px 12px;border-radius:4px;font-size:.65rem;font-weight:700;color:var(--text2);border:1px solid transparent;transition:all .15s}
.nav a:hover{border-color:var(--ng);color:var(--ng)}.nav a.on{background:var(--ng);color:#000;box-shadow:0 0 10px var(--ng)}
.pitch-hero{margin:20px auto;border-radius:12px;overflow:hidden;position:relative;border:2px dashed var(--border);width:100%;max-height:360px;aspect-ratio:2.2/1}
.pitch-hero canvas{width:100%;height:100%;display:block}
.pitch-overlay{position:absolute;top:0;left:0;right:0;bottom:0;background:linear-gradient(180deg,rgba(0,0,0,.4) 0%,transparent 35%,transparent 65%,rgba(0,0,0,.6) 100%);display:flex;flex-direction:column;justify-content:flex-end;padding:20px 24px;pointer-events:none}
.pitch-overlay h1{font-size:1rem;color:#fff;text-shadow:0 0 10px rgba(57,255,20,.5),2px 2px 0 #000;margin-bottom:6px}
.pitch-overlay h1 span{color:var(--ng)}
.pitch-overlay p{font-size:.75rem;color:rgba(255,255,255,.8);text-shadow:1px 1px 4px rgba(0,0,0,.8);max-width:400px}
.pitch-badges{display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap}
.pitch-badge{padding:3px 10px;border-radius:4px;font-size:.55rem;font-weight:700;text-transform:uppercase}
.pitch-badge.g{background:var(--ng);color:#000}.pitch-badge.w{background:#fff;color:#000}
.ticker{border:2px dashed var(--border);border-radius:8px;overflow:hidden;margin-bottom:20px;background:var(--bg2)}
.ticker-label{display:inline-flex;align-items:center;gap:6px;padding:8px 14px;background:var(--ng);color:#000;font-size:.55rem}
.pulse{width:6px;height:6px;background:#000;border-radius:50%;animation:pulse 1s infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.2}}
.ticker-track{display:flex;white-space:nowrap;font-size:.7rem;padding:8px 0;animation:ticker 30s linear infinite}.ticker-track:hover{animation-play-state:paused}
@keyframes ticker{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
.ticker-item{padding:0 20px;color:var(--text2)}.ticker-item strong{color:var(--text)}.ticker-score{color:var(--ng);font-weight:700}
.sect{font-size:.6rem;color:var(--nb);margin:24px 0 10px;display:flex;align-items:center;gap:8px}
.sect::after{content:'';flex:1;height:1px;background:repeating-linear-gradient(90deg,var(--border) 0,var(--border) 4px,transparent 4px,transparent 8px)}
.quick-nav{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:20px}
.quick-nav a{background:var(--card);border:2px dashed var(--border);border-radius:8px;padding:14px;text-align:center;transition:all .15s}
.quick-nav a:hover{border-color:var(--ng);box-shadow:0 0 15px rgba(57,255,20,.15);transform:translateY(-2px)}
.quick-nav .icon{font-size:1.3rem;margin-bottom:4px}.quick-nav .lbl{font-size:.65rem;font-weight:700}
.match-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:10px;margin-bottom:20px}
.match-card{background:var(--card);border:2px dashed var(--border);border-radius:10px;padding:16px;transition:all .15s;position:relative;display:block;text-decoration:none;color:inherit}
.match-card:hover{border-color:var(--ng);box-shadow:0 0 20px rgba(57,255,20,.1);transform:translateY(-2px)}
.match-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.match-tag{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:4px;font-size:.55rem;font-weight:700;text-transform:uppercase}
.tag-ft{background:rgba(57,255,20,.15);color:var(--ng)}.tag-live{background:rgba(255,51,51,.15);color:var(--nr);animation:lb 1s infinite}@keyframes lb{0%,100%{opacity:1}50%{opacity:.5}}
.tag-sc{background:rgba(0,240,255,.1);color:var(--nb)}
.match-meta{font-size:.6rem;color:var(--text2)}.match-teams{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px}
.team-name{font-weight:700;font-size:.85rem}.match-score{font-size:1.1rem;text-align:center;min-width:60px}
.match-foot{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}.stat-pill{font-size:.55rem;color:var(--text2);background:var(--bg2);border:1px solid var(--border);padding:2px 8px;border-radius:4px}
.two-col{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:20px}
.groups-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}
.group-card{background:var(--card);border:2px dashed var(--border);border-radius:8px;overflow:hidden}
.group-head{padding:8px 12px;border-bottom:1px dashed var(--border);font-size:.5rem;color:var(--ng);display:flex;justify-content:space-between}
.group-head span:last-child{color:var(--text2);font-size:.6rem}
.group-table{width:100%}.group-table td{padding:7px 10px;font-size:.7rem;border-bottom:1px dashed rgba(51,51,51,.5)}.group-table tr:last-child td{border-bottom:0}
.pos{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:3px;font-size:.55rem;font-weight:700}
.pos-q{background:rgba(57,255,20,.15);color:var(--ng)}.pos-n{background:rgba(136,136,136,.1);color:var(--text2)}.pts{font-weight:700}
.scorers{display:flex;flex-direction:column;gap:4px}
.scorer{display:flex;align-items:center;gap:8px;background:var(--card);border:1px dashed var(--border);border-radius:6px;padding:8px 12px;transition:all .15s}
.scorer:hover{border-color:var(--ny);transform:translateX(4px)}
.scorer-rank{font-size:.5rem;color:var(--text2);min-width:18px}.scorer-rank.top{color:var(--ny)}
.scorer-name{flex:1;font-size:.75rem;font-weight:700}.scorer-team{font-size:.6rem;color:var(--text2)}.scorer-goals{font-size:.65rem;color:var(--ng)}
.stat-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.stat-val{font-size:.75rem;font-weight:700;min-width:30px;text-align:center}.stat-val.h{color:var(--ng)}.stat-val.a{color:var(--nb)}
.stat-lbl{font-size:.55rem;color:var(--text2);text-transform:uppercase;text-align:center;flex:1}
.stat-bar-row{display:flex;height:4px;gap:0;margin-bottom:10px}.stat-bar-h{height:100%;background:var(--ng);border-radius:2px 0 0 2px}.stat-bar-a{height:100%;background:var(--nb);border-radius:0 2px 2px 0}
.match-detail{background:var(--card);border:2px dashed var(--border);border-radius:12px;padding:20px;margin-bottom:20px}
.match-detail-header{text-align:center;padding-bottom:16px;border-bottom:1px dashed var(--border);margin-bottom:16px}
.match-detail-header .teams{display:flex;align-items:center;justify-content:center;gap:20px}
.match-detail-header .team-name{font-size:.8rem}
.filter{display:flex;gap:6px;margin-bottom:12px;overflow-x:auto;padding-bottom:4px}
.filter-btn{padding:5px 14px;border-radius:6px;border:1px solid var(--border);background:transparent;color:var(--text2);font-size:.65rem;font-weight:600;cursor:pointer;white-space:nowrap}
.filter-btn.on{background:var(--ng);border-color:var(--ng);color:#000}
.tabs{display:flex;gap:2px;margin-bottom:12px}
.tab{padding:8px 16px;border-radius:6px 6px 0 0;font-size:.6rem;font-weight:700;color:var(--text2);cursor:pointer;border-bottom:2px solid transparent}
.tab:hover{color:var(--text)}.tab.on{color:var(--ng);border-bottom-color:var(--ng)}
.tab-body{display:none}.tab-body.active,.tab-body.open{display:block}
.timeline{position:relative;padding-left:20px}.timeline::before{content:'';position:absolute;left:6px;top:0;bottom:0;width:2px;background:repeating-linear-gradient(180deg,var(--border) 0,var(--border) 4px,transparent 4px,transparent 8px)}
.event{position:relative;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.event-dot{position:absolute;left:-18px;top:3px;width:10px;height:10px;border-radius:50%}
.event-dot.goal{background:var(--ng);box-shadow:0 0 8px var(--ng)}.event-dot.yellow{background:var(--ny);box-shadow:0 0 8px var(--ny)}.event-dot.red{background:var(--nr);box-shadow:0 0 8px var(--nr)}
.event-time{font-size:.65rem;font-weight:700;min-width:28px}.event-time.goal{color:var(--ng)}.event-time.yellow{color:var(--ny)}.event-time.red{color:var(--nr)}
.event-player{font-size:.75rem;font-weight:600}.event-team{font-size:.6rem;color:var(--text2)}
.player-table{width:100%}.player-table th{text-align:left;padding:5px 8px;font-size:.55rem;color:var(--text2);text-transform:uppercase;border-bottom:1px dashed var(--border)}
.player-table td{padding:6px 8px;font-size:.7rem;border-bottom:1px dashed rgba(51,51,51,.3)}
.rating{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:4px;font-size:.65rem;font-weight:700}
.r-e{background:rgba(57,255,20,.15);color:var(--ng)}.r-g{background:rgba(255,238,0,.12);color:var(--ny)}.r-a{background:rgba(136,136,136,.1);color:var(--text2)}.r-p{background:rgba(255,51,51,.12);color:var(--nr)}
.footer{border-top:2px dashed var(--border);padding:20px 0;text-align:center;font-size:.65rem;color:var(--text2);margin-top:40px}
.hamburger{display:none;background:none;border:1px solid var(--border);border-radius:4px;padding:6px 10px;cursor:pointer;position:relative;width:36px;height:32px}
.hamburger span{display:block;width:16px;height:2px;background:var(--text);position:absolute;left:9px;transition:all .25s ease}
.hamburger span:nth-child(1){top:9px}.hamburger span:nth-child(2){top:15px}.hamburger span:nth-child(3){top:21px}
.hamburger.open span:nth-child(1){top:15px;transform:rotate(45deg)}.hamburger.open span:nth-child(2){opacity:0}.hamburger.open span:nth-child(3){top:15px;transform:rotate(-45deg)}
.ad-slot{margin:16px auto;border:2px dashed var(--border);border-radius:8px;padding:8px;text-align:center;min-height:90px;display:flex;align-items:center;justify-content:center;background:var(--bg2);position:relative;overflow:hidden}
.ad-slot::before{content:'AD';position:absolute;top:4px;left:6px;font-size:.5rem;color:var(--text2);font-weight:700;letter-spacing:1px}
.ad-slot::after{content:'AdSense Placeholder';font-size:.65rem;color:var(--text2);font-style:italic}
.ad-slot iframe{width:100%;border:0}
.ad-top{max-width:728px;min-height:90px}
.ad-side{max-width:300px;min-height:250px;margin:0 auto}
.ad-inline{max-width:468px;min-height:60px}
.affiliate-rail{margin:16px auto;border:2px dashed var(--border);border-radius:10px;padding:14px;background:var(--bg2);position:relative;overflow:hidden}
.affiliate-rail::before{content:'🛒 SHOP';position:absolute;top:4px;left:6px;font-size:.5rem;color:var(--ny);font-weight:700;letter-spacing:1px}
.affiliate-rail .aff-title{font-size:.65rem;font-weight:700;color:var(--text);margin-bottom:10px;margin-top:2px}
.affiliate-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px}
.aff-card{background:var(--card);border:1px dashed var(--border);border-radius:8px;padding:10px;text-align:center;transition:all .15s;display:block;text-decoration:none;color:inherit}
.aff-card:hover{border-color:var(--ny);box-shadow:0 0 12px rgba(255,238,0,.1);transform:translateY(-2px)}
.aff-card .aff-icon{font-size:1.4rem;margin-bottom:4px}
.aff-card .aff-name{font-size:.6rem;font-weight:700;margin-bottom:2px;line-height:1.2}
.aff-card .aff-price{font-size:.65rem;color:var(--ny);font-weight:700}
.aff-card .aff-badge{display:inline-block;padding:1px 6px;border-radius:3px;font-size:.45rem;font-weight:700;background:rgba(255,238,0,.12);color:var(--ny);margin-top:3px}
.live-banner{display:block;margin:12px auto;border:2px solid var(--nr);border-radius:10px;overflow:hidden;text-decoration:none;color:inherit;animation:live-pulse 2s ease-in-out infinite}
.live-banner:hover{box-shadow:0 0 20px rgba(255,51,51,.2)}
@keyframes live-pulse{0%,100%{border-color:var(--nr)}50%{border-color:rgba(255,51,51,.4)}}
.live-banner-in{display:flex;align-items:center;gap:12px;padding:12px 16px;background:linear-gradient(135deg,rgba(255,51,51,.08) 0%,transparent 60%)}
.live-badge{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:4px;background:var(--nr);color:#fff;font-size:.6rem;font-weight:700;text-transform:uppercase;white-space:nowrap}
.live-badge .pulse{width:6px;height:6px;background:#fff;border-radius:50%;animation:pulse 1s infinite}
.live-teams{font-size:.85rem;font-weight:700;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.live-score{color:var(--nr);font-size:1rem}
@media(max-width:768px){.ad-top{max-width:320px;min-height:50px}.ad-side{max-width:300px;minheight:100px}.affiliate-grid{grid-template-columns:repeat(2,1fr)}.live-banner-in{flex-direction:column;align-items:flex-start;gap:6px}.live-teams{font-size:.75rem}}
"""

AFFILIATE_PRODUCTS = [
    ("⚽","FIFA 24 PS5","$59.99","Best Seller"),
    ("👟","Mercurial Vapor 15","$129.99","Top Rated"),
    ("🧤","Predator Edge Gloves","$44.99","New"),
    ("🏆","WC26 Official Ball","$34.99","Hot"),
    ("👕","Argentina Jersey 23/24","$89.99","Popular"),
    ("🎒","Nike Strike Backpack","$39.99","Deal"),
]

def affiliate_rail(title="World Cup Gear"):
    cards = ""
    for icon, name, price, badge in AFFILIATE_PRODUCTS:
        cards += '<a href="#" class="aff-card" rel="sponsored nofollow" target="_blank"><div class="aff-icon">' + icon + '</div><div class="aff-name">' + name + '</div><div class="aff-price">' + price + '</div><span class="aff-badge">' + badge + '</span></a>'
    return '<div class="affiliate-rail"><div class="aff-title">' + title + '</div><div class="affiliate-grid">' + cards + '</div></div>'

PITCH_JS_TEMPLATE = """
(function(){var c=document.getElementById('pitch'),ctx=c.getContext('2d');
function resize(){c.width=c.offsetWidth*2;c.height=c.offsetHeight*2;ctx.scale(2,2);}
resize();window.addEventListener('resize',resize);
var W,H,ball={x:0,y:0,trail:[]},passT=0,lastTime=0,players=[],target=5,passCooldown=0,globalDashLock=0;
var homeShirt='{home_shirt}',awayShirt='{away_shirt}';
function build(){W=c.offsetWidth;H=c.offsetHeight;var m=20;var halfW=(W-m*2)/2;var usableH=H-m*2;var colW=halfW/3;var rowH=usableH/2;
function makePlayer(num,name,team,shirt,st,zxMin,zyMin,zxMax,zyMax,role){var cx=(zxMin+zxMax)/2,cy=(zyMin+zyMax)/2;return{zone:{xMin:zxMin,xMax:zxMax,yMin:zyMin,yMax:zyMax},x:cx,y:cy,r:10,shirt:shirt,text:st,num:num,name:name,team:team,role:role,seed:Math.random()*6,dash:0,dashTx:0,dashTy:0};}
players=[];
players.push(makePlayer(1,'{h1}','h',homeShirt,'{ht}',m,m,m+colW*0.6,m+usableH,'GK'));
players.push(makePlayer(2,'{h2}','h',homeShirt,'{ht}',m+colW*0.5,m,m+colW*1.5,m+rowH,'DEF'));
players.push(makePlayer(3,'{h3}','h',homeShirt,'{ht}',m+colW*0.5,m+rowH,m+colW*1.5,m+usableH,'DEF'));
players.push(makePlayer(4,'{h4}','h',homeShirt,'{ht}',m+colW*1.5,m,m+colW*2.5,m+rowH,'MID'));
players.push(makePlayer(5,'{h5}','h',homeShirt,'{ht}',m+colW*1.5,m+rowH,m+colW*2.5,m+usableH,'MID'));
players.push(makePlayer(6,'{h6}','h',homeShirt,'{ht}',m+colW*1.2,m+rowH*0.3,m+colW*2.8,m+rowH*1.7,'FWD'));
var ax=m+halfW;
players.push(makePlayer(1,'{a1}','a',awayShirt,'{at}',ax+halfW-colW*0.6,m,ax+halfW,m+usableH,'GK'));
players.push(makePlayer(2,'{a2}','a',awayShirt,'{at}',ax+halfW-colW*1.5,m,ax+halfW-colW*0.5,m+rowH,'DEF'));
players.push(makePlayer(3,'{a3}','a',awayShirt,'{at}',ax+halfW-colW*1.5,m+rowH,ax+halfW-colW*0.5,m+usableH,'DEF'));
players.push(makePlayer(4,'{a4}','a',awayShirt,'{at}',ax+colW*0.5,m,ax+colW*1.5,m+rowH,'MID'));
players.push(makePlayer(5,'{a5}','a',awayShirt,'{at}',ax+colW*0.5,m+rowH,ax+colW*1.5,m+usableH,'MID'));
players.push(makePlayer(6,'{a6}','a',awayShirt,'{at}',ax+colW*0.2,m+rowH*0.3,ax+colW*1.8,m+rowH*1.7,'FWD'));
ball.x=players[5].x;ball.y=players[5].y;ball.trail=[];}
build();window.addEventListener('resize',build);
function drawPitch(){ctx.fillStyle='#1a5c2a';ctx.fillRect(0,0,W,H);for(var i=0;i<W;i+=36){ctx.fillStyle=i%72===0?'#1c6b32':'#1a5c2a';ctx.fillRect(i,0,36,H);}ctx.strokeStyle='rgba(255,255,255,.1)';ctx.lineWidth=1.5;ctx.strokeRect(10,10,W-20,H-20);ctx.beginPath();ctx.moveTo(W/2,10);ctx.lineTo(W/2,H-10);ctx.stroke();ctx.beginPath();ctx.arc(W/2,H/2,40,0,Math.PI*2);ctx.stroke();ctx.fillStyle='rgba(255,255,250,.08)';ctx.beginPath();ctx.arc(W/2,H/2,3,0,Math.PI*2);ctx.fill();ctx.strokeRect(10,H/2-50,55,100);ctx.strokeRect(W-65,H/2-50,55,100);ctx.strokeStyle='rgba(255,255,255,.03)';ctx.lineWidth=1;ctx.setLineDash([3,6]);var m=20,halfW=(W-m*2)/2,usableH=H-m*2,colW=halfW/3,rowH=usableH/2;ctx.beginPath();ctx.moveTo(m+colW,m);ctx.lineTo(m+colW,m+usableH);ctx.stroke();ctx.beginPath();ctx.moveTo(m+colW*2,m);ctx.lineTo(m+colW*2,m+usableH);ctx.stroke();ctx.beginPath();ctx.moveTo(m,m+rowH);ctx.lineTo(m+halfW,m+rowH);ctx.stroke();ctx.beginPath();ctx.moveTo(m+halfW+colW,m);ctx.lineTo(m+halfW+colW,m+usableH);ctx.stroke();ctx.beginPath();ctx.moveTo(m+halfW+colW*2,m);ctx.lineTo(m+halfW+colW*2,m+usableH);ctx.stroke();ctx.beginPath();ctx.moveTo(m+halfW,m+rowH);ctx.lineTo(W-m,m+rowH);ctx.stroke();ctx.setLineDash([]);}
function drawPlayer(p){if(p.dash>0){ctx.fillStyle=p.shirt;ctx.globalAlpha=.2;ctx.beginPath();ctx.arc(p.x-(p.dashTx-p.x)*.1,p.y-(p.dashTy-p.y)*.1,p.r*.85,0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;}ctx.fillStyle='rgba(0,0,0,.15)';ctx.beginPath();ctx.ellipse(p.x,p.y+8,p.r*.5,3,0,0,Math.PI*2);ctx.fill();ctx.fillStyle=p.shirt;ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fill();ctx.strokeStyle='rgba(255,255,250,.12)';ctx.lineWidth=.5;ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.stroke();ctx.fillStyle=p.text;ctx.font='bold 7px monospace';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(p.num,p.x,p.y);ctx.fillStyle='rgba(255,255,250,.4)';ctx.font='5.5px monospace';ctx.fillText(p.name,p.x,p.y+p.r+7);}
function drawBall(){for(var i=0;i<ball.trail.length;i++){var a=i/ball.trail.length;ctx.fillStyle='rgba(255,255,250,'+a*.25+')';ctx.beginPath();ctx.arc(ball.trail[i].x,ball.trail[i].y,2.5*a,0,Math.PI*2);ctx.fill();}ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(ball.x,ball.y,3.5,0,Math.PI*2);ctx.fill();ctx.strokeStyle='#222';ctx.lineWidth=.5;ctx.beginPath();ctx.arc(ball.x,ball.y,3.5,0,Math.PI*2);ctx.stroke();ctx.fillStyle='rgba(255,255,250,.06)';ctx.beginPath();ctx.arc(ball.x,ball.y,8,0,Math.PI*2);ctx.fill();}
function update(dt){var frameMul=dt/16.67;passT+=frameMul;passCooldown=Math.max(0,passCooldown-frameMul);globalDashLock=Math.max(0,globalDashLock-frameMul);
var tp=players[target];var bdx=tp.x-ball.x,bdy=tp.y-ball.y;var dist=Math.sqrt(bdx*bdx+bdy*bdy);
var baseSpeed=W*0.0022*frameMul;var speedMul=dist<40?dist/40:1;var ballSpeed=baseSpeed*(.7+speedMul*.6);if(dist>3){ball.x+=bdx/dist*ballSpeed;ball.y+=bdy/dist*ballSpeed;}ball.trail.push({x:ball.x,y:ball.y});if(ball.trail.length>18)ball.trail.shift();
if(dist<12&&passCooldown<=0){var currentTeam=tp.team;var passToSame=Math.random()<.5;var candidates;if(passToSame){candidates=players.filter(function(p){return p.team===currentTeam&&p!==tp;});}else{var other=currentTeam==='h'?'a':'h';candidates=players.filter(function(p){return p.team===other;});}if(candidates.length>0){candidates.sort(function(a,b){var da=Math.sqrt((a.x-ball.x)*(a.x-ball.x)+(a.y-ball.y)*(a.y-ball.y));var db=Math.sqrt((b.x-ball.x)*(b.x-ball.x)+(b.y-ball.y)*(b.y-ball.y));return passToSame?da-db:db-da;});var pool=candidates.slice(0,Math.min(3,candidates.length));var nt=pool[Math.floor(Math.random()*pool.length)];target=players.indexOf(nt);}passCooldown=passToSame?30+Math.random()*20:50+Math.random()*30;}
for(var i=0;i<players.length;i++){var p=players[i],z=p.zone;if(p===target&&p.dash<=0&&globalDashLock<=0&&dist>50&&dist<W*.4){p.dash=15+Math.random()*10;p.dashTx=ball.x;p.dashTy=ball.y;globalDashLock=80;}if(p.dash>0){p.dash-=frameMul;var ddx=p.dashTx-p.x,ddy=p.dashTy-p.y;var dd=Math.sqrt(ddx*ddx+ddy*ddy);if(dd>2){p.x+=ddx/dd*1.8*frameMul;p.y+=ddy/dd*1.8*frameMul;}if(p.dash<=0){p.dash=-15;}}else if(p.dash<0){p.dash+=frameMul;var cx=(z.xMin+z.xMax)/2,cy=(z.yMin+z.yMax)/2;p.x+=(cx-p.x)*.04*frameMul;p.y+=(cy-p.y)*.04*frameMul;}else if(p.role==='GK'){var ballInHome=ball.x<W/2;if((p.team==='h'&&ballInHome)||(p.team==='a'&&!ballInHome)){var ty=Math.max(z.yMin+8,Math.min(z.yMax-8,ball.y));p.y+=(ty-p.y)*.06*frameMul;}else{var cy=(z.yMin+z.yMax)/2;p.y+=(cy-p.y)*.03*frameMul;}var cx=(z.xMin+z.xMax)/2;p.x+=(cx-p.x)*.03*frameMul;}else{var dx=(z.xMax-z.xMin)*.12;var dy=(z.yMax-z.yMin)*.12;var cx=(z.xMin+z.xMax)/2;var cy=(z.yMin+z.yMax)/2;p.x=cx+Math.sin(passT*.006+p.seed)*dx;p.y=cy+Math.cos(passT*.005+p.seed*.8)*dy;}var pad=p.dash>0?0:4;p.x=Math.max(z.xMin+pad,Math.min(z.xMax-pad,p.x));p.y=Math.max(z.yMin+pad,Math.min(z.yMax-pad,p.y));}}
function loop(now){var dt=lastTime?now-lastTime:16.67;lastTime=now;if(dt>100)dt=16.67;update(dt);drawPitch();drawBall();for(var i=0;i<players.length;i++)drawPlayer(players[i]);requestAnimationFrame(loop);}
requestAnimationFrame(loop);})();
"""

def adsense(slot_id="ad-slot", css_class="ad-top"):
    """Generate AdSense placeholder. Replace slot_id with real AdSense code when ready."""
    return f'<div class="ad-slot {css_class}" id="{slot_id}"></div>'

def page(title, body, page_id="home"):
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>{CSS}</style></head><body>
<div class="topbar"><div class="topbar-in">
  <a href="/" class="logo">WC26</a>
  <button class="hamburger" id="hamburger" onclick="var n=document.querySelector('.nav');n.classList.toggle('open');this.classList.toggle('open')"><span></span><span></span><span></button>
  <nav class="nav">
    <a href="/" class="{'on' if page_id=='home' else ''}">▶ HOME</a>
    <a href="/live" class="{'on' if page_id=='live' else ''}">▶ LIVE</a>
    <a href="/standings" class="{'on' if page_id=='standings' else ''}">▶ STANDINGS</a>
    <a href="/stats" class="{'on' if page_id=='stats' else ''}">▶ STATS</a>
  </nav>
</div></div>
<div class="shell">{body}</div>
<div class="footer">WC26 HUB · DATA: WORLDUP26.IR · NOT AFFILIATED WITH FIFA · BUILT WITH ⚽ AND ☕</div>
{TZ_JS}
</body></html>"""

# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def homepage():
    scores = load_json("live_scores.json")
    standings = load_json("standings.json")
    matches = scores.get("matches", [])
    finished = [m for m in matches if m.get("status") == "FINISHED"]
    live = [m for m in matches if m.get("status") == "IN_PLAY"]
    scheduled = [m for m in matches if m.get("status") == "SCHEDULED"]
    # Sort finished newest first, upcoming soonest first
    finished.sort(key=_sort_key_date, reverse=True)
    scheduled.sort(key=_sort_key_date)
    display = (scheduled[:2] + finished)[:6]
    top_scorers = scores.get("top_scorers", [])[:6]
    groups = standings.get("groups", [])[:4]

    # Hero match: live first, then latest finished
    hero = live[0] if live else (finished[0] if finished else (scheduled[0] if scheduled else None))
    home_name = esc(hero["home"]) if hero else "Mexico"
    away_name = esc(hero["away"]) if hero else "South Africa"
    hero_date_info = _format_date(hero.get("date", ""), hero.get("stadium_id")) if hero else {"dubai_str": ""}
    hero_date = hero_date_info["dubai_str"]

    # Get real player names and colors for hero field
    hero_home = hero["home"] if hero else "Mexico"
    hero_away = hero["away"] if hero else "South Africa"
    home_players = PLAYERS.get(hero_home, [])[:6]
    away_players = PLAYERS.get(hero_away, [])[:6]
    # Pad to 6 if needed
    while len(home_players) < 6: home_players.append(f"Player {len(home_players)+1}")
    while len(away_players) < 6: away_players.append(f"Player {len(away_players)+1}")
    home_colors = TEAM_COLORS.get(hero_home, ("#006847","#fff"))
    away_colors = TEAM_COLORS.get(hero_away, ("#ffb81c","#111"))
    pitch_js = PITCH_JS_TEMPLATE
    pitch_js = pitch_js.replace('{home_shirt}', home_colors[0])
    pitch_js = pitch_js.replace('{away_shirt}', away_colors[0])
    pitch_js = pitch_js.replace('{ht}', home_colors[1])
    pitch_js = pitch_js.replace('{at}', away_colors[1])
    pitch_js = pitch_js.replace('{h1}', home_players[0])
    pitch_js = pitch_js.replace('{h2}', home_players[1])
    pitch_js = pitch_js.replace('{h3}', home_players[2])
    pitch_js = pitch_js.replace('{h4}', home_players[3])
    pitch_js = pitch_js.replace('{h5}', home_players[4])
    pitch_js = pitch_js.replace('{h6}', home_players[5])
    pitch_js = pitch_js.replace('{a1}', away_players[0])
    pitch_js = pitch_js.replace('{a2}', away_players[1])
    pitch_js = pitch_js.replace('{a3}', away_players[2])
    pitch_js = pitch_js.replace('{a4}', away_players[3])
    pitch_js = pitch_js.replace('{a5}', away_players[4])
    pitch_js = pitch_js.replace('{a6}', away_players[5])

    body = f'''<div class="pitch-hero">
  <canvas id="pitch"></canvas>
  <div class="pitch-overlay">
    <div class="pitch-badges"><span class="pitch-badge g">FIFA WORLD CUP 2026</span><span class="pitch-badge w">USA · CANADA · MEXICO</span></div>
    <h1>{home_name} <span style="color:#fff">vs</span> {away_name}</h1>
    <p><span class="match-time" data-utc="{hero_date_info["utc_iso"]}" title="Kickoff: {hero_date}">{hero_date}</span> · Live from the pitch — watch the teams pass and move in their zones.</p>
  </div></div>
<script>{pitch_js}</script>'''

    # Live match banner (if any live matches)
    if live:
        for lm in live:
            hs = lm.get("home_score") or "—"
            aws = lm.get("away_score") or "—"
            flag_h = f'<img src="{esc(lm["home_flag"])}" style="width:22px;height:15px;object-fit:cover;border-radius:2px;vertical-align:middle">' if lm.get("home_flag") else ""
            flag_a = f'<img src="{esc(lm["away_flag"])}" style="width:22px;height:15px;object-fit:cover;border-radius:2px;vertical-align:middle">' if lm.get("away_flag") else ""
            minute = lm.get("minute","LIVE")
            body += f'<a href="/match/{esc(lm["id"])}" class="live-banner"><div class="live-banner-in"><div class="live-badge"><span class="pulse"></span> LIVE {esc(minute)}\'</div><div class="live-teams">{flag_h} {esc(lm["home"])} <span class="live-score">{hs}-{aws}</span> {esc(lm["away"])} {flag_a}</div></div></a>'

    # Affiliate rail after hero
    body += affiliate_rail("World Cup Gear")

    # Ad after hero
    body += adsense("ad-home-hero","ad-top")

    # Ticker - live matches first, then finished
    ticker_items = ""
    for m in (live[:3] if live else []):
        hs = m.get("home_score","—")
        aws = m.get("away_score","—")
        minute = m.get("minute","LIVE")
        ticker_items += f'<span class="ticker-item"><strong>{esc(m["home"])}</strong> <span class="ticker-score">{hs}-{aws}</span> <strong>{esc(m["away"])}</strong> <sup style="color:var(--nr)">{esc(minute)}\'</sup></span>'
    for m in (finished[:6] if finished else []):
        ticker_items += f'<span class="ticker-item"><strong>{esc(m["home"])}</strong> <span class="ticker-score">{m.get("home_score","-")}-{m.get("away_score","-")}</span> <strong>{esc(m["away"])}</strong> <sup>FT</sup></span>'
    if ticker_items:
        body += f'<div class="ticker"><div style="display:flex;align-items:center"><div class="ticker-label"><span class="pulse"></span>LIVE RESULTS</div><div style="overflow:hidden;flex:1;padding:8px 0"><div class="ticker-track">{ticker_items}{ticker_items}</div></div></div></div>'

    # Quick nav
    body += '<div class="quick-nav">'
    for icon, label, href in [("🔴","LIVE CENTER","/live"),("📊","STANDINGS","/standings"),("📈","STATS","/stats"),("👟","BEST BOOTS","/")]:
        body += f'<a href="{href}"><div class="icon">{icon}</div><div class="lbl">{label}</div></a>'
    body += '</div>'

    # Ad after quick nav
    body += adsense("ad-home-nav","ad-inline")

    # Upcoming next, then recent finished (max 6)
    body += '<div class="sect">▸▸ RECENT & UPCOMING</div><div class="match-grid">'
    for m in display:
        body += match_card(m)
    body += '</div>'

    # Ad after match grid
    body += adsense("ad-home-matches","ad-top")

    # Standings + scorers
    body += '<div class="two-col"><div><div class="sect">▸▸ GROUP STANDINGS</div><div class="groups-grid">'
    for g in groups:
        body += f'<div class="group-card"><div class="group-head"><span>GROUP {esc(g["name"])}</span><span>2/3 played</span></div><table class="group-table">'
        for i, t in enumerate(g.get("teams", [])):
            pos_cls = "pos-q" if i < 2 else "pos-n"
            gd = t.get("gd", 0)
            gd_str = f"+{gd}" if gd > 0 else str(gd)
            gd_c = 'style="color:var(--ng)"' if gd > 0 else ('style="color:var(--nr)"' if gd < 0 else "")
            body += f'<tr><td><span class="pos {pos_cls}">{i+1}</span></td><td>{esc(t["name"])}</td><td>{t.get("mp",0)}</td><td {gd_c}>{gd_str}</td><td class="pts">{t.get("pts",0)}</td></tr>'
        body += '</table></div>'
    body += '</div></div>'

    body += '<div><div class="sect">▸▸ TOP SCORERS</div><div class="scorers">'
    if top_scorers:
        for i, s in enumerate(top_scorers):
            rank_cls = "top" if i < 3 else ""
            medal = "🥇" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else str(i+1)))
            body += f'<div class="scorer"><span class="scorer-rank {rank_cls}">{medal}</span><span class="scorer-name">{esc(s["name"])}</span><span class="scorer-team">{esc(s["team"])}</span><span class="scorer-goals">{s["goals"]}</span></div>'
    else:
        body += '<div style="text-align:center;font-size:.7rem;color:var(--text2);padding:16px">No goals yet</div>'
    body += '</div></div></div>'

    # Ad after standings/scorers
    body += adsense("ad-home-bottom","ad-top")

    updated = scores.get("updated_at", "never")
    body += f'<div style="text-align:center;font-size:.65rem;color:var(--text2);margin-top:16px">{scores.get("match_count",0)} matches · Updated {updated[:19]}</div>'
    return page("World Cup 2026 — Live Scores, Stats & Analysis", body, "home")


@app.get("/live", response_class=HTMLResponse)
async def live_page():
    scores = load_json("live_scores.json")
    matches = scores.get("matches", [])
    finished = [m for m in matches if m.get("status") == "FINISHED"]
    in_play = [m for m in matches if m.get("status") == "IN_PLAY"]
    scheduled = [m for m in matches if m.get("status") == "SCHEDULED"]
    # Sort finished newest first, upcoming soonest first
    finished.sort(key=_sort_key_date, reverse=True)
    scheduled.sort(key=_sort_key_date)

    body = f'''<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
  <div><h1 style="font-size:1.5rem;font-weight:800;margin-bottom:2px">Match Center</h1><p style="font-size:.65rem;color:var(--text2)">{len(matches)} matches · Auto-refresh 120s</p></div>
  <div style="display:flex;gap:6px">'''
    if in_play:
        body += f'<span class="match-tag tag-live">🔴 {len(in_play)} LIVE</span>'
    if finished:
        body += f'<span class="match-tag tag-ft">✅ {len(finished)} FT</span>'
    if scheduled:
        body += f'<span class="match-tag tag-sc">⏳ {len(scheduled)} Upcoming</span>'
    body += '</div></div>'

    # Filter tabs
    body += '<div class="filter">'
    body += '<button class="filter-btn on" onclick="filterMatches(\'all\',this)">ALL</button>'
    if in_play:
        body += '<button class="filter-btn" onclick="filterMatches(\'live\',this)">🔴 LIVE</button>'
    if finished:
        body += '<button class="filter-btn" onclick="filterMatches(\'finished\',this)">✅ FINISHED</button>'
    if scheduled:
        body += '<button class="filter-btn" onclick="filterMatches(\'scheduled\',this)">⏳ UPCOMING</button>'
    body += '</div>'

    # Ad after filter tabs
    body += adsense("ad-live-filter","ad-inline")

    # All matches visible by default — live first, then finished, then scheduled
    body += '<div class="match-grid" id="matchgrid">'
    for m in (in_play + finished + scheduled):
        s = m.get("status", "")
        data_status = "live" if s == "IN_PLAY" else ("finished" if s == "FINISHED" else "scheduled")
        body += f'<div class="match-card-wrap" data-status="{data_status}">'
        body += match_card(m)
        body += '</div>'
    body += '</div>'

    # Ad after match grid
    body += adsense("ad-live-bottom","ad-top")

    body += """<script>
function filterMatches(type, btn) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  document.querySelectorAll('.match-card-wrap').forEach(el => {
    el.style.display = (type === 'all' || el.dataset.status === type) ? '' : 'none';
  });
}
// Auto-refresh every 30s for live matches
setInterval(function() { location.reload(); }, 30000);
</script>"""

    updated = scores.get("updated_at", "")[:19]
    body += f'<div style="text-align:center;font-size:.65rem;color:var(--text2);margin-top:20px">{len(matches)} matches · Updated {updated}</div>'
    return page("Match Center — Live Scores & Fixtures | WC26 Hub", body, "live")


@app.get("/match/{match_id}", response_class=HTMLResponse)
async def match_detail(match_id: str):
    scores = load_json("live_scores.json")
    match = None
    for m in scores.get("matches", []):
        if str(m.get("id")) == str(match_id):
            match = m; break
    if not match:
        return page("Match Not Found | WC26 Hub", '<div style="text-align:center;padding:40px;color:var(--text2)">Match not found</div>', "live")

    s = match.get("status", "")
    status_class = "tag-ft" if s == "FINISHED" else ("tag-live" if s == "IN_PLAY" else "tag-sc")
    status_text = "● FULL TIME" if s == "FINISHED" else (f"🔴 LIVE - {match.get('minute','')}'" if s == "IN_PLAY" else "● UPCOMING")
    hs = match.get("home_score") or "—"
    aws = match.get("away_score") or "—"
    flag_h = f'<img src="{esc(match["home_flag"])}" style="width:22px;height:15px;object-fit:cover;border-radius:2px;vertical-align:middle">' if match.get("home_flag") else ""
    flag_a = f'<img src="{esc(match["away_flag"])}" style="width:22px;height:15px;object-fit:cover;border-radius:2px;vertical-align:middle">' if match.get("away_flag") else ""
    match_date_info = _format_date(match.get("date", ""), match.get("stadium_id"))
    match_date = match_date_info["dubai_str"]
    match_utc = match_date_info["utc_iso"]

    body = f'''<div class="match-detail">
  <div class="match-detail-header">
    <div style="font-size:.6rem;color:var(--text2);margin-bottom:8px">{esc(match.get("group",""))} · MD{esc(match.get("matchday",""))} · {esc(match.get("stadium",""))} · <span class="match-time" data-utc="{match_utc}" title="Kickoff: {match_date}">{match_date}</span></div>
    <div class="teams">
      <div><span class="team-name">{flag_h} {esc(match["home"])}</span></div>
      <div class="match-score">{hs} — {aws}</div>
      <div><span class="team-name">{esc(match["away"])} {flag_a}</span></div>
    </div>
    <div style="margin-top:8px"><span class="match-tag {status_class}">{status_text}</span></div>
  </div>
  <div class="tabs">
    <div class="tab on" data-tab="stats" onclick="switchTab('stats')">📊 STATS</div>
    <div class="tab" data-tab="events" onclick="switchTab('events')">⏱️ TIMELINE</div>
    <div class="tab" data-tab="players" onclick="switchTab('players')">👥 PLAYERS</div>
  </div>'''

    # Ad after tabs, before content
    body += adsense("ad-match-top","ad-inline")

    # Stats tab (active by default)
    body += '<div id="tab-stats" class="tab-body active">'
    if match.get("stats"):
        st = match["stats"]
        for label, hk, suffix in [
            ("Possession","possession","%"),("Total Shots","shots",""),("Shots on Target","shots_on_target",""),
            ("Passes","passes",""),("Pass Accuracy","pass_accuracy","%"),("Expected Goals (xG)","xG",""),
            ("Corners","corners",""),("Fouls","fouls",""),("Yellow Cards","yellow_cards",""),
            ("Red Cards","red_cards",""),("Tackles","tackles",""),("Interceptions","interceptions",""),("Offsides","offsides","")
        ]:
            hv = st[hk]["home"]; av = st[hk]["away"]
            total = hv + av
            hp = round(hv / total * 100) if total > 0 else 50
            ap = 100 - hp
            body += f'<div class="stat-row"><span class="stat-val h">{hv}{suffix}</span><span class="stat-lbl">{label}</span><span class="stat-val a">{av}{suffix}</span></div>'
            body += f'<div class="stat-bar-row"><div class="stat-bar-h" style="width:{hp}%"></div><div class="stat-bar-a" style="width:{ap}%"></div></div>'
    else:
        body += '<div style="text-align:center;padding:24px;color:var(--text2);font-size:.75rem">No stats available</div>'
    body += '</div>'

    # Events tab
    body += '<div id="tab-events" class="tab-body">'
    if match.get("events"):
        body += '<div class="timeline">'
        for e in sorted(match["events"], key=lambda x: x["minute"]):
            color = "goal" if e["type"] == "goal" else ("yellow" if e["type"] == "yellow_card" else "red")
            icon = "⚽" if e["type"] == "goal" else ("🟨" if e["type"] == "yellow_card" else "🟥")
            body += f'<div class="event"><div class="event-dot {color}"></div><span class="event-time {color}">{e["minute"]}\'</span> {icon} <span class="event-player">{esc(e["player"])}</span> <span class="event-team">({esc(e["team"])})</span></div>'
        body += '</div>'
    else:
        body += '<div style="text-align:center;padding:24px;color:var(--text2);font-size:.75rem">No events recorded</div>'
    body += '</div>'

    # Players tab
    body += '<div id="tab-players" class="tab-body">'
    if match.get("players"):
        home_players = [p for p in match["players"] if p["team"] == match["home"]]
        away_players = [p for p in match["players"] if p["team"] == match["away"]]
        for team_name, team_players in [(match["home"], home_players), (match["away"], away_players)]:
            team_players.sort(key=lambda p: p.get("rating", 0), reverse=True)
            team_color = "var(--ng)" if team_name == match["home"] else "var(--nb)"
            body += f'<div style="font-size:.65rem;font-weight:700;color:{team_color};margin-bottom:6px">{esc(team_name)}</div>'
            body += '<table class="player-table"><thead><tr><th>#</th><th>Player</th><th>Pos</th><th>Min</th><th>⚽</th><th>🅰️</th><th>Sh</th><th>Rt</th></tr></thead><tbody>'
            for p in team_players:
                goal_style = 'style="color:var(--ng);font-weight:700"' if p.get("goals",0)>0 else ""
                ast_style = 'style="color:var(--nb);font-weight:700"' if p.get("assists",0)>0 else ""
                body += f'<tr><td>{p.get("number","")}</td><td>{esc(p["name"])}</td><td>{p.get("position","")}</td><td>{p.get("minutes","")}</td><td {goal_style}>{p.get("goals",0)}</td><td {ast_style}>{p.get("assists",0)}</td><td>{p.get("shots",0)}</td><td>{rating_badge(p.get("rating",0))}</td></tr>'
            body += '</tbody></table>'
    else:
        body += '<div style="text-align:center;padding:24px;color:var(--text2);font-size:.75rem">No player data available</div>'
    body += '</div>'

    # Ad before back link
    body += adsense("ad-match-bottom","ad-top")

    # Affiliate rail
    body += affiliate_rail("Shop " + match["home"] + " & " + match["away"] + " Gear")

    body += '''<div style="margin-top:16px;text-align:center"><a href="/live" style="font-size:.65rem;color:var(--nb)">← Back to Match Center</a></div></div>
<script>
function switchTab(t){
  document.querySelectorAll(".tab").forEach(function(x){x.classList.remove("on")});
  document.querySelector("[data-tab="+t+"]").classList.add("on");
  document.querySelectorAll(".tab-body").forEach(function(x){x.classList.remove("active")});
  document.getElementById("tab-"+t).classList.add("active");
}
</script>'''
    return page(f"{match['home']} vs {match['away']} — Match Details | WC26 Hub", body, "live")


@app.get("/standings", response_class=HTMLResponse)
async def standings_page():
    standings = load_json("standings.json")
    groups = standings.get("groups", [])
    body = '<div class="sect">▸▸ GROUP STANDINGS</div><div class="groups-grid">'
    for g in groups:
        body += f'<div class="group-card"><div class="group-head"><span>GROUP {esc(g["name"])}</span><span>{g["teams"][0].get("mp",0) if g.get("teams") else 0}/3 played</span></div><table class="group-table">'
        for i, t in enumerate(g.get("teams", [])):
            pos_cls = "pos-q" if i < 2 else "pos-n"
            gd = t.get("gd", 0)
            gd_str = f"+{gd}" if gd > 0 else str(gd)
            gd_c = 'style="color:var(--ng)"' if gd > 0 else ('style="color:var(--nr)"' if gd < 0 else "")
            body += f'<tr><td><span class="pos {pos_cls}">{i+1}</span></td><td>{esc(t["name"])}</td><td>{t.get("mp",0)}</td><td {gd_c}>{gd_str}</td><td class="pts">{t.get("pts",0)}</td></tr>'
        body += '</table></div>'
    body += '</div>'

    # Ad after group grid
    body += adsense("ad-standings-bottom","ad-top")

    return page("Group Standings — World Cup 2026 | WC26 Hub", body, "standings")


@app.get("/stats", response_class=HTMLResponse)
async def stats_page():
    scores = load_json("live_scores.json")
    matches = scores.get("matches", [])
    finished = [m for m in matches if m.get("status") == "FINISHED"]
    top_scorers = scores.get("top_scorers", [])

    team_map = {}
    for m in finished:
        for team, idx in [(m["home"], 0), (m["away"], 1)]:
            if team not in team_map:
                team_map[team] = {"team": team, "mp": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "xg": 0}
            t = team_map[team]
            t["mp"] += 1
            gf = int(m["home_score"]) if idx == 0 and m.get("home_score") and m["home_score"] != "null" else 0
            ga = int(m["away_score"]) if idx == 0 and m.get("away_score") and m["away_score"] != "null" else 0
            if idx == 1:
                gf = int(m["away_score"]) if m.get("away_score") and m["away_score"] != "null" else 0
                ga = int(m["home_score"]) if m.get("home_score") and m["home_score"] != "null" else 0
            t["gf"] += gf; t["ga"] += ga
            if gf > ga: t["w"] += 1
            elif gf == ga: t["d"] += 1
            else: t["l"] += 1
            if m.get("stats"):
                t["xg"] += m["stats"]["xG"]["home"] if idx == 0 else m["stats"]["xG"]["away"]
    teams_sorted = sorted(team_map.values(), key=lambda t: (t["w"] * 3 + t["d"]), reverse=True)

    body = '<div class="sect">▸▸ TOURNAMENT STATS</div>'
    body += f'<p style="font-size:.65rem;color:var(--text2);margin-bottom:16px">Top scorers, team performance, and key metrics · {len(finished)} matches played</p>'
    body += '<div class="two-col">'

    body += '<div><div class="sect">▸▸ TOP SCORERS</div><div class="scorers">'
    if top_scorers:
        for i, s in enumerate(top_scorers):
            rank_cls = "top" if i < 3 else ""
            medal = "🥇" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else str(i+1)))
            body += f'<div class="scorer"><span class="scorer-rank {rank_cls}">{medal}</span><span class="scorer-name">{esc(s["name"])}</span><span class="scorer-team">{esc(s["team"])}</span><span class="scorer-goals">{s["goals"]}</span></div>'
    else:
        body += '<div style="text-align:center;font-size:.7rem;color:var(--text2);padding:16px">No goals yet</div>'
    body += '</div></div>'

    # Ad after top scorers
    body += adsense("ad-stats-scorers","ad-inline")

    body += '<div><div class="sect">▸▸ TEAM PERFORMANCE</div><div class="groups-grid">'
    for t in teams_sorted:
        gd = t["gf"] - t["ga"]
        gd_str = f"+{gd}" if gd > 0 else str(gd)
        body += f'<div class="group-card" style="padding:12px"><div style="display:flex;justify-content:space-between;margin-bottom:8px"><span style="font-weight:700;font-size:.85rem">{esc(t["team"])}</span><span style="font-size:.65rem;color:var(--text2)">{t["mp"]} MP</span></div>'
        body += f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:4px;text-align:center"><div><div style="font-size:1.1rem;font-weight:800;color:var(--ng)">{t["w"]}</div><div style="font-size:.55rem;color:var(--text2)">W</div></div><div><div style="font-size:1.1rem;font-weight:800;color:var(--ny)">{t["d"]}</div><div style="font-size:.55rem;color:var(--text2)">D</div></div><div><div style="font-size:1.1rem;font-weight:800;color:var(--nr)">{t["l"]}</div><div style="font-size:.55rem;color:var(--text2)">L</div></div><div><div style="font-size:1.1rem;font-weight:800">{gd_str}</div><div style="font-size:.55rem;color:var(--text2)">GD</div></div></div>'
        body += f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:4px;text-align:center;font-size:.65rem;color:var(--text2);margin-top:6px"><div><span style="color:var(--ng)">{t["gf"]}</span> GF</div><div><span style="color:var(--nr)">{t["ga"]}</span> GA</div><div><span style="color:var(--nb)">{t["xg"]:.1f}</span> xG</div></div></div>'
    body += '</div></div></div>'

    # Ad at bottom
    body += adsense("ad-stats-bottom","ad-top")

    return page("Stats — Top Scorers, xG & Team Stats | WC26 Hub", body, "stats")


@app.get("/api/scores")
async def api_scores():
    return JSONResponse(load_json("live_scores.json"))

@app.get("/api/standings")
async def api_standings():
    return JSONResponse(load_json("standings.json"))
