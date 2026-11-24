"""Fetch Kalshi 2026 House and Senate race markets (public API, no key).
Rate-limited: sleeps between calls and retries on 429. Saves raw JSON under raw/."""
import json, re, time, os, csv, datetime, urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
RACES = os.path.join(HERE, "..", "data (1)", "races_2026.csv")
B = "https://api.elections.kalshi.com/trade-api/v2"

def get(path, **q):
    err = None
    for i in range(5):
        try:
            with urllib.request.urlopen(B + path + "?" + urllib.parse.urlencode(q), timeout=60) as r:
                return json.load(r)
        except Exception as ex:
            err = str(ex); time.sleep(2.5 * (i + 1))
    return {"_err": err}

def slim(m):
    keys = ["ticker", "event_ticker", "title", "yes_sub_title", "subtitle", "status", "yes_bid_dollars", "yes_ask_dollars",
            "last_price_dollars", "previous_price_dollars", "volume_fp", "volume_24h_fp", "open_interest_fp", "close_time", "rules_primary"]
    return {k: m.get(k) for k in keys}

def all_events(series):
    out, cur = [], None
    while True:
        q = {"series_ticker": series, "limit": 200, "with_nested_markets": "true"}
        if cur: q["cursor"] = cur
        d = get("/events", **q)
        out += d.get("events", []); cur = d.get("cursor")
        if not cur or "_err" in d: break
        time.sleep(0.6)
    return out

def main():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    series = get("/series", limit=5000).get("series", [])
    tickers = [x["ticker"] for x in series if x.get("category") == "Elections"]
    house_series = [t for t in tickers if re.match(r"^(KX)?HOUSE[A-Z]{2}\d{1,2}$", t)] + ["KXALASKAHOUSE", "HOUSENH2", "KXHOUSENY21"]
    out = {"fetched_utc": stamp, "events": {}}
    print("KXHOUSERACE...", flush=True)
    for e in all_events("KXHOUSERACE"):
        out["events"][e["event_ticker"]] = {"title": e.get("title"), "sub_title": e.get("sub_title"), "series": "KXHOUSERACE",
                                            "markets": [slim(m) for m in e.get("markets", [])]}
    print("  events:", len(out["events"]), flush=True)
    print("per-district House series:", len(house_series), flush=True)
    for t in sorted(set(house_series)):
        d = get("/events", series_ticker=t, limit=50, with_nested_markets="true")
        for e in d.get("events", []):
            if "26" in e["event_ticker"]:
                out["events"][e["event_ticker"]] = {"title": e.get("title"), "sub_title": e.get("sub_title"), "series": t,
                                                    "markets": [slim(m) for m in e.get("markets", [])]}
        time.sleep(0.6)
    print("Senate...", flush=True)
    races = list(csv.DictReader(open(RACES)))
    for r in races:
        if r["office"] != "senate": continue
        st = r["state"]; et = f"SENATE{st}{'S' if r['special'] == '1' else ''}-26"
        d = get("/markets", event_ticker=et, limit=50)
        ms = d.get("markets", [])
        if ms:
            out["events"][et] = {"title": et, "sub_title": st, "series": et.split("-")[0], "markets": [slim(m) for m in ms]}
        else:
            print("  no Kalshi senate markets for", et, d.get("_err", ""))
        time.sleep(0.6)
    # national House popular-vote margin (for the write-up / coherence check only)
    d = get("/markets", series_ticker="KXHOUSEPOPVOTEMARGIND", limit=50)
    out["house_popvote_margin"] = [slim(m) for m in d.get("markets", [])]
    json.dump(out, open(os.path.join(RAW, "kalshi_2026.json"), "w"))
    print("KXVOTEGENERAL vote-percentage ladders...", flush=True)
    lad = all_events("KXVOTEGENERAL")
    json.dump(lad, open(os.path.join(RAW, "kalshi_votegeneral_2026.json"), "w"))
    print("  ladder events:", len(lad))
    priced = sum(1 for e in out["events"].values() if any((m.get("yes_bid_dollars") not in (None, "0.0000")) for m in e["markets"]))
    print("Kalshi done: events", len(out["events"]), "priced", priced)

if __name__ == "__main__":
    main()
