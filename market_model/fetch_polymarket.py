"""Fetch Polymarket 2026 race markets (winner + margin-of-victory) and resolved
2024/2025 markets with daily price history. Uses curl (Polymarket's CLOB blocks
the default Python client). Saves raw JSON under raw/."""
import csv, json, subprocess, sys, time, re, os, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
RACES = os.path.join(HERE, "..", "data (1)", "races_2026.csv")
G = "https://gamma-api.polymarket.com"
C = "https://clob.polymarket.com"

def curl(url, tries=3):
    for i in range(tries):
        out = subprocess.run(["curl", "-s", "--max-time", "30", url], capture_output=True, text=True).stdout
        try:
            return json.loads(out)
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None

def event_by_slug(slug):
    d = curl(f"{G}/events?slug={slug}")
    return d[0] if d else None

def search(q, resolved=False):
    url = f"{G}/public-search?q={subprocess.run(['python3','-c','import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))',q],capture_output=True,text=True).stdout.strip()}&limit_per_type=20"
    if resolved:
        url += "&events_status=resolved"
    d = curl(url)
    return (d or {}).get("events", [])

def slim_event(e):
    if not e:
        return None
    return {"slug": e.get("slug"), "title": e.get("title"), "volume": e.get("volume"), "endDate": e.get("endDate"),
            "closed": e.get("closed"),
            "markets": [{"question": m.get("question"), "outcomes": m.get("outcomes"), "outcomePrices": m.get("outcomePrices"),
                         "volumeNum": m.get("volumeNum"), "liquidityNum": m.get("liquidityNum"),
                         "clobTokenIds": m.get("clobTokenIds"), "bestBid": m.get("bestBid"), "bestAsk": m.get("bestAsk"),
                         "lastTradePrice": m.get("lastTradePrice"), "closed": m.get("closed"), "endDate": m.get("endDate")}
                        for m in e.get("markets", [])]}

STATE_NAMES = {"AK":"alaska","AL":"alabama","AR":"arkansas","CO":"colorado","DE":"delaware","FL":"florida","GA":"georgia","IA":"iowa","ID":"idaho","IL":"illinois","KS":"kansas","KY":"kentucky","LA":"louisiana","MA":"massachusetts","ME":"maine","MI":"michigan","MN":"minnesota","MS":"mississippi","MT":"montana","NC":"north-carolina","NE":"nebraska","NH":"new-hampshire","NJ":"new-jersey","NM":"new-mexico","OH":"ohio","OK":"oklahoma","OR":"oregon","RI":"rhode-island","SC":"south-carolina","SD":"south-dakota","TN":"tennessee","TX":"texas","VA":"virginia","WV":"west-virginia","WY":"wyoming"}
SENATE_MOV_OVERRIDE = {
    "AK": "alaska-senate-election-margin-of-victory-final-round",
    "ME": "maine-senate-election-margin-of-victory-final-round",
    "GA": "georgia-senate-election-first-round-margin-of-victory-20260804175717495",
    "MS": "mississippi-senate-election-margin-of-victory-first-round-20260804182229477",
}

def fetch_2026():
    races = list(csv.DictReader(open(RACES)))
    out = {}
    for i, r in enumerate(races):
        rid = r["race_id"]; st = r["state"]
        rec = {"winner": None, "mov": None, "winner_slug": None, "mov_slug": None}
        if r["office"] == "house":
            d = int(float(r["district"])); k = f"{st.lower()}-{d:02d}"
            w = event_by_slug(f"{k}-house-election-winner")
            if not w:
                # alternates for at-large / oddly named events
                for alt in [f"{st.lower()}-al-house-election-winner", f"{STATE_NAMES.get(st, st.lower())}-house-election-winner",
                            f"{STATE_NAMES.get(st, st.lower())}-at-large-house-election-winner", f"{k}-house-election-winner-2026"]:
                    w = event_by_slug(alt)
                    if w: break
            if not w:
                for e in search(f"{st}-{d:02d} House election winner"):
                    s = e.get("slug", "")
                    if "house" in s and (f"{st.lower()}-{d:02d}" in s or f"{st.lower()}-al" in s) and "margin" not in s and "primary" not in s and not e.get("closed"):
                        w = e; break
            m = event_by_slug(f"{k}-house-margin-of-victory-2026")
            if not m:
                for e in search(f"{st}-{d:02d} House margin of victory"):
                    s = e.get("slug", "")
                    if "margin" in s and (f"{st.lower()}-{d:02d}" in s) and "primary" not in s and not e.get("closed"):
                        m = e; break
        else:
            n = STATE_NAMES[st]
            w = event_by_slug(f"{n}-senate-election-winner")
            if not w:
                for e in search(f"{n.replace('-', ' ')} senate election winner"):
                    s = e.get("slug", "")
                    if s.startswith(n) and "senate" in s and "margin" not in s and "primary" not in s and "nominee" not in s and "state-senate" not in s and not e.get("closed"):
                        w = e; break
            m = event_by_slug(SENATE_MOV_OVERRIDE.get(st, f"{n}-senate-margin-of-victory-2026"))
        rec["winner"] = slim_event(w); rec["mov"] = slim_event(m)
        rec["winner_slug"] = w.get("slug") if w else None; rec["mov_slug"] = m.get("slug") if m else None
        out[rid] = rec
        if i % 50 == 0:
            print(f"  {i}/{len(races)} {rid} winner={bool(w)} mov={bool(m)}", flush=True)
    return out

