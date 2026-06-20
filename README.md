# ⚽ WC26 Hub — World Cup 2026 Match Tracker

Live match tracker for FIFA World Cup 2026 (USA · Canada · Mexico). Features real-time scores, standings, player stats, top scorers, match timeline, and a retro arcade aesthetic with an animated soccer field hero.

**Live demo:** [your-domain.com](#) *(replace with your URL)*

![Retro arcade design with animated pitch](https://via.placeholder.com/800x400/111/0f0?text=WC26+Hub)

## Features

- **Live Match Center** — All 72 group stage matches with auto-refresh, filter by LIVE/FINISHED/UPCOMING
- **Animated Hero** — Canvas-based soccer field showing real players from the latest match passing the ball
- **Match Detail Pages** — Full stats (possession, shots, xG, passes), timeline events, player ratings
- **Standings** — Group tables with qualification indicators
- **Top Scorers** — Aggregated from match player data
- **Auto Timezone** — All kickoff times convert to the visitor's local timezone via JS
- **AdSense Ready** — 11 ad slots across all pages with placeholder styling
- **Affiliate Rail** — Product showcase section on homepage and match detail pages
- **Mobile First** — Responsive with hamburger menu, touch-friendly filters
- **Self-Contained** — Single `server.py` file, background scraper, no external DB needed

## Tech Stack

- **Backend:** Python 3.11+ / FastAPI / uvicorn
- **HTTP Client:** aiohttp (for scraping worldcup26.ir API)
- **Frontend:** Vanilla JS + CSS (no frameworks, no build step)
- **Timezone:** Python `zoneinfo` (IANA) → UTC → JS `Intl.DateTimeFormat` for local display
- **Data:** Scraped every 120s from worldcup26.ir, cached in `output/live_scores.json`

## Quick Start

### Prerequisites

- Python 3.11+
- pip or uv

### Install & Run

```bash
# Clone the repo
git clone https://github.com/controlForge/wc26-hub.git
cd wc26-hub

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install fastapi uvicorn aiohttp

# Run the server
python3 -c "from server import app; import uvicorn; uvicorn.run(app, host='0.0.0.0', port=8000)"
```

Visit `http://localhost:8000` — the scraper runs on startup and every 2 minutes after.

### Dependencies

```
fastapi>=0.100.0
uvicorn>=0.20.0
aiohttp>=3.9.0
```

Python 3.11+ includes `zoneinfo` stdlib — no extra package needed.

---

## 🚀 Free Hosting Options

### Option 1: Oracle Cloud Free Tier (Recommended — Always Free)

Oracle Cloud offers an **always-free** VM with 1GB RAM — enough for this app.

**Steps:**

1. Sign up at [cloud.oracle.com/free](https://cloud.oracle.com/free)
2. Create an **Ampere A1** instance (ARM, always free):
   - Shape: `VM.Standard.A1.Flex`
   - OCPUs: 1, Memory: 6GB (or minimum 1GB)
   - Image: Ubuntu 22.04 or 24.04
3. In the VCN security list, open ports **22** (SSH) and **80/443** (HTTP/HTTPS)
4. SSH in and set up:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11+
sudo apt install python3.11 python3.11-venv -y

# Clone and set up
git clone https://github.com/controlForge/wc26-hub.git
cd wc26-hub
python3.11 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn aiohttp

# Run with systemd for auto-restart
sudo tee /etc/systemd/system/wc26.service << 'EOF'
[Unit]
Description=WC26 Hub
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/wc26-hub
ExecStart=/home/ubuntu/wc26-hub/.venv/bin/python3 -c "from server import app; import uvicorn; uvicorn.run(app, host='0.0.0.0', port=8000, log_level='warning')"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable wc26
sudo systemctl start wc26
```

5. Your site is now live at `http://<VM_PUBLIC_IP>:8000`

**To use port 80 instead of 8000:**
```bash
# Option A: Run on port 80 directly (change port=8000 to port=80 in the service file)
# Option B: Use nginx as reverse proxy (recommended for HTTPS later)
sudo apt install nginx -y
sudo tee /etc/nginx/sites-available/wc26 << 'EOF'
server {
    listen 80;
    server_name _;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF
sudo ln -s /etc/nginx/sites-available/wc26 /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
```

### Option 2: Render.com (Free Tier)

1. Push to GitHub (already done)
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo
4. Settings:
   - **Runtime:** Python 3
   - **Build Command:** `pip install fastapi uvicorn aiohttp`
   - **Start Command:** `python3 -c "from server import app; import uvicorn; uvicorn.run(app, host='0.0.0.0', port=10000, log_level='warning')"`
   - **Instance Type:** Free
5. Render auto-deploys on every push

> ⚠️ Render free tier spins down after 15min inactivity. First request after idle takes ~30s to wake up.

### Option 3: Railway.app

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Add a `Procfile` in repo root:
   ```
   web: python3 -c "from server import app; import uvicorn; uvicorn.run(app, host='0.0.0.0', port=\${PORT:-8000}, log_level='warning')"
   ```
3. Railway auto-detects Python and installs from a `requirements.txt`

### Option 4: PythonAnywhere

1. Sign up at [pythonanywhere.com](https://pythonanywhere.com) (free tier available)
2. Upload files or clone from GitHub
3. Create a virtual env and install dependencies
4. Configure WSGI to point to the FastAPI app

---

## 🔗 Connecting a Custom Domain

### If hosting on Oracle Cloud (or any VPS):

**Step 1 — Buy a domain** (if you don't have one):
- [Namecheap](https://namecheap.com) (~$5-10/year for .com)
- [Cloudflare Registrar](https://cloudflare.com/products/registrar/) (at-cost pricing)
- [Porkbun](https://porkbun.com) (cheap, good UI)

**Step 2 — Point DNS to your server:**

In your domain registrar's DNS settings, create:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | @ | `<YOUR_VM_IP>` | 300 |
| A | www | `<YOUR_VM_IP>` | 300 |

**Step 3 — Update server to accept the domain:**

In `server.py`, the server binds to `0.0.0.0` so it accepts all hosts. If using nginx, update `server_name`:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    ...
}
```

**Step 4 — Add HTTPS with Let's Encrypt (free):**

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d yourdomain.com -d www.ydomain.com
# Certbot auto-configures nginx and sets up auto-renewal
```

### If hosting on Render/Railway:

Both offer free custom domains with automatic HTTPS:
- **Render:** Dashboard → your service → Settings → Custom Domain
- **Railway:** Project → Settings → Domains

---

## 💰 Setting Up Google AdSense

The site has **11 ad slots** across 5 pages, each with a unique `id`:

| Page | Ad Slot ID | Location |
|------|-----------|----------|
| Home | `ad-home-hero` | Below hero |
| Home | `ad-home-nav` | Below quick nav |
| Home | `ad-home-matches` | Below match grid |
| Home | `ad-home-bottom` | Below standings/scorers |
| Live | `ad-live-filter` | Below filter tabs |
| Live | `ad-live-bottom` | Below match grid |
| Match Detail | `ad-match-top` | Below tabs |
| Match Detail | `ad-match-bottom` | Below content |
| Standings | `ad-standings` | Below group tables |
| Stats | `ad-stats-top` | Below header |
| Stats | `ad-stats-bottom` | Below content |

### Step 1 — Get AdSense Approval

1. Go to [google.com/adsense](https://google.com/adsense)
2. Sign in with your Google account
3. Add your site URL
4. AdSense will give you a code snippet to add to your site
5. Wait for approval (usually 1-3 days for a new site)

### Step 2 — Replace Placeholders with Real Ad Code

Once approved, AdSense gives you a script like:

```html
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-XXXXXXXXXXXXXXXX" crossorigin="anonymous"></script>
```

**Replace the ad helper in `server.py`:**

Find the `adsense()` function (around line 330) and update it:

```python
def adsense(slot_id, css_class=""):
    return f'''<div class="ad-slot {css_class}" id="{slot_id}">
  <ins class="adsbygoogle"
       style="display:block"
       data-ad-client="ca-pub-YOUR_PUBLISHER_ID"
       data-ad-slot="YOUR_SLOT_ID"
       data-ad-format="auto"
       data-full-width-responsive="true"></ins>
  <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
</div>'''
```

**Also add the AdSense `<script>` to the `<head>` in the `page()` function:**

```python
<head>
  ...
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-YOUR_PUBLISHER_ID" crossorigin="anonymous"></script>
</head>
```

### Step 3 — Create Ad Units in AdSense Dashboard

1. In AdSense → Ads → By site → New ad unit
2. Choose display type (Display, In-article, In-feed)
3. Give it a name matching the slot (e.g. "Home Hero")
4. Copy the **data-ad-slot** ID and map it to the corresponding `slot_id` in the code

### Ad Placement Tips

- **Above the fold:** `ad-home-hero` and `ad-home-nav` get the most impressions
- **Between content:** `ad-home-matches` and `ad-live-bottom` perform well
- **Avoid too many ads above the fold** — Google penalizes this
- The current layout follows AdSense policies (no more than 3 ads per page visible at once)

---

## 🛒 Setting Up Affiliate Links

The site has an **affiliate product rail** on the homepage and match detail pages with 6 World Cup products.

### Current Products

| Product | Placeholder Link |
|---------|-----------------|
| FIFA 24 PS5 | `#` |
| Nike Mercurial Boots | `#` |
| Predator Gloves | `#` |
| Official Match Ball | `#` |
| Argentina Jersey | `#` |
| Nike Backpack | `#` |

### Step 1 — Join Affiliate Programs

**Amazon Associates** (easiest for physical products):
1. Go to [affiliate-program.amazon.com](https://affiliate-program.amazon.com)
2. Sign up with your Amazon account
3. Get your tracking ID (e.g. `yourname-20`)
4. Search for products and generate affiliate links

**Other programs:**
- **Nike Affiliate Program** — via [Impact](https://impact.com) or [Rakuten](https://rakutenadvertising.com)
- **FIFA/EA Sports** — via [Impact](https://impact.com)
- **Fanatics** — [fanatics.com/affiliates](https://www.fanatics.com) (jerseys, merch)
- **Pro:Direct Soccer** — [prodirectsoccer.com](https://www.prodirectsoccer.com) (boots, balls)

### Step 2 — Update the Affiliate Rail

Find the `affiliate_rail()` function in `server.py` (around line 340) and replace the placeholder links:

```python
def affiliate_rail(title="World Cup Gear"):
    products = [
        ("FIFA 24 PS5", "https://amzn.to/YOUR_AMAZON_LINK", "🎮"),
        ("Nike Mercurial Boots", "https://amzn.to/YOUR_AMAZON_LINK", "👟"),
        ("Predator Gloves", "https://amzn.to/YOUR_AMAZON_LINK", "🧤"),
        ("Official Match Ball", "https://amzn.to/YOUR_AMAZON_LINK", "⚽"),
        ("Argentina Jersey", "https://amzn.to/YOUR_AMAZON_LINK", "👕"),
        ("Nike Backpack", "https://amzn.to/YOUR_AMAZON_LINK", "🎒"),
    ]
    html = f'<div class="affiliate-sect">▸▸ {title}</div><div class="affiliate-rail">'
    for name, url, icon in products:
        html += f'<a href="{url}" class="affiliate-card" target="_blank" rel="sponsored nofollow"><div class="affiliate-icon">{icon}</div><div class="affiliate-name">{name}</div><div class="affiliate-cta">SHOP →</div></a>'
    html += '</div>'
    return html
```

### Step 3 — Disclose Affiliate Links

Add a disclosure to the footer (required by FTC and most affiliate programs):

```html
<div class="footer">
  WC26 HUB · DATA: WORLDUP26.IR · NOT AFFILIATED WITH FIFA · BUILT WITH ⚽ AND ☕
  <br><small>Some links are affiliate links. We may earn a commission at no extra cost to you.</small>
</div>
```

### Affiliate Best Practices

- **Always use `rel="sponsored nofollow"`** on affiliate links (already in the code)
- **Don't cloak links** — be transparent
- **Place affiliate rails near relevant content** (match detail pages convert better)
- **Update products seasonally** — swap in trending items during knockout rounds
- **Track performance** — most dashboards show clicks, conversions, and earnings

---

## 📁 Project Structure

```
wc26-hub/
├── server.py          # Main server — FastAPI app, scraper, all HTML templates
├── players.json       # 48 teams, 13-15 real players each (670+ total)
├── output/            # Auto-generated data cache (created on first run)
│   ├── live_scores.json   # Match data, updated every 120s
│   └── standings.json     # Group standings
├── .gitignore
└── README.md
```

## 🔧 Configuration

Key settings at the top of `server.py`:

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE` | `https://worldcup26.ir` | API base URL |
| Scraper interval | 120s | Background thread sleep in `_scraper_loop()` |
| Port | 8000 | Change in `uvicorn.run()` call |

## 📝 License

MIT — use it, modify it, monetize it. Just don't claim you built it from scratch.

---

**Built with ⚽ and ☕ by controlForge**
