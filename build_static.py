#!/usr/bin/env python3
"""Static site generator for WC26 Hub. Reads output/live_scores.json and
output/standings.json, writes pre-rendered HTML files into docs/.
Run: python3 build_static.py
"""
import json, hashlib, random, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SITE = Path(__file__).parent
OUTPUT = SITE / "output"
DOCS = SITE / "docs"
PLAYERS_FILE = SITE / "players.json"

# ── Reuse constants from server ──────────────────────────────────────────────

STADIUM_TZ = {
    "1": "America/Mexico_City", "2": "America/Mexico_City", "3": "America/Mexico_City",
    "4": "America/Chicago", "5": "America/Chicago", "6": "America/Chicago",
    "7": "America/New_York", "8": "America/New_York", "9": "America/New_York",
    "10": "America/New_York", "11": "America/New_York",
    "12": "America/Toronto", "13": "America/Vancouver",
    "14": "America/Los_Angeles", "15": "America/Los_Angeles", "16": "America/Los_Angeles",
}
DUBAI_TZ = ZoneInfo("Asia/Dubai")

TEAM_COLORS = {
    "Mexico":("#006847","#fff"),"South Africa":("#ffb81c","#111"),"South Korea":("#c60c30","#fff"),
    "Czech Republic":("#d7141a","#fff"),"Canada":("#ff0000","#fff"),"Bosnia and Herzegovina":("#002395","#fff"),
    "United States":("#002868","#fff"),"Paraguay":("#d52b1e","#fff"),"Haiti":("#00209f","#fff"),
    "Scotland":("#003399","#fff"),"Australia":("#00843d","#fff"),"Turkey":("#e30a17","#fff"),
    "Brazil":("#009739","#fff"),"Morocco":("#c1272d","#fff"),"Qatar":("#8b1538","#fff"),
    "Switzerland":("#ff0000","#fff"),"Ivory Coast":("#f77f00","#fff"),"Ecuador":("#ffd100","#111"),
    "Germany":("#000000","#fff"),"Curaçao":("#002b7f","#fff"),"Netherlands":("#ff6600","#fff"),
    "Japan":("#000080","#fff"),"Sweden":("#006aa7","#fff"),"Tunisia":("#e70013","#fff"),
    "Iran":("#239f40","#fff"),"New Zealand":("#000000","#fff"),"Spain":("#c60b1e","#fff"),
    "Cape Verde":("#003893","#fff"),"Belgium":("#ed2939","#fff"),"Egypt":("#000000","#fff"),
    "Saudi Arabia":("#006c35","#fff"),"Uruguay":("#0038a8","#fff"),"France":("#002395","#fff"),
    "Senegal":("#00853f","#fff"),"Iraq":("#007a3d","#fff"),"Norway":("#ef2b2d","#fff"),
    "Argentina":("#74acdf","#fff"),"Algeria":("#006233","#fff"),"Austria":("#ed2939","#fff"),
    "Jordan":("#007a3d","#fff"),"Portugal":("#006600","#fff"),"Democratic Republic of the Congo":("#007fff","#fff"),
    "England":("#ffffff","#111"),"Croatia":("#ff0000","#fff"),"Uzbekistan":("#0099b5","#fff"),
    "Colombia":("#fcd116","#111"),"Ghana":("#006b3f","#fff"),"Panama":("#d21034","#fff"),
}

AFFILIATE_PRODUCTS = [
    ("⚽","FIFA 24 PS5","$59.99","Best Seller"),
    ("👟","Mercurial Vapor 15","$129.99","Top Rated"),
    ("🧤","Predator Edge Gloves","$44.99","New"),
    ("🏆","WC26 Official Ball","$34.99","Hot"),
    ("👕","Argentina Jersey 23/24","$89.99","Popular"),
    ("🎒","Nike Strike Backpack","$39.99","Deal"),
]

# ── Load data ────────────────────────────────────────────────────────────────

def seeded(s):
    h = hashlib.md5(s.encode()).hexdigest()
    return random.Random(int(h[:8], 16))