# ---------------- historical (training) events ----------------
SEN24 = ["arizona","ohio","pennsylvania","montana","nevada","nebraska","michigan","wisconsin","texas","maryland","florida","california","washington","utah","wyoming","new-mexico","north-dakota","minnesota","missouri","tennessee","mississippi","indiana","west-virginia","virginia","delaware","new-jersey","new-york","connecticut","rhode-island","massachusetts","vermont","maine","hawaii"]
HOUSE24 = ["ca-13-election-gray-d-vs-duarte-r","nj-07-election-altman-d-vs-kean-r","ca-45-election-tran-d-vs-steel-r","ca-27-election-whitesides-d-vs-garcia-r","wa-03-house-race-perez-d-vs-kent-r","ak-1-election-peltola-d-vs-begich-r","ca-13-election-rollins-d-vs-calvert-r","ca-22-election-salas-d-vs-valadao-r","az-06-election-engel-d-vs-ciscomani-r","ia-01-election-bohannan-d-vs-miller-meeks-r","co-8-election-caraveo-d-vs-evans-r","ny-17-election-jones-d-vs-lawler-r",
           "or-05-election-bynum-d-vs-chavez-deremer-r","ny-19-election-jones-d-vs-molinaro-r","ny-04-election-jones-d-vs-desposito-r","az-01-election-shah-d-vs-schweikert-r","pa-10-election-stelson-d-vs-perry-r","fl-13-election-fox-d-vs-luna-r","ia-03-election-baccam-d-vs-nunn-r","ca-47-election-min-d-vs-baugh-r","pa-07-election-wild-d-vs-mackenzie-r","nh-02-election-goodlander-d-vs-mackenzie-r","nebraska-senate-special-election","arizona-senate-election-margin-of-victory"]
OTHER = ["virginia-governor-election-winner-2025","new-jersey-governor-election-winner-2025","delaware-governor-election-winner","vermont-governor-election-winner",
         "fl-6-special-election-randy-fine-margin-of-victory","fl-1-special-election-jimmy-patronis-margin-of-victory","az-07-special-election-adelita-grijalva-margin-of-victory",
         "tn-07-special-election-margin-of-victory","wisconsin-supreme-court-election-susan-crawford-margin-of-victory","democratic-margin-of-victory-in-va-11-special-election-at-least-45"]
SPECIAL_SEARCH = ["FL-1 special election winner","FL-6 special election winner","VA-11 special election","AZ-07 special election","TN-07 special election","Wisconsin Supreme Court election winner","Virginia Governor margin of victory 2025","New Jersey Governor margin of victory 2025"]

def history(token):
    d = curl(f"{C}/prices-history?market={token}&interval=max&fidelity=1440")
    return (d or {}).get("history", [])

def fetch_hist():
    events = {}
    slugs = [f"{s}-us-senate-election-winner" for s in SEN24] + HOUSE24 + OTHER
    for s in slugs:
        e = event_by_slug(s)
        if e: events[s] = slim_event(e)
        else: print("  missing hist slug", s)
    for q in SPECIAL_SEARCH:
        for e in search(q, resolved=True):
            s = e.get("slug", "")
            if re.search(r"(special|supreme-court|governor)", s) and "primary" not in s and s not in events and "2025" in (e.get("endDate") or "") + s or "special" in s:
                if s not in events and ("special" in s or "supreme" in s or "governor" in s) and "primary" not in s and "ap-call" not in s and "when-will" not in s:
                    events[s] = slim_event(e)
    print("  historical events:", len(events))
    # price history for every market token (Yes side)
    for s, e in events.items():
        for m in e["markets"]:
            try:
                toks = json.loads(m.get("clobTokenIds") or "[]")
            except Exception:
                toks = []
            m["history_yes"] = history(toks[0]) if toks else []
            time.sleep(0.15)
    return events

if __name__ == "__main__":
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "2026"):
        print("Fetching 2026 Polymarket markets...", flush=True)
        d = fetch_2026()
        json.dump({"fetched_utc": stamp, "races": d}, open(os.path.join(RAW, "polymarket_2026.json"), "w"))
        nw = sum(1 for v in d.values() if v["winner"]); nm = sum(1 for v in d.values() if v["mov"])
        print(f"2026 done: winner events {nw}/{len(d)}, MOV events {nm}/{len(d)}")
        print("no winner:", [k for k, v in d.items() if not v["winner"]])
    if what in ("all", "hist"):
        print("Fetching historical Polymarket markets...", flush=True)
        h = fetch_hist()
        json.dump({"fetched_utc": stamp, "events": h}, open(os.path.join(RAW, "polymarket_hist.json"), "w"))
        print("hist done:", len(h), "events")
