"""Enumerate PredictIt market IDs via the public metadata API, keep resolved U.S. Senate/House/governor
race markets, and download their 90-day daily price history (closed markets still serve it)."""
import json, os, re, sys, time, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, "raw", "predictit"); os.makedirs(RAW, exist_ok=True)
META = "https://www.predictit.org/api/marketdata/markets/{id}"
CHART = "https://www.predictit.org/Resource/DownloadMarketChartData?marketid={id}&timespan=90d"
RX = re.compile(r"(senate|house|congressional|district|governor|gubernatorial|\b[A-Z]{2}-\d{1,2}\b)", re.I)
EXCL = re.compile(r"(primary|nominee|nomination|caucus|runoff lead|how many|control|majority|seats|special session|confirm|vote|poll|approval|debate|tweet|resign|impeach|speaker|leader|whip|retire|announce|run for|endorse|cabinet|supreme court|lead the first round)", re.I)

def curl(url):
    out = subprocess.run(["curl", "-s", "--max-time", "30", url], capture_output=True, text=True).stdout
    return out

def enumerate_ids(lo, hi, outfile):
    hits = json.load(open(outfile)) if os.path.exists(outfile) else {}
    done = set(int(k) for k in hits.get("_scanned", []))
    for i in range(lo, hi):
        if i in done: continue
        raw = curl(META.format(id=i))
        try: d = json.loads(raw)
        except Exception: d = None
        if d and isinstance(d, dict) and d.get("name"):
            name = d["name"]
            if RX.search(name) and not EXCL.search(name):
                hits[str(i)] = {"name": name, "shortName": d.get("shortName"), "status": d.get("status"),
                                "contracts": [{"id": c.get("id"), "name": c.get("name"), "shortName": c.get("shortName"), "status": c.get("status"), "dateEnd": c.get("dateEnd")} for c in d.get("contracts", [])]}
                print(i, "|", name, flush=True)
        if i % 100 == 0:
            hits.setdefault("_scanned", []); hits["_scanned"] = sorted(set(hits["_scanned"]) | set(range(lo, i + 1)))
            json.dump(hits, open(outfile, "w"), indent=0); print("...", i, flush=True)
        time.sleep(0.08)
    hits["_scanned"] = sorted(set(hits.get("_scanned", [])) | set(range(lo, hi)))
    json.dump(hits, open(outfile, "w"), indent=0)
    return hits

def download_charts(hits):
    for i, h in hits.items():
        if i.startswith("_"): continue
        f = os.path.join(RAW, f"chart_{i}.csv")
        if os.path.exists(f) and os.path.getsize(f) > 50: continue
        open(f, "w").write(curl(CHART.format(id=i))); time.sleep(0.2)

if __name__ == "__main__":
    lo, hi = int(sys.argv[1]), int(sys.argv[2])
    out = os.path.join(RAW, f"markets_{lo}_{hi}.json")
    hits = enumerate_ids(lo, hi, out)
    print("race-like markets:", sum(1 for k in hits if not k.startswith("_")))
    download_charts(hits); print("charts downloaded")
