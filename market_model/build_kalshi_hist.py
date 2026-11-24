"""Kalshi settled race markets -> training rows (D-side price 2 days before the election vs actual D two-party share)."""
import json, os, re, csv, datetime, calendar, time
HERE = os.path.dirname(os.path.abspath(__file__))
H = json.load(open(os.path.join(HERE, "raw", "kalshi_hist.json")))
res = {r["race_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "..", "data (1)", "hw4_results_2012_2024.csv")))}
HAND = {  # two-party D-side share (%), election date, D-side name fragments
    "GOVPARTYVA-25": (57.6, "2025-11-04"), "GOVPARTYNJ-25": (56.7, "2025-11-04"),
    "HOUSEFL1-25": (42.6, "2025-04-01"), "HOUSEFL6-25": (43.0, "2025-04-01"), "HOUSEVA11S-25": (75.3, "2025-09-09"),
    "HOUSETN7S-25": (45.4, "2025-12-02"), "GOVPARTYDE-24": (57.2, "2024-11-05"),
    "GOVPARTYNC-24": (51.3, "2024-11-05"), "GOVPARTYNH-24": (46.0, "2024-11-05"), "GOVPARTYWA-24": (55.9, "2024-11-05"),
    "GOVPARTYMO-24": (39.6, "2024-11-05"), "GOVPARTYIN-24": (42.4, "2024-11-05"), "GOVPARTYMT-24": (40.8, "2024-11-05"),
    "GOVPARTYND-24": (31.1, "2024-11-05"), "GOVPARTYUT-24": (30.7, "2024-11-05"), "GOVPARTYWV-24": (36.1, "2024-11-05"),
}
def lastnames(s):
    out = []
    for part in (s or "").split(";"):
        part = part.strip()
        if "," in part: out.append(part.split(",")[0].strip().lower())
        else:
            toks = [t for t in part.split() if t.lower().strip(".") not in ("jr", "sr", "ii", "iii")]
            if toks: out.append(toks[-1].lower())
    return out
def price_at(candles, date, days_before):
    cutoff = calendar.timegm(time.strptime(date, "%Y-%m-%d")) - days_before * 86400 + 86399
    pts = [c for c in candles if c["end_period_ts"] <= cutoff and c["price"].get("close") is not None]
    if not pts: return None
    c = pts[-1]["price"]; return float(c["close"])
rows = []
for et, ms in H.items():
    m_ = re.match(r"^(HOUSE|SENATE)([A-Z]{2})(\d{0,2})(S?)-(24|25)$", et)
    label = date = None; kind = None
    if m_:
        off, st, dist, sp, yr = m_.groups()
        if yr == "24":
            rid = f"HOU_{st}_{int(dist):02d}_2024" if off == "HOUSE" else f"SEN_{st}_2024" + ("_S" if sp else "")
            r = res.get(rid)
            if not r or not r.get("dem_share"): print("no label", et, rid); continue
            label, date = float(r["dem_share"]), "2024-11-05"; dn, rn = lastnames(r["dem_candidate"]), lastnames(r["rep_candidate"]); other_is_d = r["d_side_party"] == "I"
            kind = ("house24" if off == "HOUSE" else "senate24")
        else:
            if et not in HAND: continue
            label, date = HAND[et]; dn, rn = [], []; other_is_d = False; kind = "special25"
    elif et in HAND:
        label, date = HAND[et]; dn, rn = [], []; other_is_d = False; kind = "gov" + et[-2:]
    else:
        continue
    pD = pR = None; vol = 0.0
    for m in ms:
        name = ((m.get("yes_sub_title") or "") + " " + json.dumps(m.get("custom_strike") or {})).lower()
        p = price_at(m["candles"], date, 2)
        if p is None: continue
        vol += float(m.get("volume_fp") or m.get("volume") or 0)
        if any(n in name for n in dn) or (not dn and "democrat" in name) or (dn and "democrat" in name and not other_is_d):
            pD = (pD or 0) + p
        elif any(n in name for n in rn) or "republican" in name:
            pR = (pR or 0) + p
        elif other_is_d and ("independent" in name or "other" in name):
            pD = (pD or 0) + p
    if pD is None and pR is None: print("no side match", et, [m.get("yes_sub_title") for m in ms]); continue
    p = (pD + (1 - pR)) / 2 if (pD is not None and pR is not None) else (pD if pD is not None else 1 - pR)
    rows.append({"slug": f"kalshi-{et}", "kind": kind, "source": "kalshi", "election_date": date, "p_t2": round(min(max(p, 0.001), 0.999), 4),
                 "p_t1": None, "p_t7": None, "label_share": label / 100, "volume": round(vol), "market": et})
rows.sort(key=lambda r: (r["kind"], r["slug"]))
with open(os.path.join(HERE, "training_kalshi.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
from collections import Counter
print("Kalshi training rows:", len(rows), Counter(r["kind"] for r in rows))
for r in rows: print(f"  {r['kind']:9s} {r['market']:16s} p={r['p_t2']:.3f} actual={r['label_share']:.3f} vol={r['volume']}")