PLAYERS = json.loads(PLAYERS_FILE.read_text(encoding="utf-8")) if PLAYERS_FILE.exists() else {}
SCORES = json.loads((OUTPUT / "live_scores.json").read_text()) if (OUTPUT / "live_scores.json").exists() else {"matches":[],"top_scorers":[]}
STANDINGS = json.loads((OUTPUT / "standings.json").read_text()) if (OUTPUT / "standings.json").exists() else {"groups":[]}

# ── Helpers (same logic as server.py, no FastAPI deps) ───────────────────────

def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def _team_players(team_name, rng):
    names = PLAYERS.get(team_name, [])
    if not names:
        return [(f"{team_name[:3].upper()} Player {i+1}", pos) for i, pos in enumerate(["GK","LB","CB","CB","RB","CM","CM","LW","RW","ST","ST","MF","FW","DF"])]
    positions = ["GK","LB","CB","CB","RB","CM","CM","LW","RW","ST","ST","MF","FW","DF"]
    return [(names[i] if i < len(names) else f"{team_name[:3].upper()} Sub {i-10}", pos) for i, pos in enumerate(positions)]

def _parse_date(date_str, stadium_id=None):
    if not date_str: return None
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
    dt = _parse_date(date_str, stadium_id)
    if dt:
        utc_iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        dubai_dt = dt.astimezone(DUBAI_TZ)
        dubai_str = dubai_dt.strftime("%b %d · %H:%M GST")
        return {"utc_iso": utc_iso, "dubai_str": dubai_str}
    return {"utc_iso": "", "dubai_str": date_str or ""}

def _sort_key_date(m):
    dt = _parse_date(m.get("date",""), m.get("stadium_id"))
    return dt if dt else datetime.min.replace(tzinfo=timezone.utc)

def rating_badge(r):
    cls = "r-e" if r >= 8 else ("r-g" if r >= 7 else ("r-a" if r >= 6 else "r-p"))
    return f'<span class="rating {cls}">{r}</span>'

# ── CSS (extracted from server.py) ───────────────────────────────────────────

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
@media(max-width:768px){.ad-top{max-width:320px;min-height:50px}.ad-side{max-width:300px;min-height:100px}.affiliate-grid{grid-template-columns:repeat(2,1fr)}.live-banner-in{flex-direction:column;align-items:flex-start;gap:6px}.live-teams{font-size:.75rem}}
"""

# ── JS ───────────────────────────────────────────────────────────────────────

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
    else if(parts[i].type==='day') localStr+=parts[i].value+' \\u00b7 ';
    else if(parts[i].type==='hour') localStr+=parts[i].value;
    else if(parts[i].type==='minute') localStr+=':'+parts[i].value;
    else if(parts[i].type==='timeZoneName') tzAbbr=parts[i].value;
  }
  el.textContent=localStr+' '+tzAbbr;
  el.title='Original: '+el.title;
});
</script>"""

# Pitch JS template (simplified — same animation, no changes needed)
PITCH_JS_TEMPLATE = open(SITE / "server.py").read().split("PITCH_JS_TEMPLATE = ")[1].split("\n")[0]
# Too complex to extract inline — read from server.py directly
import importlib.util
spec = importlib.util.spec_from_file_location("server_mod", str(SERVER_PY := SITE / "server.py"))
# Actually, just inline the pitch JS. It's too long to duplicate.
# Better approach: import from server.py at build time.

# ── Build-time import from server.py ────────────────────────────────────────

import importlib.util, types

_server = types.ModuleType("_server")
_server.__file__ = str(SERVER_PY)
# We only need PITCH_JS_TEMPLATE from server.py — read it directly
_server_code = SERVER_PY.read_text()
# Extract PITCH_JS_TEMPLATE
import re
_pitch_match = re.search(r'PITCH_JS_TEMPLATE\s*=\s*"""(.*?)"""', _server_code, re.DOTALL)
PITCH_JS_TEMPLATE = _pitch_match.group(1) if _pitch_match else ""

# Also extract the full CSS from server.py to make sure they stay in sync
_css_match = re.search(r'CSS\s*=\s*"""(.*?)"""', _server_code, re.DOTALL)
if _css_match:
    CSS = _css_match.group(1)

# ── HTML builders ────────────────────────────────────────────────────────────

