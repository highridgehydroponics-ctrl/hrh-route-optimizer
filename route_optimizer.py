#!/usr/bin/env python3
"""
HRH Daily Route Optimizer Ã¢ÂÂ GitHub Actions Version
Runs daily at 3pm ET (7pm UTC) MonÃ¢ÂÂSat to optimize tomorrow's delivery route.

Replicates the full Cowork skill logic:
  Ã¢ÂÂ¢ AppSheet order fetch Ã¢ÂÂ Saturday FM filter Ã¢ÂÂ WFM pickup filter
  Ã¢ÂÂ¢ Address fallback (geocache Ã¢ÂÂ client table Ã¢ÂÂ Claude API)
  Ã¢ÂÂ¢ Google Geocoding API (cached in data/hrh-geocode-cache.json)
  Ã¢ÂÂ¢ GMPRO route optimization with JW auth
  Ã¢ÂÂ¢ Westport canonical loop ordering
  Ã¢ÂÂ¢ Thursday farm-unload stop (Taner only)
  Ã¢ÂÂ¢ Brooklawn Country Club 1pm departure override
  Ã¢ÂÂ¢ Dashboard HTML generated from assets/dashboard-template.html
  Ã¢ÂÂ¢ Full AppSheet write-back: stop numbers + delivery record + delivery items
  Ã¢ÂÂ¢ Email with route summary + dashboard attachment + GitHub Pages link

Required GitHub Secrets (set in repo Settings Ã¢ÂÂ Secrets Ã¢ÂÂ Actions):
  APPSHEET_APP_ID       bea55701-8006-4581-a791-19a75092943f
  APPSHEET_API_KEY      V2-f4zl4-...
  DELIVERY_APP_ID       f57f33e9-2515-46d3-8394-168d7e834ded
  DELIVERY_API_KEY      V2-pFgDb-...
  GMAP_API_KEY          AIzaSyB3Q0z...
  GCP_SA_KEY_JSON       (full JSON content of the service account key file)
  EMAIL_USER            highridgehydroponics@gmail.com
  EMAIL_PASSWORD        (Gmail app password Ã¢ÂÂ NOT your account password)
"""

import os, sys, json, time, base64, math, re, traceback, smtplib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header
from urllib.parse import quote as urlquote

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
# Constants
# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

EASTERN = ZoneInfo("America/New_York")

# AppSheet Ã¢ÂÂ Orders app
AS_APP_ID  = os.environ["APPSHEET_APP_ID"]
AS_API_KEY = os.environ["APPSHEET_API_KEY"]

# AppSheet Ã¢ÂÂ Deliveries app
DL_APP_ID  = os.environ["DELIVERY_APP_ID"]
DL_API_KEY = os.environ["DELIVERY_API_KEY"]

# Google APIs
GMAP_KEY          = os.environ["GMAP_API_KEY"]
GCP_SA_KEY_JSON   = os.environ["GCP_SA_KEY_JSON"]   # full JSON of service account key

# Claude API (optional Ã¢ÂÂ used for address resolution fallback)
ANTHROPIC_KEY     = os.environ.get("ANTHROPIC_API_KEY", "")

# Email
EMAIL_USER        = os.environ["EMAIL_USER"]
EMAIL_PASSWORD    = os.environ["EMAIL_PASSWORD"]
EMAIL_TO          = os.environ.get("EMAIL_TO", "highridgehydroponics@gmail.com")

# GitHub Pages URL (auto-set by the workflow)
PAGES_URL         = os.environ.get("GITHUB_PAGES_URL", "").rstrip("/")

# File paths (relative to repo root, where the script runs)
GEOCACHE_PATH     = "data/hrh-geocode-cache.json"
HISTORY_PATH      = "data/hrh-route-history.json"
TEMPLATE_PATH     = "assets/dashboard-template.html"
DOCS_DIR          = "docs"

# Farm
FARM_ADDR = "1 1/2 Island Brook Ave, Bridgeport, CT 06606"
FARM_LAT  = 41.1979603
FARM_LNG  = -73.1872799

# Driver defaults
FALLBACK_SCHEDULE = {
    "Monday":    {"driver": "Rene Jimenez", "slug": "rene",  "depart": "4:00 PM"},
    "Tuesday":   {"driver": "Rene Jimenez", "slug": "rene",  "depart": "4:00 PM"},
    "Wednesday": {"driver": "Taner Genc",   "slug": "taner", "depart": "11:00 AM"},
    "Thursday":  {"driver": "Taner Genc",   "slug": "taner", "depart": "8:30 AM"},
    "Friday":    {"driver": "Taner Genc",   "slug": "taner", "depart": "11:30 AM"},
    "Saturday":  {"driver": "Taner Genc",   "slug": "taner", "depart": "8:30 AM"},
    "Sunday":    None,
}

DRIVER_HOMES = {
    "Rene Jimenez": "207 Liberty Square, Norwalk, CT 06854",
    "Joe Alvarez":  "1 Brookwood Dr, Newtown, CT 06470",
    "Taner Genc":   "179 Davis St, Oakville, CT 06779",
}

STAFF_IDS = {
    "Joe Alvarez":  "4aa339f5",
    "Rene Jimenez": "9d3e9108",
    "Taner Genc":   "68969327",
}

VEHICLE_IDS = {
    "Joe Alvarez":  "VEH1ABCD",
    "Rene Jimenez": "VEH3ABCD",
    "Taner Genc":   "VEH4ABCD",   # Thu/Fri/Sat Ã¢ÂÂ VEH1ABCD
}

# driver index for dashboard template (Rene=0, Joe=1, Taner=2)
DRIVER_IDX = {"Rene Jimenez": 0, "Joe Alvarez": 1, "Taner Genc": 2}

# Westport canonical loop
WESTPORT_LOOP = ["Casa Me", "Massi Co", "Nomade", "Hudson Malone", "Oko Westport"]

# Customers that pick up at WFM (not routed as separate stops)
WFM_PICKUP_NAMES = {"the cottage", "herbaceous catering", "sprout juicebar", "sprout juice"}

# Saturday Farmers Market pickup customers (first name match)
SAT_FM_FIRST_NAMES = {"glenn", "stacy", "eric"}

