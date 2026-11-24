"""Build the calibration set: resolved Polymarket win markets (2024 Senate/House, 2024-25 governors,
2025 specials) with the D-side price 2 days before the election and the actual D two-party share."""
import json, os, re, csv, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data (1)")
hist = json.load(open(os.path.join(HERE, "raw", "polymarket_hist.json")))["events"]
res = {r["race_id"]: r for r in csv.DictReader(open(os.path.join(DATA, "hw4_results_2012_2024.csv")))}

STATES = {"arizona":"AZ","ohio":"OH","pennsylvania":"PA","montana":"MT","nevada":"NV","nebraska":"NE","michigan":"MI","wisconsin":"WI","texas":"TX","maryland":"MD","florida":"FL","california":"CA","washington":"WA","utah":"UT","wyoming":"WY","new-mexico":"NM","north-dakota":"ND","minnesota":"MN","missouri":"MO","tennessee":"TN","mississippi":"MS","indiana":"IN","west-virginia":"WV","virginia":"VA","delaware":"DE","new-jersey":"NJ","new-york":"NY","connecticut":"CT","rhode-island":"RI","massachusetts":"MA","vermont":"VT","maine":"ME","hawaii":"HI"}
# hand-entered two-party D-side shares (%, public returns) for races not in the course results file
HAND = {
    "virginia-governor-election-winner-2025": ("gov", 57.6, "2025-11-04", ["spanberger"]),
    "new-jersey-governor-election-winner-2025": ("gov", 56.7, "2025-11-04", ["sherrill"]),
    "delaware-governor-election-winner": ("gov", 57.2, "2024-11-05", ["meyer"]),
    "vermont-governor-election-winner": ("gov", 24.3, "2024-11-05", ["charlestin"]),
}
SPECIALS = [  # (slug regex, label, election date, D candidate name fragments)
    (r"fl-?0?1.*special.*(winner|valimont|patronis)(?!.*margin)", 42.6, "2025-04-01", ["valimont", "democrat"]),
    (r"fl-?0?6.*special.*(winner|weil|fine)(?!.*margin)", 43.0, "2025-04-01", ["weil", "democrat"]),
    (r"va-?11.*special(?!.*margin)", 75.3, "2025-09-09", ["walkinshaw", "democrat"]),
    (r"az-?0?7.*special(?!.*margin)", 69.9, "2025-09-23", ["grijalva", "democrat"]),
    (r"tn-?0?7.*special(?!.*margin)", 45.4, "2025-12-02", ["behn", "democrat"]),
    (r"wisconsin-supreme-court(?!.*margin)", 55.0, "2025-04-01", ["crawford"]),
]

def price_at(history, date, days_before):
    cutoff = datetime.datetime.fromisoformat(date).replace(tzinfo=datetime.timezone.utc) - datetime.timedelta(days=days_before)
    pts = [p for p in history if datetime.datetime.fromtimestamp(p["t"], datetime.timezone.utc) <= cutoff + datetime.timedelta(hours=23, minutes=59)]
    return pts[-1]["p"] if pts else None

def dside_market(ev, names, generic_other=False):
    """Pick the market whose Yes = D-side win. Returns (market, invert)."""
    for m in ev["markets"]:
        q = (m["question"] or "").lower()
        if any(n in q for n in names): return m, False
    if generic_other:
        for m in ev["markets"]:
            if "another party" in (m["question"] or "").lower() or "independent" in (m["question"] or "").lower(): return m, False
    for m in ev["markets"]:
        if "democrat" in (m["question"] or "").lower(): return m, False
    return None, False