def page(title, body, page_id="home"):
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>{CSS}</style></head><body>
<div class="topbar"><div class="topbar-in">
  <a href="/" class="logo">WC26</a>
  <button class="hamburger" id="hamburger" onclick="var n=document.querySelector('.nav');n.classList.toggle('open');this.classList.toggle('open')"><span></span><span></span><span></button>
  <nav class="nav">
    <a href="/" class="{'on' if page_id=='home' else ''}">▶ HOME</a>
    <a href="/live.html" class="{'on' if page_id=='live' else ''}">▶ LIVE</a>
    <a href="/standings.html" class="{'on' if page_id=='standings' else ''}">▶ STANDINGS</a>
    <a href="/stats.html" class="{'on' if page_id=='stats' else ''}">▶ STATS</a>
  </nav>
</div></div>
<div class="shell">{body}</div>
<div class="footer">WC26 HUB · DATA: WORLDUP26.IR · NOT AFFILIATED WITH FIFA · BUILT WITH ⚽ AND ☕</div>
{TZ_JS}
</body></html>"""

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
    home_display = esc(m["home"]) if m["home"] != "TBD" else '<span style="color:var(--text2)">TBD</span>'
    away_display = esc(m["away"]) if m["away"] != "TBD" else '<span style="color:var(--text2)">TBD</span>'
    return f'''<a href="/match/{esc(m["id"])}.html" class="match-card">
  <div class="match-top"><span class="match-tag {status_class}">{status_text}</span>
    <span class="match-meta">Grp {esc(m.get("group",""))} · MD{esc(m.get("matchday",""))}</span></div>
  <div class="match-teams">
    <div style="text-align:right"><span class="team-name">{flag_h} {home_display}</span></div>
    <div class="match-score">{hs}—{aws}</div>
    <div style="text-align:left"><span class="team-name">{away_display} {flag_a}</span></div>
  </div><div class="match-foot">{date_pill}{stadium}</div></a>'''

def adsense(slot_id, css_class=""):
    return f'''<div class="ad-slot {css_class}" id="{slot_id}">
  <ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-XXXXXXXXXXXXXXXX"
       data-ad-slot="YYYYYYYYYY" data-ad-format="auto" data-full-width-responsive="true"></ins>
  <script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script>
</div>'''

def affiliate_rail(title="World Cup Gear"):
    cards = ""
    for icon, name, price, badge in AFFILIATE_PRODUCTS:
        cards += '<a href="#" class="aff-card" rel="sponsored nofollow" target="_blank"><div class="aff-icon">' + icon + '</div><div class="aff-name">' + name + '</div><div class="aff-price">' + price + '</div><span class="aff-badge">' + badge + '</span></a>'
    return '<div class="affiliate-rail"><div class="aff-title">' + title + '</div><div class="affiliate-grid">' + cards + '</div></div>'

# ── Page generators ──────────────────────────────────────────────────────────

def build_homepage(matches, top_scorers, groups):
    finished = sorted([m for m in matches if m.get("status")=="FINISHED"], key=_sort_key_date, reverse=True)
    live = [m for m in matches if m.get("status")=="IN_PLAY"]
    scheduled = sorted([m for m in matches if m.get("status")=="SCHEDULED"], key=_sort_key_date)
    display = (scheduled[:2] + finished)[:6]
    groups = groups[:4]

    hero = live[0] if live else (finished[0] if finished else (scheduled[0] if scheduled else None))
    home_name = esc(hero["home"]) if hero else "Mexico"
    away_name = esc(hero["away"]) if hero else "South Africa"
    hero_date_info = _format_date(hero.get("date",""), hero.get("stadium_id")) if hero else {"dubai_str":""}
    hero_date = hero_date_info["dubai_str"]

    hero_home = hero["home"] if hero else "Mexico"
    hero_away = hero["away"] if hero else "South Africa"
    home_players = PLAYERS.get(hero_home, [])[:6]
    away_players = PLAYERS.get(hero_away, [])[:6]
    while len(home_players) < 6: home_players.append(f"Player {len(home_players)+1}")
    while len(away_players) < 6: away_players.append(f"Player {len(away_players)+1}")
    home_colors = TEAM_COLORS.get(hero_home, ("#006847","#fff"))
    away_colors = TEAM_COLORS.get(hero_away, ("#ffb81c","#111"))
    pitch_js = PITCH_JS_TEMPLATE
    for k,v in [('{home_shirt}',home_colors[0]),('{away_shirt}',away_colors[0]),('{ht}',home_colors[1]),('{at}',away_colors[1]),
                ('{h1}',home_players[0]),('{h2}',home_players[1]),('{h3}',home_players[2]),('{h4}',home_players[3]),('{h5}',home_players[4]),('{h6}',home_players[5]),
                ('{a1}',away_players[0]),('{a2}',away_players[1]),('{a3}',away_players[2]),('{a4}',away_players[3]),('{a5}',away_players[4]),('{a6}',away_players[5])]:
        pitch_js = pitch_js.replace(k, v)

    body = f'''<div class="pitch-hero">
  <canvas id="pitch"></canvas>
  <div class="pitch-overlay">
    <div class="pitch-badges"><span class="pitch-badge g">FIFA WORLD CUP 2026</span><span class="pitch-badge w">USA · CANADA · MEXICO</span></div>
    <h1>{home_name} <span style="color:#fff">vs</span> {away_name}</h1>
    <p><span class="match-time" data-utc="{hero_date_info["utc_iso"]}" title="Kickoff: {hero_date}">{hero_date}</span> · Live from the pitch — watch the teams pass and move in their zones.</p>
  </div></div>
<script>{pitch_js}</script>'''

    if live:
        for lm in live:
            hs = lm.get("home_score") or "—"
            aws = lm.get("away_score") or "—"
            flag_h = f'<img src="{esc(lm["home_flag"])}" style="width:22px;height:15px;object-fit:cover;border-radius:2px;vertical-align:middle">' if lm.get("home_flag") else ""
            flag_a = f'<img src="{esc(lm["away_flag"])}" style="width:22px;height:15px;object-fit:cover;border-radius:2px;vertical-align:middle">' if lm.get("away_flag") else ""
            minute = lm.get("minute","LIVE")
            body += f'<a href="/match/{esc(lm["id"])}.html" class="live-banner"><div class="live-banner-in"><div class="live-badge"><span class="pulse"></span> LIVE {esc(minute)}\'</div><div class="live-teams">{flag_h} {esc(lm["home"])} <span class="live-score">{hs}-{aws}</span> {esc(lm["away"])} {flag_a}</div></div></a>'

    body += affiliate_rail("World Cup Gear")
    body += adsense("ad-home-hero","ad-top")

    ticker_items = ""
    for m in (live[:3] if live else []):
        hs = m.get("home_score","—"); aws = m.get("away_score","—"); minute = m.get("minute","LIVE")
        ticker_items += '<span class="ticker-item"><strong>' + esc(m["home"]) + '</strong> <span class="ticker-score">' + str(hs) + '-' + str(aws) + '</span> <strong>' + esc(m["away"]) + '</strong> <sup style="color:var(--nr)">' + esc(minute) + '\'</sup></span>'
    for m in (finished[:6] if finished else []):
        ticker_items += f'<span class="ticker-item"><strong>{esc(m["home"])}</strong> <span class="ticker-score">{m.get("home_score","-")}-{m.get("away_score","-")}</span> <strong>{esc(m["away"])}</strong> <sup>FT</sup></span>'
    if ticker_items:
        body += f'<div class="ticker"><div style="display:flex;align-items:center"><div class="ticker-label"><span class="pulse"></span>LIVE RESULTS</div><div style="overflow:hidden;flex:1;padding:8px 0"><div class="ticker-track">{ticker_items}{ticker_items}</div></div></div></div>'

    body += '<div class="quick-nav">'
    for icon, label, href in [("🔴","LIVE CENTER","/live.html"),("📊","STANDINGS","/standings.html"),("📈","STATS","/stats.html"),("👟","BEST BOOTS","/")]:
        body += f'<a href="{href}"><div class="icon">{icon}</div><div class="lbl">{label}</div></a>'
    body += '</div>'
    body += adsense("ad-home-nav","ad-inline")

    body += '<div class="sect">▸▸ RECENT & UPCOMING</div><div class="match-grid">'
    for m in display:
        body += match_card(m)
    body += '</div>'
    body += adsense("ad-home-matches","ad-top")

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
            medal = ["🥇","🥈","🥉"][i] if i < 3 else f"{i+1}"
            body += f'<div class="scorer"><span class="scorer-rank {rank_cls}">{medal}</span><span class="scorer-name">{esc(s["name"])}</span><span class="scorer-team">{esc(s["team"])}</span><span class="scorer-goals">{s["goals"]}</span></div>'
    body += '</div></div></div>'
    body += adsense("ad-home-bottom","ad-top")
    updated = SCORES.get("updated_at","")
    body += f'<div style="text-align:center;font-size:.65rem;color:var(--text2);margin-top:16px">{len(matches)} matches · Updated {updated}</div>'

    return page("WC26 Hub — World Cup 2026 Live Scores, Standings & Stats", body, "home")

def build_live_page(matches):
    finished = sorted([m for m in matches if m.get("status")=="FINISHED"], key=_sort_key_date, reverse=True)
    in_play = [m for m in matches if m.get("status")=="IN_PLAY"]
    scheduled = sorted([m for m in matches if m.get("status")=="SCHEDULED"], key=_sort_key_date)

    body = f'''<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
  <div><h1 style="font-size:1.5rem;font-weight:800;margin-bottom:2px">Match Center</h1><p style="font-size:.65rem;color:var(--text2)">{len(matches)} matches · Last updated {SCORES.get("updated_at","")}</p></div>
  <div style="display:flex;gap:6px">'''
    if in_play:
        body += f'<span class="match-tag tag-live">🔴 {len(in_play)} LIVE</span>'
    if finished:
        body += f'<span class="match-tag tag-ft">✅ {len(finished)} FT</span>'
    if scheduled:
        body += f'<span class="match-tag tag-sc">⏳ {len(scheduled)} Upcoming</span>'
    body += '</div></div>'

    body += '<div class="filter">'
    body += '<button class="filter-btn on" onclick="filterMatches(\'all\',this)">ALL</button>'
    if in_play:
        body += '<button class="filter-btn" onclick="filterMatches(\'live\',this)">🔴 LIVE</button>'
    if finished:
        body += '<button class="filter-btn" onclick="filterMatches(\'finished\',this)">✅ FINISHED</button>'
    if scheduled:
        body += '<button class="filter-btn" onclick="filterMatches(\'scheduled\',this)">⏳ UPCOMING</button>'
    body += '</div>'
    body += adsense("ad-live-filter","ad-inline")

    body += '<div class="match-grid" id="matchgrid">'
    for m in (in_play + finished + scheduled):
        s = m.get("status", "")
        data_status = "live" if s == "IN_PLAY" else ("finished" if s == "FINISHED" else "scheduled")
        body += f'<div class="match-card-wrap" data-status="{data_status}">'
        body += match_card(m)
        body += '</div>'
    body += '</div>'
    body += adsense("ad-live-bottom","ad-top")

    body += """<script>