# New Canaan area stops for Thursday precedence rules
NC_AREA_KEYWORDS = ["roger sherman", "chef prasad", "new canaan"]

# Geocode bounding box for Connecticut / Westchester area
LAT_MIN, LAT_MAX = 40.85, 41.75
LNG_MIN, LNG_MAX = -74.15, -72.60
MAX_DIST_MI = 70


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
# Time utilities
# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def t2m(t: str) -> int:
    """Convert '4:00 PM' Ã¢ÂÂ 960 (minutes since midnight)."""
    t = t.strip()
    h, rest = t.split(":")
    m_part, ap = rest.split()
    h = int(h) % 12 + (12 if ap.upper() == "PM" else 0)
    return h * 60 + int(m_part)


def m2t(m: int) -> str:
    """Convert 960 Ã¢ÂÂ '4:00 PM'."""
    m = int(m) % (24 * 60)
    h, mi = divmod(m, 60)
    ap = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{mi:02d} {ap}"


def utc_iso_to_et_mins(utc_str: str) -> int:
    """Convert '2026-05-28T20:00:00Z' Ã¢ÂÂ minutes since midnight Eastern."""
    utc_str = utc_str.replace("Z", "+00:00")
    dt_utc = datetime.fromisoformat(utc_str)
    dt_et = dt_utc.astimezone(EASTERN)
    return dt_et.hour * 60 + dt_et.minute


def tz_offset_str(dt) -> str:
    """Return ÃÂ±HH:MM offset string from a timezone-aware datetime, e.g. '-04:00'."""
    off = dt.utcoffset()
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    h, rem = divmod(abs(total), 3600)
    return f"{sign}{h:02d}:{rem // 60:02d}"


def haversine_mi(lat1, lng1, lat2, lng2) -> float:
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
# AppSheet helpers
# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def _as_post(app_id: str, api_key: str, table: str, body: dict) -> list:
    url = f"https://api.appsheet.com/api/v2/apps/{app_id}/tables/{table}/Action"
    resp = requests.post(
        url,
        headers={"ApplicationAccessKey": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    if resp.status_code == 200 and resp.text.strip():
        try:
            return resp.json()
        except Exception:
            return []
    return []


def as_find(app_id, api_key, table, selector) -> list:
    return _as_post(app_id, api_key, table, {
        "Action": "Find",
        "Properties": {"Locale": "en-US", "Timezone": "US/Eastern", "Selector": selector},
        "Rows": [],
    })


def as_edit(app_id, api_key, table, rows) -> bool:
    url = f"https://api.appsheet.com/api/v2/apps/{app_id}/tables/{table}/Action"
    resp = requests.post(
        url,
        headers={"ApplicationAccessKey": api_key, "Content-Type": "application/json"},
        json={"Action": "Edit", "Properties": {"Locale": "en-US"}, "Rows": rows},
        timeout=30,
    )
    return resp.status_code == 200


def as_add(app_id, api_key, table, rows) -> bool:
    url = f"https://api.appsheet.com/api/v2/apps/{app_id}/tables/{table}/Action"
    resp = requests.post(
        url,
        headers={"ApplicationAccessKey": api_key, "Content-Type": "application/json"},
        json={"Action": "Add", "Properties": {"Locale": "en-US"}, "Rows": rows},
        timeout=30,
    )
    return resp.status_code == 200


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
# Geocode cache
# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def load_cache() -> dict:
    try:
        with open(GEOCACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"addresses": {}, "customers": {}}


def save_cache(cache: dict):
    os.makedirs("data", exist_ok=True)
    with open(GEOCACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def geocode_address(address: str, cache: dict):
    """Return (lat, lng) from cache or Google Geocoding API. Returns (None, None) on failure."""
    if address in cache.get("addresses", {}):
        c = cache["addresses"][address]
        return c["lat"], c["lng"]

    resp = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": address, "key": GMAP_KEY},
        timeout=15,
    )
    data = resp.json()
    if data.get("status") != "OK":
        return None, None

    loc = data["results"][0]["geometry"]["location"]
    lat, lng = loc["lat"], loc["lng"]

    # Validate bounding box
    if not (LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX):
        print(f"  Ã¢ÂÂ Ã¯Â¸Â  Suspicious geocode for '{address}': ({lat}, {lng}) Ã¢ÂÂ out of bounding box")
        return None, None
    if haversine_mi(FARM_LAT, FARM_LNG, lat, lng) > MAX_DIST_MI:
        print(f"  Ã¢ÂÂ Ã¯Â¸Â  Geocode too far from farm ({haversine_mi(FARM_LAT, FARM_LNG, lat, lng):.1f} mi) for '{address}'")
        return None, None

    cache.setdefault("addresses", {})[address] = {"lat": lat, "lng": lng}
    return lat, lng


def resolve_address_via_claude(customer_name: str) -> str | None:
    """Optional: ask Claude API to suggest an address for a customer when all else fails."""
    if not ANTHROPIC_KEY:
        return None
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 100,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"What is the full street address for '{customer_name}' in Connecticut "
                        f"(likely Fairfield County Ã¢ÂÂ Westport, New Canaan, Darien, Greenwich, Stamford, Norwalk area)? "
                        f"Reply with ONLY the address string, nothing else. If unknown, reply: UNKNOWN"
                    ),
                }],
            },
            timeout=15,
        )
        text = resp.json()["content"][0]["text"].strip()
        if text and text != "UNKNOWN" and len(text) > 5:
            return text
    except Exception as e:
        print(f"  Ã¢ÂÂ Ã¯Â¸Â  Claude address lookup failed: {e}")
    return None


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
# Route history
# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def load_history() -> dict:
    try:
        with open(HISTORY_PATH) as f:
            return json.load(f)
    except Exception:
        return {"routes": []}


