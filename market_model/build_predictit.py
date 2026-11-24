"""Turn downloaded PredictIt race markets into training rows (D-side price 2 days out vs actual D two-party share).
Labels come from the course results file (2012-2024 House/Senate). Governors and House specials are skipped (no labels)."""
import csv, glob, json, os, re, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, "raw", "predictit")
res = {r["race_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "..", "data (1)", "hw4_results_2012_2024.csv")))}
ELECTIONS = {2014: "2014-11-04", 2016: "2016-11-08", 2018: "2018-11-06", 2020: "2020-11-03", 2022: "2022-11-08", 2024: "2024-11-05"}
STATES = {"alabama":"AL","alaska":"AK","arizona":"AZ","arkansas":"AR","california":"CA","colorado":"CO","connecticut":"CT","delaware":"DE","florida":"FL","georgia":"GA","hawaii":"HI","idaho":"ID","illinois":"IL","indiana":"IN","iowa":"IA","kansas":"KS","kentucky":"KY","louisiana":"LA","maine":"ME","maryland":"MD","massachusetts":"MA","michigan":"MI","minnesota":"MN","mississippi":"MS","missouri":"MO","montana":"MT","nebraska":"NE","nevada":"NV","new hampshire":"NH","new jersey":"NJ","new mexico":"NM","new york":"NY","north carolina":"NC","north dakota":"ND","ohio":"OH","oklahoma":"OK","oregon":"OR","pennsylvania":"PA","rhode island":"RI","south carolina":"SC","south dakota":"SD","tennessee":"TN","texas":"TX","utah":"UT","vermont":"VT","virginia":"VA","washington":"WA","west virginia":"WV","wisconsin":"WI","wyoming":"WY"}
ORD = {"first":1,"second":2,"third":3,"fourth":4,"fifth":5,"sixth":6,"seventh":7,"eighth":8,"ninth":9,"tenth":10}

def parse_race(name):
    n = name.lower()
    if re.search(r"governor|gubernatorial|mayor|president|attorney general|secretary of state|state senate|state house|assembly|legislature|supreme court|parliament|prime minister|chancellor", n): return None
    if "special" in n and "senate" not in n: return None
    m = re.search(r"\b([A-Z]{2})-(\d{1,2})\b", name)
    if m and m.group(1) in STATES.values(): return "house", m.group(1), int(m.group(2))
    st = None
    for s, ab in sorted(STATES.items(), key=lambda t: -len(t[0])):
        if re.search(r"\b" + s + r"(?:'s)?\b", n): st = ab; break
    if st is None: return None
    if "senate" in n or "senator" in n: return ("senate_special" if "special" in n else "senate"), st, None
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)\s+(?:congressional\s+)?district", n) or re.search(r"district\s+(\d{1,2})\b", n)
    if m: return "house", st, int(m.group(1))
    m = re.search(r"\b(" + "|".join(ORD) + r")\s+(?:congressional\s+)?district", n)
    if m: return "house", st, ORD[m.group(1)]
    if "at-large" in n or "at large" in n: return "house", st, 1
    if "house" in n or "congress" in n:
        return None
    return None

def lastnames(s):
    out = []
    for part in (s or "").split(";"):
        part = part.strip()
        if "," in part: out.append(part.split(",")[0].strip().lower())
        else:
            toks = [t for t in part.split() if t.lower().strip(".") not in ("jr", "sr", "ii", "iii")]
            if toks: out.append(toks[-1].lower())
    return out

rows = []; skipped = {}
for mf in glob.glob(os.path.join(RAW, "markets_*.json")):
    hits = json.load(open(mf))
    for mid, h in hits.items():
        if mid.startswith("_"): continue
        pr = parse_race(h["name"])
        if not pr: skipped[h["name"]] = "no race parse"; continue
        kind, st, dist = pr
        f = os.path.join(RAW, f"chart_{mid}.csv")
        if not os.path.exists(f) or os.path.getsize(f) < 50: skipped[h["name"]] = "no chart"; continue
        ch = list(csv.DictReader(open(f)))
        if not ch: skipped[h["name"]] = "empty chart"; continue
        dates = sorted(set(datetime.datetime.strptime(r["Date"].split()[0], "%m/%d/%Y").date() for r in ch))
        last = dates[-1]
        year = next((y for y, e in ELECTIONS.items() if -5 <= (last - datetime.date.fromisoformat(e)).days <= 75), None)
        if year is None: skipped[h["name"]] = f"last chart date {last} not near an election"; continue
        E = datetime.date.fromisoformat(ELECTIONS[year]); cutoff = E - datetime.timedelta(days=2)
        rid = f"SEN_{st}_{year}" + ("_S" if kind == "senate_special" else "") if kind != "house" else f"HOU_{st}_{dist:02d}_{year}"
        r = res.get(rid)
        if not r or not r.get("dem_share"): skipped[h["name"]] = f"no label for {rid}"; continue
        dn, rn = lastnames(r["dem_candidate"]), lastnames(r["rep_candidate"])
        # price per contract at cutoff (latest close on/before cutoff)
        price = {}
        for c in sorted(set(r2["ContractName"] for r2 in ch)):
            pts = [(datetime.datetime.strptime(r2["Date"].split()[0], "%m/%d/%Y").date(), float(r2["CloseSharePrice"].strip("$"))) for r2 in ch if r2["ContractName"] == c]
            pts = [p for p in pts if p[0] <= cutoff]
            if pts: price[c] = max(pts)[1]
        if not price: skipped[h["name"]] = "no prices before cutoff"; continue
        pD = pR = None
        for c, v in price.items():
            cl = c.lower()
            if any(n in cl for n in dn) or cl.startswith("democrat"): pD = (pD or 0) + v
            elif any(n in cl for n in rn) or cl.startswith("republican"): pR = (pR or 0) + v
        if pD is None and pR is None: skipped[h["name"]] = f"contracts {list(price)} not matched to {dn}/{rn}"; continue
        p = (pD + (1 - pR)) / 2 if (pD is not None and pR is not None) else (pD if pD is not None else 1 - pR)
        rows.append({"slug": f"predictit-{mid}", "kind": f"{'house' if kind=='house' else 'senate'}{str(year)[2:]}", "source": "predictit", "election_date": ELECTIONS[year],
                     "p_t2": round(min(max(p, 0.001), 0.999), 4), "p_t1": None, "p_t7": None, "label_share": float(r["dem_share"]) / 100, "volume": None, "market": h["name"], "race_id": rid})
rows.sort(key=lambda r: (r["election_date"], r["slug"]))
with open(os.path.join(HERE, "training_predictit.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print("PredictIt training rows:", len(rows))
from collections import Counter; print(Counter(r["kind"] for r in rows))
for r in rows: print(f"  {r['kind']:9s} {r['race_id']:16s} p={r['p_t2']:.3f} actual={r['label_share']:.3f}  {r['market'][:60]}")
print("\nskipped:", len(skipped))
for k, v in list(skipped.items())[:60]: print("  ", v, "|", k[:80])