rows = []
for slug, ev in hist.items():
    kind = label = date = None; names = []; other = False
    m_ = re.match(r"^([a-z-]+)-us-senate-election-winner$", slug)
    if m_:
        st = STATES[m_.group(1)]; r = res.get(f"SEN_{st}_2024")
        if not r or st in ("ME", "VT"): continue  # ME: markets priced King (I); VT: Sanders priced as the Democrat
        kind, label, date = "senate24", float(r["dem_share"]), "2024-11-05"
        other = r["d_side_party"] == "I"; names = [r["dem_candidate"].split(",")[0].lower()] if not other else [r["dem_candidate"].split(",")[0].lower()]
    elif re.match(r"^[a-z]{2}-\d{1,2}-(election|house-race)-", slug):
        st = slug[:2].upper(); d = int(re.match(r"^[a-z]{2}-(\d{1,2})", slug).group(1))
        if slug.startswith("ca-13-election-rollins"): d = 41       # Polymarket slug typo: CA-41 Rollins vs Calvert
        r = res.get(f"HOU_{st}_{d:02d}_2024")
        if not r: print("no result for", slug); continue
        kind, label, date = "house24", float(r["dem_share"]), "2024-11-05"
        names = [n.split(",")[0].lower() for n in r["dem_candidate"].split(";")]
    elif slug in HAND:
        kind, label, date, names = HAND[slug]
    else:
        for rx, lab, dt, nm in SPECIALS:
            if re.search(rx, slug) and "margin" not in slug:
                kind, label, date, names = "special25", lab, dt, nm; break
    if kind is None: continue
    m, inv = dside_market(ev, names, generic_other=other)
    if m is None:
        # single-market "A (D) vs. B (R)" events: outcomes are candidate names, Yes = first outcome
        if len(ev["markets"]) == 1:
            m = ev["markets"][0]
            try: outs = json.loads(m.get("outcomes") or "[]")
            except Exception: outs = []
            if outs and not any(n in outs[0].lower() for n in names): inv = True
        else:
            print("no D-side market for", slug, [x["question"] for x in ev["markets"]][:4]); continue
    h = m.get("history_yes") or []
    p2, p1, p7 = (price_at(h, date, k) for k in (2, 1, 7))
    if p2 is None: print("no history for", slug); continue
    if inv: p2, p1, p7 = 1 - p2, (1 - p1 if p1 is not None else None), (1 - p7 if p7 is not None else None)
    rows.append({"slug": slug, "kind": kind, "election_date": date, "p_t2": round(p2, 4), "p_t1": p1, "p_t7": p7,
                 "label_share": label / 100.0, "volume": round(float(ev.get("volume") or 0)), "market": m["question"]})
rows.sort(key=lambda r: (r["kind"], r["slug"]))
with open(os.path.join(HERE, "training.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(f"training rows: {len(rows)}")
for r in rows: print(f"  {r['kind']:9s} {r['slug'][:48]:48s} p(T-2)={r['p_t2']:.3f} actual={r['label_share']:.3f}")

# ---- resolved MOV markets (sanity check of the bucket -> margin path) ----
import mm
movs = []
for slug, ev in hist.items():
    if "margin" not in slug: continue
    for rx, lab, dt, nm in SPECIALS + [(r"va-11", 75.3, "2025-09-09", ["democrat"])]:
        if re.search(rx.split("(?!")[0], slug):
            dn = [n for n in nm if n != "democrat"]
            # rebuild buckets from T-2 prices
            bks = []; 
            for m in ev["markets"]:
                pb = mm.parse_bucket(m["question"] or "", dn + ["democrat"], ["patronis", "fine", "whitson", "butierez", "van epps", "schimel", "republican"])
                p2 = price_at(m.get("history_yes") or [], dt, 2)
                if pb and p2 is not None:
                    side, lo, hi = pb
                    if side == "D" or any(n in (m["question"] or "").lower() for n in dn): bks.append((lo, hi, p2))
                    else: bks.append((-hi, -lo, p2))
            if len(bks) >= 3:
                fit = mm.fit_normal_to_buckets(bks)
                if fit:
                    mu, sd, _ = fit; movs.append((slug, mu, sd, (lab - 50) * 2))
            break
print("\nMOV sanity check (implied D margin from buckets at T-2 vs actual two-party margin, points):")
for s, mu, sd, act in movs: print(f"  {s[:60]:60s} implied {mu:+6.1f} (sd {sd:4.1f})  actual {act:+6.1f}")
json.dump([{"slug": s, "mu": mu, "sd": sd, "actual_margin": a} for s, mu, sd, a in movs], open(os.path.join(HERE, "mov_check.json"), "w"), indent=1)