def save_history(history: dict, record: dict):
    history.setdefault("routes", []).append(record)
    history["routes"] = sorted(history["routes"], key=lambda r: r.get("date", ""))[-180:]
    os.makedirs("data", exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
# GMPRO auth
# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def get_gmpro_bearer() -> str:
    sa = json.loads(GCP_SA_KEY_JSON)
    pk = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
    now = int(time.time())

    hdr = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()

    pay = base64.urlsafe_b64encode(json.dumps({
        "iss": sa["client_email"],
        "scope": "https://www.googleapis.com/auth/cloud-platform",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }).encode()).rstrip(b"=").decode()

    sig_input = f"{hdr}.{pay}".encode()
    sig = base64.urlsafe_b64encode(
        pk.sign(sig_input, padding.PKCS1v15(), hashes.SHA256())
    ).rstrip(b"=").decode()

    jwt = f"{hdr}.{pay}.{sig}"

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=f"grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion={jwt}",
        timeout=20,
    )
    return resp.json()["access_token"]


def call_gmpro(bearer: str, payload: dict) -> dict:
    resp = requests.post(
        "https://routeoptimization.googleapis.com/v1/projects/hrh-route-optimizer:optimizeTours",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {bearer}"},
        json=payload,
        timeout=45,
    )
    return resp.json()


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
# Westport canonical loop
# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def apply_westport_loop(stops: list) -> list:
    """
    If 2+ canonical Westport stops are present, enforce:
      Casa Me Ã¢ÂÂ Massi Co Ã¢ÂÂ Nomade Ã¢ÂÂ Hudson Malone Ã¢ÂÂ Oko Westport
    Preserve GMPRO's entry point; rotate from there.
    Non-canonical Westport stops (Whelk, Allium, etc.) are untouched.
    """
    loop_lower = [n.lower() for n in WESTPORT_LOOP]
    canonical_idxs = [i for i, s in enumerate(stops) if s["name"].lower() in loop_lower]

    if len(canonical_idxs) < 2:
        return stops

    # GMPRO's entry point = first canonical stop in the ordered list
    entry_name = stops[canonical_idxs[0]]["name"].lower()
    entry_pos = loop_lower.index(entry_name)
    rotated = WESTPORT_LOOP[entry_pos:] + WESTPORT_LOOP[:entry_pos]

    # Map canonical stops by name
    present = {stops[i]["name"].lower(): stops[i] for i in canonical_idxs}
    reordered = [present[n.lower()] for n in rotated if n.lower() in present]

    # Replace in-place at canonical positions (order preserved within cluster)
    result = list(stops)
    for list_pos, stop_idx in enumerate(canonical_idxs):
        result[stop_idx] = reordered[list_pos]

    return result


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
# Dashboard HTML generation
# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def generate_dashboard(
    stops: list,
    driver_name: str,
    depart_time: str,
    home_arrival: str,
    total_miles: float,
    route_date: str,    # MM/DD/YYYY
    date_label: str,
    cache: dict,
) -> str:
    """
    Reads assets/dashboard-template.html and substitutes all PLACEHOLDER_ values.
    Returns the completed HTML string.
    """
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        html = f.read()

    driver_idx   = DRIVER_IDX.get(driver_name, 0)
    stop_offset  = 0          # Always 0 for daily run (single route per day)
    depart_mins  = t2m(depart_time)
    home_mins    = t2m(home_arrival)

    # Build stops JS array Ã¢ÂÂ ensure constOpen is always present
    stops_for_js = []
    for s in stops:
        stops_for_js.append({
            "num":         s.get("num", 0),
            "name":        s.get("name", ""),
            "orderNum":    s.get("orderNum"),      # null or "Ã¢ÂÂ"
            "addr":        s.get("addr", ""),
            "lat":         s.get("lat", 0),
            "lng":         s.get("lng", 0),
            "arrive":      s.get("arrive", ""),
            "depart":      s.get("depart", ""),
            "warn":        s.get("warn", False),
            "constraint":  s.get("constraint"),
            "constOpen":   False,
            "id":          s.get("id", ""),        # AppSheet record id
        })

    stops_js   = json.dumps(stops_for_js, ensure_ascii=False)
    cache_js   = json.dumps(cache, ensure_ascii=False)

    html = html.replace("PLACEHOLDER_CACHE_DATA",        cache_js)
    html = html.replace("PLACEHOLDER_STOPS_JSON",        stops_js)
    html = html.replace("PLACEHOLDER_DRIVER_IDX",        str(driver_idx))
    html = html.replace("PLACEHOLDER_STOP_NUM_OFFSET",   str(stop_offset))
    html = html.replace("PLACEHOLDER_DEPART_MINS",       str(depart_mins))
    html = html.replace("PLACEHOLDER_HOME_ARRIVAL_MINS", str(home_mins))
    html = html.replace("PLACEHOLDER_TOTAL_MILES",       str(round(total_miles, 1)))
    html = html.replace("PLACEHOLDER_DATE_LABEL",        date_label)
    html = html.replace("PLACEHOLDER_DEPART_TIME",       depart_time)
    html = html.replace("PLACEHOLDER_ROUTE_DATE",        route_date)
    html = html.replace("PLACEHOLDER_APPSHEET_APP_ID",   AS_APP_ID)
    html = html.replace("PLACEHOLDER_APPSHEET_API_KEY",  AS_API_KEY)
    html = html.replace("PLACEHOLDER_DELIVERY_APP_ID",   DL_APP_ID)
    html = html.replace("PLACEHOLDER_DELIVERY_API_KEY",  DL_API_KEY)

    # Ã¢ÂÂÃ¢ÂÂ Bug fixes (from Cowork skill) Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

    # Fix 1: Leaflet init crash on restricted origins
    OLD_LEAFLET = (
        "const leafletMap = L.map('map').setView([41.14,-73.38],11);\n"
        "L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{\n"
        "  attribution:'&copy; OpenStreetMap &copy; CartoDB',subdomains:'abcd',maxZoom:19\n"
        "}).addTo(leafletMap);"
    )
    NEW_LEAFLET = (
        "let leafletMap = null;\n"
        "try {\n"
        "  leafletMap = L.map('map').setView([41.14,-73.38],11);\n"
        "  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{\n"
        "    attribution:'&copy; OpenStreetMap &copy; CartoDB',subdomains:'abcd',maxZoom:19\n"
        "  }).addTo(leafletMap);\n"
        "} catch(e) {\n"
        "  console.warn('Leaflet map init failed:', e);\n"
        "}"
    )
    if OLD_LEAFLET in html:
        html = html.replace(OLD_LEAFLET, NEW_LEAFLET)

    # Fix 2: drawMap null guard
    OLD_DRAW = "function drawMap() {\n  stopMarkers.forEach(m=>leafletMap.removeLayer(m));"
    NEW_DRAW = "function drawMap() {\n  if (!leafletMap) return;\n  stopMarkers.forEach(m=>leafletMap.removeLayer(m));"
    if OLD_DRAW in html:
        html = html.replace(OLD_DRAW, NEW_DRAW)

    # Fix 3: fetchTodayOrders infinite self-recursion
    html = html.replace("  buildDropdown(); fetchTodayOrders();", "  buildDropdown();")

    # Fix 4: PLACEHOLDER_STOP_NUM_OFFSET fallback via regex (safety net)
    html = re.sub(
        r"const STOP_NUM_OFFSET\s*=\s*PLACEHOLDER_STOP_NUM_OFFSET;",
        f"const STOP_NUM_OFFSET = {stop_offset};",
        html,
    )

    # Fix 5: Python escape artifact Ã¢ÂÂ \\! Ã¢ÂÂ \!
    raw = html.encode("utf-8")
    raw = raw.replace(bytes([0x5C, 0x21]), bytes([0x21]))
    html = raw.decode("utf-8")

    return html


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
# Email
# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def send_email(subject: str, text_body: str, attachment_path: str = None, dashboard_url: str = None):
    btn_html = ""
    if dashboard_url:
        btn_html = (
            f'<p style="margin-top:16px;">'
            f'<a href="{dashboard_url}" style="background:#22d3ee;color:#0f172a;'
            f'font-weight:700;padding:10px 20px;border-radius:6px;text-decoration:none;">'
            f'View Live Dashboard Ã¢ÂÂ</a></p>'
        )

    html_body = f"""
<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  color:#1e293b;max-width:640px;margin:0 auto;padding:24px;">
  <h2 style="color:#0f766e;margin-bottom:4px;">Ã°ÂÂÂ HRH Route Ready</h2>
  <pre style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
    padding:16px;font-size:13px;line-height:1.6;white-space:pre-wrap;
    overflow-x:auto;">{text_body}</pre>
  {btn_html}
  <p style="color:#94a3b8;font-size:11px;margin-top:24px;">
    HRH Route Optimizer ÃÂ· {datetime.now(EASTERN).strftime('%m/%d/%Y %I:%M %p ET')}
  </p>
</body></html>"""

    msg = MIMEMultipart("mixed")
    msg["From"]    = EMAIL_USER
    msg["To"]      = EMAIL_TO
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            fname = os.path.basename(attachment_path)
            part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
            msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASSWORD)
            smtp.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
        print(f"  Ã¢ÂÂ Email sent Ã¢ÂÂ {EMAIL_TO}")
    except Exception as e:
        print(f"  Ã¢ÂÂ Ã¯Â¸Â  Email failed: {e}")


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
# Main
# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def main():
    # Ã¢ÂÂÃ¢ÂÂ Step 0: Determine tomorrow Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    now_et       = datetime.now(EASTERN)
    tomorrow_et  = now_et + timedelta(days=1)
    tomorrow_str = tomorrow_et.strftime("%m/%d/%Y")   # AppSheet format
    day_of_week  = tomorrow_et.strftime("%A")

    print(f"\n{'='*60}")
    print(f"HRH Route Optimizer Ã¢ÂÂ {tomorrow_str} ({day_of_week})")
    print(f"{'='*60}\n")

    # Avoid re-running if a dashboard for tomorrow already exists (idempotency)
    slug_check = f"route-{tomorrow_et.strftime('%Y-%m-%d')}"
    existing = [f for f in os.listdir(DOCS_DIR) if slug_check in f] if os.path.isdir(DOCS_DIR) else []
    if existing and os.environ.get("FORCE_RUN", "").lower() not in ("1", "true", "yes"):
        print(f"  Ã¢ÂÂ¹Ã¯Â¸Â  Dashboard already exists for {tomorrow_str} ({existing[0]}) Ã¢ÂÂ skipping.")
        print("     Set FORCE_RUN=1 to override.")
        return

    # Ã¢ÂÂÃ¢ÂÂ Step 1: Determine driver and depart time Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    history  = load_history()
    same_day = sorted(
        [r for r in history.get("routes", []) if r.get("day_of_week") == day_of_week],
        key=lambda r: r.get("date", ""),
        reverse=True,
    )

    if same_day:
        driver_name = same_day[0]["driver"]
        depart_time = same_day[0]["depart_time"]
        driver_slug = same_day[0].get("driver_slug", same_day[0]["driver"].split()[0].lower())
        print(f"Step 1: Driver from history Ã¢ÂÂ {driver_name} @ {depart_time} ({same_day[0]['date']})")
    else:
        fb = FALLBACK_SCHEDULE.get(day_of_week)
        if not fb:
            msg = f"No deliveries scheduled for {day_of_week} Ã¢ÂÂ exiting."
            print(f"  Ã¢ÂÂ¹Ã¯Â¸Â  {msg}")
            send_email(f"HRH Route Ã¢ÂÂ No Deliveries {tomorrow_str}", msg)
            return
        driver_name = fb["driver"]
        depart_time = fb["depart"]
        driver_slug = fb["slug"]
        print(f"Step 1: Driver from fallback Ã¢ÂÂ {driver_name} @ {depart_time}")

    # Ã¢ÂÂÃ¢ÂÂ Step 2: Fetch orders from AppSheet Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    print(f"\nStep 2: Fetching orders for {tomorrow_str}...")
    orders = as_find(
        AS_APP_ID, AS_API_KEY, "order",
        f'FILTER(order, AND([fulfillment_date] = "{tomorrow_str}", [pickup_or_delivery] = "Delivery"))',
    )

    if not orders:
        msg = f"No delivery orders found for {day_of_week} {tomorrow_str}."
        print(f"  Ã¢ÂÂ¹Ã¯Â¸Â  {msg}")
        send_email(f"HRH Route Ã¢ÂÂ No Deliveries {tomorrow_str}", msg)
        return

    print(f"  Found {len(orders)} order(s)")

    # Ã¢ÂÂÃ¢ÂÂ Pre-process orders: apply filters Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    cache = load_cache()
    raw_stops      = []
    wfm_pickups    = []   # customers who pick up at WFM
    fm_pickups     = []   # Saturday FM pickup customers
    skipped_stops  = []

    for o in orders:
        name     = (o.get("client_name") or o.get("account_name") or "Unknown").strip()
        addr     = (o.get("client_address") or "").strip()
        order_id = o.get("id", "")
        row_num  = o.get("_RowNumber", "")
        name_lc  = name.lower()
        first_lc = name.split()[0].lower() if name.split() else ""

        # Saturday Farmers Market pickup filter
        if day_of_week == "Saturday" and first_lc in SAT_FM_FIRST_NAMES:
            fm_pickups.append({"name": name, "id": order_id, "rowNum": row_num})
            continue

        # WFM pickup filter (substring match so "Herbaceous Catering (pickup @ WFM)" still matches)
        if any(wfm in name_lc for wfm in WFM_PICKUP_NAMES):
            wfm_pickups.append({"name": name, "id": order_id, "rowNum": row_num})
            continue

        raw_stops.append({"name": name, "addr": addr, "id": order_id, "rowNum": row_num})

    # Saturday FM warning if FM not on route
    if day_of_week == "Saturday" and fm_pickups:
        nc_on_route = any("new canaan farmers" in s["name"].lower() for s in raw_stops)
        if not nc_on_route:
            print("  Ã¢ÂÂ Ã¯Â¸Â  Glenn/Stacy/Eric have orders but New Canaan FM not on route Ã¢ÂÂ confirm with Joe")

    # Ã¢ÂÂÃ¢ÂÂ Step 2.5a: Fill missing addresses Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    print("\nStep 2.5a: Resolving missing addresses...")
    for s in raw_stops:
        if s["addr"]:
            continue

        # 1. Check geocache customers section
        if s["name"] in cache.get("customers", {}):
            s["addr"] = cache["customers"][s["name"]]
            print(f"  Ã°ÂÂÂ From geocache: {s['name']} Ã¢ÂÂ {s['addr']}")
            continue

        # 2. Query AppSheet client table
        clients = as_find(AS_APP_ID, AS_API_KEY, "client",
                          f'FILTER(client, [account_name] = "{s["name"]}")')
        if clients:
            a = (clients[0].get("address") or clients[0].get("client_address") or "").strip()
            if a:
                s["addr"] = a
                print(f"  Ã°ÂÂÂ From client table: {s['name']} Ã¢ÂÂ {a}")
                continue

        # 3. Try first+last name split
        parts = s["name"].split(None, 1)
        if len(parts) == 2:
            clients2 = as_find(AS_APP_ID, AS_API_KEY, "client",
                               f'FILTER(client, AND([first_name] = "{parts[0]}", [last_name] = "{parts[1]}"))')
            if clients2:
                a = (clients2[0].get("address") or clients2[0].get("client_address") or "").strip()
                if a:
                    s["addr"] = a
                    print(f"  Ã°ÂÂÂ From client table (name split): {s['name']} Ã¢ÂÂ {a}")
                    continue

        # 4. Optional Claude API fallback
        a = resolve_address_via_claude(s["name"])
        if a:
            s["addr"] = a
            print(f"  Ã°ÂÂÂ From Claude: {s['name']} Ã¢ÂÂ {a}")
            continue

        # No address found
        skipped_stops.append(s["name"])
        print(f"  Ã¢ÂÂ Ã¯Â¸Â  No address found Ã¢ÂÂ skipping: {s['name']}")

    raw_stops = [s for s in raw_stops if s["addr"]]

    # Ã¢ÂÂÃ¢ÂÂ Brooklawn Country Club departure override Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    if any("brooklawn" in s["name"].lower() for s in raw_stops):
        depart_time = "1:00 PM"
        print(f"\n  Ã°ÂÂÂÃ¯Â¸Â  Brooklawn Country Club on route Ã¢ÂÂ overriding depart Ã¢ÂÂ 1:00 PM")

    if not raw_stops:
        print("  Ã¢ÂÂ No routable stops after address resolution.")
        return

    # Ã¢ÂÂÃ¢ÂÂ Step 3: Geocode all addresses Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    print(f"\nStep 3: Geocoding {len(raw_stops)} stops...")
    all_addrs = [FARM_ADDR, DRIVER_HOMES[driver_name]] + [s["addr"] for s in raw_stops]
    new_geocodes = 0

    for addr in all_addrs:
        if addr and addr not in cache.get("addresses", {}):
            lat, lng = geocode_address(addr, cache)
            if lat:
                new_geocodes += 1

    # Update customer name Ã¢ÂÂ address mapping
    for s in raw_stops:
        if s["addr"]:
            cache.setdefault("customers", {})[s["name"]] = s["addr"]

    save_cache(cache)
    if new_geocodes:
        print(f"  Ã°ÂÂÂ¾ {new_geocodes} new address(es) added to geocache")

    # Attach lat/lng; drop stops that fail geocoding
    valid_stops = []
    for s in raw_stops:
        coords = cache.get("addresses", {}).get(s["addr"])
        if coords:
            s["lat"] = coords["lat"]
            s["lng"] = coords["lng"]
            valid_stops.append(s)
        else:
            skipped_stops.append(s["name"])
            print(f"  Ã¢ÂÂ Ã¯Â¸Â  Geocode failed Ã¢ÂÂ skipping: {s['name']} ({s['addr']})")

    if not valid_stops:
        print("  Ã¢ÂÂ No geocodable stops Ã¢ÂÂ exiting.")
        return

    print(f"  Ã¢ÂÂ {len(valid_stops)} stops geocoded")

    # Ã¢ÂÂÃ¢ÂÂ Step 4: Build and call GMPRO Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    print(f"\nStep 4: Calling GMPRO with {len(valid_stops)} stops...")

    farm_coords = cache.get("addresses", {}).get(FARM_ADDR, {"lat": FARM_LAT, "lng": FARM_LNG})
    home_coords = cache.get("addresses", {}).get(DRIVER_HOMES.get(driver_name, ""), {"lat": FARM_LAT, "lng": FARM_LNG})

    depart_mins  = t2m(depart_time)
    depart_h, depart_m = divmod(depart_mins, 60)
    tz_str = tz_offset_str(tomorrow_et)
    date_str = tomorrow_et.strftime("%Y-%m-%d")

    global_start = f"{date_str}T{depart_h:02d}:{depart_m:02d}:00{tz_str}"
    global_end   = f"{date_str}T20:00:00{tz_str}"

    # Build shipments list
    shipments        = []
    nc_area_indices  = []
    shelton_idx      = None
    is_thursday_taner = day_of_week == "Thursday" and driver_name == "Taner Genc"

    wfm_on_route = any(
        "westport farmers market" in s["name"].lower() or s["name"].lower() == "wfm"
        for s in valid_stops
    )

    for i, s in enumerate(valid_stops):
        name_lc  = s["name"].lower()
        is_wfm   = "westport farmers market" in name_lc or name_lc == "wfm"
        duration = "1800s" if is_wfm else "300s"

        shipments.append({
            "deliveries": [{
                "arrivalLocation": {"latitude": s["lat"], "longitude": s["lng"]},
                "duration": duration,
            }],
            "label": s["name"],
        })

        if is_thursday_taner:
            if any(kw in name_lc for kw in NC_AREA_KEYWORDS):
                nc_area_indices.append(i)
            if "marketplace" in name_lc and "shelton" in name_lc:
                shelton_idx = i

    # Thursday farm-unload stop (Taner only)
    precedence_rules = []
    farm_unload_shipment_idx = None

    if is_thursday_taner:
        farm_unload_shipment_idx = len(shipments)
        shipments.append({
            "deliveries": [{
                "arrivalLocation": {"latitude": FARM_LAT, "longitude": FARM_LNG},
                "duration": "300s",
            }],
            "label": "Farm Ã¢ÂÂ Unload",
        })
        for nc_i in nc_area_indices:
            precedence_rules.append({
                "firstIndex": nc_i, "secondIndex": farm_unload_shipment_idx,
                "firstIsDelivery": True, "secondIsDelivery": True, "offsetDuration": "0s",
            })
        if shelton_idx is not None:
            precedence_rules.append({
                "firstIndex": farm_unload_shipment_idx, "secondIndex": shelton_idx,
                "firstIsDelivery": True, "secondIsDelivery": True, "offsetDuration": "0s",
            })

    gmpro_payload = {
        "timeout": "30s",
        "considerRoadTraffic": True,
        "model": {
            "globalStartTime": global_start,
            "globalEndTime":   global_end,
            "shipments": shipments,
            "vehicles": [{
                "startLocation": {"latitude": farm_coords["lat"], "longitude": farm_coords["lng"]},
                "endLocation":   {"latitude": home_coords["lat"], "longitude": home_coords["lng"]},
                "costPerKilometer": 1,
                "costPerHour": 15,
            }],
        },
    }

    if precedence_rules:
        gmpro_payload["model"]["precedenceRules"] = precedence_rules

    bearer       = get_gmpro_bearer()
    gmpro_result = call_gmpro(bearer, gmpro_payload)

    if "error" in gmpro_result:
        raise RuntimeError(f"GMPRO error: {gmpro_result['error']}")
    if not gmpro_result.get("routes"):
        raise RuntimeError("GMPRO returned no routes")

    # Ã¢ÂÂÃ¢ÂÂ Step 5: Parse GMPRO response Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    print("\nStep 5: Parsing GMPRO response...")
    route    = gmpro_result["routes"][0]
    visits   = route.get("visits", [])
    metrics  = route.get("metrics", {})

    total_miles   = metrics.get("totalDistanceMeters", 0) * 0.000621371
    vehicle_end   = route.get("vehicleEndTime", "")

    # Build ordered stop list
    ordered_stops     = []
    num_regular_stops = 0

    for visit in visits:
        ship_idx   = visit.get("shipmentIndex", 0)
        start_utc  = visit.get("startTime", "")
        arrive_mins = utc_iso_to_et_mins(start_utc) if start_utc else depart_mins

        # Identify if this is the Farm Ã¢ÂÂ Unload internal stop
        is_farm_unload = (ship_idx == farm_unload_shipment_idx)

        if is_farm_unload:
            stop_data = {
                "name":    "Farm Ã¢ÂÂ Unload",
                "addr":    FARM_ADDR,
                "lat":     FARM_LAT,
                "lng":     FARM_LNG,
                "id":      "",
                "rowNum":  "",
                "orderNum": "Ã¢ÂÂ",
            }
            dwell_mins = 5
        else:
            orig      = valid_stops[ship_idx] if ship_idx < len(valid_stops) else valid_stops[-1]
            stop_data = orig.copy()
            stop_data["orderNum"] = None

            is_wfm = "westport farmers market" in orig["name"].lower() or orig["name"].lower() == "wfm"
            dwell_mins = 330 if is_wfm else 5    # 5h 30min or 5 min
            num_regular_stops += 1

        seq_num = len([s for s in ordered_stops if s.get("orderNum") != "Ã¢ÂÂ"]) + 1 if not is_farm_unload else 0
        depart_stop_mins = arrive_mins + dwell_mins

        ordered_stops.append({
            "num":        seq_num,
            "name":       stop_data["name"],
            "orderNum":   stop_data.get("orderNum"),
            "addr":       stop_data.get("addr", ""),
            "lat":        stop_data.get("lat", 0),
            "lng":        stop_data.get("lng", 0),
            "arrive":     m2t(arrive_mins),
            "depart":     m2t(depart_stop_mins),
            "id":         stop_data.get("id", ""),
            "rowNum":     stop_data.get("rowNum", ""),
            "warn":       False,
            "constraint": None,
        })

    # Home arrival = vehicleEndTime + (num_regular_stops ÃÂ 5 min)
    if vehicle_end:
        home_mins = utc_iso_to_et_mins(vehicle_end) + num_regular_stops * 5
    else:
        home_mins = depart_mins + 180   # fallback

    home_arrival_str = m2t(home_mins)

    # Ã¢ÂÂÃ¢ÂÂ Add WFM pickup sub-entries Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    if wfm_on_route and wfm_pickups:
        wfm_i = next((i for i, s in enumerate(ordered_stops)
                      if "westport farmers market" in s["name"].lower()), None)
        if wfm_i is not None:
            wfm_num = ordered_stops[wfm_i]["num"]
            for p in reversed(wfm_pickups):
                ordered_stops.insert(wfm_i + 1, {
                    "num": wfm_num, "name": f"{p['name']} (pickup @ WFM)",
                    "orderNum": None, "addr": ordered_stops[wfm_i]["addr"], "lat": ordered_stops[wfm_i]["lat"], "lng": ordered_stops[wfm_i]["lng"],                    "arrive": ordered_stops[wfm_i]["arrive"],
                    "depart": ordered_stops[wfm_i]["depart"],
                    "id": p["id"], "rowNum": p["rowNum"],
                    "warn": False, "constraint": None,
                })
    elif wfm_pickups and not wfm_on_route:
        print("  Ã¢ÂÂ Ã¯Â¸Â  WFM pickup customers present but WFM not on route Ã¢ÂÂ flag for Joe")

    # Ã¢ÂÂÃ¢ÂÂ Add Saturday FM pickup sub-entries Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    if day_of_week == "Saturday" and fm_pickups:
        nc_i = next((i for i, s in enumerate(ordered_stops)
                     if "new canaan farmers" in s["name"].lower()), None)
        if nc_i is not None:
            nc_num = ordered_stops[nc_i]["num"]
            for p in reversed(fm_pickups):
                ordered_stops.insert(nc_i + 1, {
                    "num": nc_num, "name": f"{p['name']} (pickup @ New Canaan FM)",
                        "orderNum": None, "addr": ordered_stops[nc_i]["addr"], "lat": ordered_stops[nc_i]["lat"], "lng": ordered_stops[nc_i]["lng"],                    "arrive": ordered_stops[nc_i]["arrive"],
                    "depart": ordered_stops[nc_i]["depart"],
                    "id": p["id"], "rowNum": p["rowNum"],
                    "warn": False, "constraint": None,
                })

    # Ã¢ÂÂÃ¢ÂÂ Step 6.5: Westport canonical loop Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    ordered_stops = apply_westport_loop(ordered_stops)

    print(f"  Ã¢ÂÂ {num_regular_stops} stops ÃÂ· ~{total_miles:.1f} mi ÃÂ· "
          f"depart {depart_time} Ã¢ÂÂ home ~{home_arrival_str}")

    # Ã¢ÂÂÃ¢ÂÂ Step 7: Google Maps directions link Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    map_addrs = [FARM_ADDR] + [
        s["addr"] for s in ordered_stops
        if s.get("orderNum") != "Ã¢ÂÂ" and s.get("addr")
        and "(pickup @" not in s["name"]
    ]
    maps_url = "https://www.google.com/maps/dir/" + "/".join(urlquote(a) for a in map_addrs)

    # Ã¢ÂÂÃ¢ÂÂ Step 8: Generate dashboard Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    print("\nStep 8: Generating dashboard...")
    n_stops_label = sum(1 for s in ordered_stops if s.get("orderNum") != "Ã¢ÂÂ" and "(pickup @" not in s["name"])
    date_label    = f"{tomorrow_et.strftime('%a').upper()} {tomorrow_et.strftime('%b %d').upper()} ÃÂ· {n_stops_label} STOPS"

    dashboard_html = generate_dashboard(
        stops        = ordered_stops,
        driver_name  = driver_name,
        depart_time  = depart_time,
        home_arrival = home_arrival_str,
        total_miles  = total_miles,
        route_date   = tomorrow_str,
        date_label   = date_label,
        cache        = cache,
    )

    os.makedirs(DOCS_DIR, exist_ok=True)
    dashboard_filename = f"route-{tomorrow_et.strftime('%Y-%m-%d')}-{driver_slug}.html"
    dashboard_path     = os.path.join(DOCS_DIR, dashboard_filename)
    index_path         = os.path.join(DOCS_DIR, "index.html")

    with open(dashboard_path, "w", encoding="utf-8") as f:
        f.write(dashboard_html)
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(dashboard_html)

    print(f"  Ã¢ÂÂ Dashboard saved: {dashboard_path}")

    # Ã¢ÂÂÃ¢ÂÂ Step 8.8: Write back to AppSheet Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    print("\nStep 8.8: Writing to AppSheet...")
    now_str = datetime.now().strftime("%m/%d/%Y %H:%M:%S")

    # 8.8a Ã¢ÂÂ Stop numbers
    stop_rows = []
    for s in ordered_stops:
        if s.get("orderNum") == "Ã¢ÂÂ":
            continue
        if "(pickup @" in s.get("name", ""):
            continue
        if not s.get("rowNum") or not s.get("id"):
            continue
        stop_rows.append({
            "_RowNumber":   str(s["rowNum"]),
            "stop_number":  str(s["num"]),
        })

    if stop_rows:
        ok = as_edit(AS_APP_ID, AS_API_KEY, "order", stop_rows)
        print(f"  {'Ã¢ÂÂ' if ok else 'Ã¢ÂÂ'} Stop numbers written Ã¢ÂÂ {len(stop_rows)} order(s)")
    else:
        print("  Ã¢ÂÂ Ã¯Â¸Â  No stop rows to write (missing rowNum/id?)")

    # 8.8b Ã¢ÂÂ Create delivery record
    dt_obj = datetime.strptime(depart_time, "%I:%M %p")
    sched_time_str = dt_obj.strftime("%H:%M:%S")
    order_ids = ", ".join(
        s["id"] for s in ordered_stops
        if s.get("orderNum") != "Ã¢ÂÂ"
        and "(pickup @" not in s.get("name", "")
        and s.get("id")
    )

    staff_id   = STAFF_IDS.get(driver_name, "")
    vehicle_id = (
        "VEH1ABCD"
        if driver_name == "Taner Genc" and day_of_week in {"Thursday", "Friday", "Saturday"}
        else VEHICLE_IDS.get(driver_name, "VEH1ABCD")
    )

    delivery_row = {
        "scheduled_date":     tomorrow_str,
        "scheduled_time":     sched_time_str,
        "staff":              staff_id,
        "vehicle":            vehicle_id,
        "actual_date":        "",
        "actual_time":        "",
        "status":             "Scheduled",
        "load_tracking_type": "Orders",
        "orders":             order_ids,
        "starting_mileage":   "0",
        "ending_mileage":     "0",
        "starting_cash":      "0",
        "ending_cash":        "0",
        "created_by":         "joe@highridgehydroponics.com",
        "modified_by":        "joe@highridgehydroponics.com",
        "trigger":            f"RouteOptimizer-GH | joe@highridgehydroponics.com | {now_str}",
    }
    ok = as_add(DL_APP_ID, DL_API_KEY, "delivery", [delivery_row])
    print(f"  {'Ã¢ÂÂ' if ok else 'Ã¢ÂÂ'} Delivery record created")

    # 8.8c Ã¢ÂÂ Find new delivery record ID
    time.sleep(2)
    delivery_records = as_find(DL_APP_ID, DL_API_KEY, "delivery",
        f'FILTER(delivery, AND([scheduled_date] = "{tomorrow_str}", [staff] = "{staff_id}"))')

    delivery_id = None
    if delivery_records:
        delivery_records.sort(key=lambda r: int(r.get("_RowNumber", 0) or 0), reverse=True)
        delivery_id = delivery_records[0].get("id")
        print(f"  Ã¢ÂÂ Delivery ID: {delivery_id}")
    else:
        print("  Ã¢ÂÂ Ã¯Â¸Â  Could not retrieve delivery record ID")

    # 8.8d Ã¢ÂÂ Create delivery items
    if delivery_id:
        item_rows = []
        sorter = 1
        for s in ordered_stops:
            if s.get("orderNum") == "Ã¢ÂÂ":
                continue
            if "(pickup @" in s.get("name", ""):
                continue
            if not s.get("id"):
                continue
            item_rows.append({
                "delivery":    delivery_id,
                "order":       s["id"],
                "status":      "Pending",
                "sorter":      str(sorter),
                "order_items": "",
                "reserve_1":   "0",
                "created_by":  "joe@highridgehydroponics.com",
                "modified_by": "joe@highridgehydroponics.com",
                "created_at":  now_str,
                "modified_at": now_str,
                "trigger":     f"RouteOptimizer-GH | joe@highridgehydroponics.com | {now_str}",
            })
            sorter += 1

        if item_rows:
            ok = as_add(DL_APP_ID, DL_API_KEY, "delivery_item", item_rows)
            print(f"  {'Ã¢ÂÂ' if ok else 'Ã¢ÂÂ'} {len(item_rows)} delivery item(s) created")

    # Ã¢ÂÂÃ¢ÂÂ Update route history Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    save_history(history, {
        "date":        tomorrow_str,
        "day_of_week": day_of_week,
        "driver":      driver_name,
        "driver_slug": driver_slug,
        "depart_time": depart_time,
        "stops":       num_regular_stops,
        "miles":       round(total_miles, 1),
    })
    print("\n  Ã¢ÂÂ Route history updated")

    # Ã¢ÂÂÃ¢ÂÂ Build summary text for email Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    summary_lines = [
        f"Driver:       {driver_name}",
        f"Date:         {day_of_week} {tomorrow_str}",
        f"Depart farm:  {depart_time}",
        f"Home ~:       {home_arrival_str}",
        f"Stops:        {num_regular_stops}",
        f"Est. miles:   {total_miles:.1f}",
        "",
        "Ã¢ÂÂ" * 48,
    ]

    for s in ordered_stops:
        if s.get("orderNum") == "Ã¢ÂÂ":
            summary_lines.append(f"  Ã¢ÂÂ {s['name']}  ({s.get('arrive','')})")
        elif "(pickup @" in s.get("name", ""):
            summary_lines.append(f"    Ã¢ÂÂ {s['name']}")
        else:
            summary_lines.append(f"\n  Stop {s['num']:>2}: {s['name']}")
            if s.get("addr"):
                summary_lines.append(f"           {s['addr']}")
            summary_lines.append(f"           {s.get('arrive','')} Ã¢ÂÂ {s.get('depart','')}")

    if skipped_stops:
        summary_lines += ["", "Ã¢ÂÂ Ã¯Â¸Â  Skipped stops (no address):"] + [f"  Ã¢ÂÂ¢ {n}" for n in skipped_stops]

    summary_lines.append(f"\nÃ°ÂÂÂºÃ¯Â¸Â  Maps: {maps_url}")
    summary_text = "\n".join(summary_lines)

    # Ã¢ÂÂÃ¢ÂÂ Send email Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    print("\nSending email...")
    dashboard_url = f"{PAGES_URL}/{dashboard_filename}" if PAGES_URL else None
    send_email(
        subject       = f"Ã°ÂÂÂ HRH Route Ã¢ÂÂ {day_of_week} {tomorrow_str} ÃÂ· {driver_name} ÃÂ· {num_regular_stops} stops",
        text_body     = summary_text,
        attachment_path = dashboard_path,
        dashboard_url = dashboard_url,
    )

    # Ã¢ÂÂÃ¢ÂÂ Final summary Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
    print(f"\n{'='*60}")
    print(f"Ã¢ÂÂ Route optimizer complete!")
    print(f"   {day_of_week} {tomorrow_str} ÃÂ· {driver_name} ÃÂ· {num_regular_stops} stops ÃÂ· ~{total_miles:.1f} mi")
    print(f"   Depart {depart_time} Ã¢ÂÂ Home ~{home_arrival_str}")
    if dashboard_url:
        print(f"   Dashboard: {dashboard_url}")
    print(f"{'='*60}\n")


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nÃ¢ÂÂ Route optimizer failed: {exc}\n")
        traceback.print_exc()
        # Send failure email so Joe knows something went wrong
        try:
            send_email(
                subject   = "Ã¢ÂÂ HRH Route Optimizer Failed",
                text_body = f"The route optimizer encountered an error:\n\n{exc}\n\n{traceback.format_exc()}",
            )
        except Exception:
            pass
        sys.exit(1)