function filterMatches(type, btn) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  document.querySelectorAll('.match-card-wrap').forEach(el => {
    el.style.display = (type === 'all' || el.dataset.status === type) ? '' : 'none';
  });
}
</script>"""

    return page("Match Center — WC26 Hub", body, "live")

def build_match_detail(match):
    m = match
    s = m.get("status", "")
    status_class = "tag-ft" if s == "FINISHED" else ("tag-live" if s == "IN_PLAY" else "tag-sc")
    status_text = "● FULL TIME" if s == "FINISHED" else (f"🔴 LIVE - {match.get('minute','')}'" if s == "IN_PLAY" else "● UPCOMING")
    hs = match.get("home_score") or "—"
    aws = match.get("away_score") or "—"
    flag_h = f'<img src="{esc(match["home_flag"])}" style="width:22px;height:15px;object-fit:cover;border-radius:2px;vertical-align:middle">' if match.get("home_flag") else ""
    flag_a = f'<img src="{esc(match["away_flag"])}" style="width:22px;height:15px;object-fit:cover;border-radius:2px;vertical-align:middle">' if match.get("away_flag") else ""
    match_date_info = _format_date(match.get("date",""), match.get("stadium_id"))
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

    body += adsense("ad-match-top","ad-inline")

    # Stats tab
    stats = match.get("stats", {})
    body += '<div class="tab-body open" id="tab-stats">'
    if stats:
        for label, hk, ak in [("POSSESSION","possession","possession"),("SHOTS","shots","shots"),("SHOTS ON TARGET","shots_on_target","shots_on_target"),
                               ("PASSES","passes","passes"),("PASS ACCURACY","pass_accuracy","pass_accuracy"),("xG","xG","xG"),
                               ("FOULS","fouls","fouls"),("CORNERS","corners","corners"),("OFFSIDES","offsides","offsides"),
                               ("TACKLES","tackles","tackles"),("INTERCEPTIONS","interceptions","interceptions"),
                               ("YELLOW CARDS","yellow_cards","yellow_cards"),("RED CARDS","red_cards","red_cards")]:
            hv = stats.get(hk,{}).get("home",0); av = stats.get(ak,{}).get("away",0)
            total = hv + av if (hv+av) > 0 else 1
            hp = int(hv/total*100); ap = 100-hp
            body += f'<div class="stat-row"><span class="stat-val h">{hv}</span><span class="stat-lbl">{label}</span><span class="stat-val a">{av}</span></div>'
            body += f'<div class="stat-bar-row"><div class="stat-bar-h" style="width:{hp}%"></div><div class="stat-bar-a" style="width:{ap}%"></div></div>'
    body += '</div>'

    # Events tab
    body += '<div class="tab-body" id="tab-events"><div class="timeline">'
    for ev in match.get("events", []):
        dot_cls = "goal" if ev["type"]=="goal" else ("yellow" if ev["type"]=="yellow_card" else "red")
        time_cls = "goal" if ev["type"]=="goal" else ("yellow" if ev["type"]=="yellow_card" else "red")
        icon = "⚽" if ev["type"]=="goal" else ("🟨" if ev["type"]=="yellow_card" else "🟥")
        body += f'<div class="event"><div class="event-dot {dot_cls}"></div><span class="event-time {time_cls}">{ev["minute"]}\'</span><span>{icon} {esc(ev["player"])}</span><span class="event-team">{esc(ev["team"])}</span></div>'
    body += '</div></div>'

    # Players tab
    body += '<div class="tab-body" id="tab-players">'
    for team_name in [match["home"], match["away"]]:
        team_players = [p for p in match.get("players",[]) if p["team"]==team_name]
        body += f'<h3 style="font-size:.7rem;margin:12px 0 6px;color:var(--ng)">{esc(team_name)}</h3><table class="player-table"><tr><th>#</th><th>Player</th><th>Pos</th><th>Min</th><th>G</th><th>A</th><th>Rating</th></tr>'
        for p in team_players:
            body += f'<tr><td>{p["number"]}</td><td>{esc(p["name"])}</td><td>{p["position"]}</td><td>{p["minutes"]}</td><td>{p["goals"]}</td><td>{p["assists"]}</td><td>{rating_badge(p["rating"])}</td></tr>'
        body += '</table>'
    body += '</div>'

    body += adsense("ad-match-bottom","ad-top")

    body += """<script>
