"""Download settled Kalshi election markets and daily candlesticks from the public /historical/ endpoints (no key needed)."""
import json, os, re, time, urllib.request, urllib.parse, calendar
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, "raw")
B = "https://api.elections.kalshi.com/trade-api/v2"
def get(path, **q):
    err = None
    for i in range(5):
        try:
            with urllib.request.urlopen(B + path + ("?" + urllib.parse.urlencode(q) if q else ""), timeout=60) as r:
                return json.load(r)
        except Exception as ex:
            err = str(ex); time.sleep(2.5 * (i + 1))
    return {"_err": err}
settled = json.load(open(os.path.join(RAW, "kalshi_settled_events.json")))
events = sorted({e for v in settled.values() for e, _ in v})
extra = ["HOUSETN7S-25", "HOUSEAZ7S-25", "KXUSELECTIONTEXAS18-26", "KXTX18SPECIAL-26", "GOVPARTYVA-25", "GOVPARTYNJ-25"]
events = sorted(set(events + extra))
keep = [e for e in events if re.search(r"^(HOUSE|SENATE|GOVPARTY|KXHOUSE|KXSENATE|KXGOVPARTY|KXFL|KXELECTIONMOV|KXMOV|KXGA14|KXUSELECTION|KXTX18)", e) and not re.search(r"(26$|NOM|PRIMARY|MOVIL)", e.replace("KXUSELECTIONTEXAS18-26", "x").replace("KXTX18SPECIAL-26", "x"))]
print("settled events total", len(events), "kept", len(keep), flush=True)
out = {}
for et in keep:
    d = get("/historical/markets", event_ticker=et, limit=100)
    ms = d.get("markets", [])
    if not ms: print("  no markets:", et, d.get("_err", "")); time.sleep(0.4); continue
    rec = []
    for m in ms:
        ts = lambda s: calendar.timegm(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))
        start, end = ts(m["open_time"]), ts(m["close_time"])
        c = get(f"/historical/markets/{m['ticker']}/candlesticks", start_ts=start, end_ts=min(end, start + 86400 * 4800), period_interval=1440)
        rec.append({k: m.get(k) for k in ("ticker", "event_ticker", "title", "yes_sub_title", "no_sub_title", "custom_strike", "result", "expiration_value", "open_time", "close_time", "volume_fp", "volume", "floor_strike", "cap_strike", "strike_type")} | {"candles": c.get("candlesticks", []), "candle_err": c.get("_err")})
        time.sleep(0.4)
    out[et] = rec
    print(" ", et, len(ms), [len(r["candles"]) for r in rec][:4], flush=True)
    json.dump(out, open(os.path.join(RAW, "kalshi_hist.json"), "w"))
print("done: events with markets", len(out))