function switchTab(id) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
  document.querySelectorAll('.tab-body').forEach(b => b.classList.remove('open'));
  document.querySelector('[data-tab="'+id+'"]').classList.add('on');
  document.getElementById('tab-'+id).classList.add('open');
}
</script>"""

    body += '<a href="/live.html" style="display:inline-block;margin-top:16px;font-size:.65rem;color:var(--nb)">← BACK TO MATCH CENTER</a>'
    body += '</div>'

    body += affiliate_rail("Match Day Gear")

    return page(f'{esc(match["home"])} vs {esc(match["away"])} — WC26 Hub', body, "match")

def build_standings_page(groups):
    body = '<h1 style="font-size:1.5rem;font-weight:800;margin-bottom:16px">Group Standings</h1>'
    body += adsense("ad-standings-top","ad-inline")
    body += '<div class="groups-grid">'
    for g in groups:
        body += f'<div class="group-card"><div class="group-head"><span>GROUP {esc(g["name"])}</span><span>{g.get("teams",[])[0].get("mp",0)} played</span></div><table class="group-table">'
        for i, t in enumerate(g.get("teams", [])):
            pos_cls = "pos-q" if i < 2 else "pos-n"
            gd = t.get("gd", 0)
            gd_str = f"+{gd}" if gd > 0 else str(gd)
            gd_c = 'style="color:var(--ng)"' if gd > 0 else ('style="color:var(--nr)"' if gd < 0 else "")
            body += f'<tr><td><span class="pos {pos_cls}">{i+1}</span></td><td>{esc(t["name"])}</td><td>{t.get("mp",0)}</td><td>{t.get("w",0)}</td><td>{t.get("d",0)}</td><td>{t.get("l",0)}</td><td {gd_c}>{gd_str}</td><td class="pts">{t.get("pts",0)}</td></tr>'
        body += '</table></div>'
    body += '</div>'
    body += adsense("ad-standings","ad-top")
    return page("Standings — WC26 Hub", body, "standings")

def build_stats_page(matches, top_scorers):
    finished = [m for m in matches if m.get("status")=="FINISHED"]
    body = '<h1 style="font-size:1.5rem;font-weight:800;margin-bottom:16px">Tournament Stats</h1>'
    body += adsense("ad-stats-top","ad-inline")

    # Aggregate stats
    total_goals = sum(int(m.get("home_score",0) or 0) + int(m.get("away_score",0) or 0) for m in finished)
    total_matches = len(finished)
    avg_goals = round(total_goals/total_matches, 1) if total_matches else 0

    body += f'<div class="match-detail" style="margin-bottom:20px"><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;text-align:center">'
    body += f'<div><div style="font-size:1.5rem;font-weight:800;color:var(--ng)">{total_matches}</div><div style="font-size:.55rem;color:var(--text2)">MATCHES PLAYED</div></div>'
    body += f'<div><div style="font-size:1.5rem;font-weight:800;color:var(--ng)">{total_goals}</div><div style="font-size:.55rem;color:var(--text2)">TOTAL GOALS</div></div>'
    body += f'<div><div style="font-size:1.5rem;font-weight:800;color:var(--ng)">{avg_goals}</div><div style="font-size:.55rem;color:var(--text2)">AVG GOALS/MATCH</div></div>'
    body += '</div></div>'

    body += '<div class="sect">▸▸ TOP SCORERS</div><div class="scorers">'
    if top_scorers:
        for i, s in enumerate(top_scorers):
            rank_cls = "top" if i < 3 else ""
            medal = ["🥇","🥈","🥉"][i] if i < 3 else f"{i+1}"
            body += f'<div class="scorer"><span class="scorer-rank {rank_cls}">{medal}</span><span class="scorer-name">{esc(s["name"])}</span><span class="scorer-team">{esc(s["team"])}</span><span class="scorer-goals">{s["goals"]} goals</span></div>'
    body += '</div>'

    body += adsense("ad-stats-bottom","ad-top")
    return page("Stats — WC26 Hub", body, "stats")

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    DOCS.mkdir(exist_ok=True)
    matches = SCORES.get("matches", [])
    top_scorers = SCORES.get("top_scorers", [])
    groups = STANDINGS.get("groups", [])

    if not matches:
        print("ERROR: No match data. Run the scraper first.", file=sys.stderr)
        sys.exit(1)

    print(f"Building static site: {len(matches)} matches, {len(groups)} groups, {len(top_scorers)} scorers")

    # Homepage
    (DOCS / "index.html").write_text(build_homepage(matches, top_scorers, groups))
    print("  ✓ index.html")

    # Live page
    (DOCS / "live.html").write_text(build_live_page(matches))
    print("  ✓ live.html")

    # Standings
    (DOCS / "standings.html").write_text(build_standings_page(groups))
    print("  ✓ standings.html")

    # Stats
    (DOCS / "stats.html").write_text(build_stats_page(matches, top_scorers))
    print("  ✓ stats.html")

    # Match detail pages
    match_dir = DOCS / "match"
    match_dir.mkdir(exist_ok=True)
    for m in matches:
        (match_dir / f'{m["id"]}.html').write_text(build_match_detail(m))
    print(f"  ✓ {len(matches)} match detail pages")

    # Copy players.json for reference
    import shutil
    shutil.copy2(PLAYERS_FILE, DOCS / "players.json")

    print(f"\nDone! {DOCS}/ is ready for GitHub Pages.")

if __name__ == "__main__":
    main()
