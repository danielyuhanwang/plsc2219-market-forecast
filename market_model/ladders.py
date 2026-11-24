"""Kalshi KXVOTEGENERAL vote-percentage ladders -> implied vote share per candidate -> D two-party share per race."""
import json, re, csv, os, math, numpy as np, mm
HERE = os.path.dirname(os.path.abspath(__file__))
def lastnames(s):
    out = []
    for part in (s or "").split(";"):
        toks = [t.strip(" .,") for t in part.strip().split() if t.lower().strip(".") not in ("jr", "sr", "ii", "iii", "iv")]
        if toks: out.append(toks[-1].lower())
    return out
def fnum(x):
    try: return float(x)
    except Exception: return None
def ladder_fit(points):
    """points: list of (x, S) with S = P(share >= x). Normal fit by least squares -> (mu, sd, loss)."""
    def loss(v):
        mu, ls = v; sd = math.exp(ls)
        return sum((S - (1 - mm.phi((x - mu) / sd))) ** 2 for x, S in points)
    xs = [x for x, _ in points]; best = None
    for mu0 in (np.mean(xs), 50.0):
        for s0 in (3.0, 6.0):
            x, v = mm.nelder_mead(loss, [mu0, math.log(s0)], step=2.0)
            if best is None or v < best[1]: best = (x, v)
    (mu, ls), v = best; return mu, math.exp(ls), v
def candidate_dist(markets, max_spread=0.25):
    pts = []; vol = 0.0; spreads = []
    for m in markets:
        x = fnum(m.get("floor_strike")); bid, ask, last = fnum(m.get("yes_bid_dollars")), fnum(m.get("yes_ask_dollars")), fnum(m.get("last_price_dollars"))
        if x is None: continue
        if bid is not None and ask is not None and ask > 0:
            if ask - bid > max_spread: continue
            p = (bid + ask) / 2; spreads.append(ask - bid)
        elif last is not None: p = last
        else: continue
        pts.append((x, p)); vol += fnum(m.get("volume_fp")) or 0
    if len(pts) < 3: return None
    pts.sort()
    # enforce a non-increasing survival function (pool adjacent violators)
    S = [p for _, p in pts]
    for i in range(1, len(S)):
        if S[i] > S[i - 1]: S[i] = S[i - 1]
    pts = [(x, s) for (x, _), s in zip(pts, S)]
    mu, sd, loss = ladder_fit(pts)
    return {"mu": mu, "sd": sd, "loss": loss, "n": len(pts), "vol": vol, "spread": float(np.mean(spreads)) if spreads else None, "xmin": pts[0][0], "xmax": pts[-1][0]}
def name_tokens(s):
    return [t.strip(" .,").lower() for t in (s or "").replace(";", " ").split() if t.lower().strip(".") not in ("jr", "sr", "ii", "iii", "iv")]
def race_shares(events, races):
    """Return {race_id: {...}} with implied D two-party share from the candidate ladders.
    For ranked-choice races the '(Final Round)' ladder is used when it exists. Among several ladders on the same
    side (e.g. a minor candidate sharing a surname) the one with the largest implied share is kept."""
    out = {}; by_key = {}
    for r in races:
        if r["office"] == "house": by_key[("H", r["state"], int(float(r["district"])))] = r
        else: by_key[("S", r["state"], int(r["special"]))] = r
    for e in events:
        et = e["event_ticker"]; title = (e.get("title") or "")
        m = re.search(r"(?:KXHOUSERACE-|KXHOUSE|HOUSE)([A-Z]{2})(\d{1,2}|AL)-26", et) or re.search(r"(?:KX)?SENATE([A-Z]{2})(S?)-26", et)
        if not m: continue
        key = ("S", m.group(1), 1 if m.group(2) == "S" else 0) if ("SENATE" in et and "HOUSE" not in et) else ("H", m.group(1), 1 if m.group(2) == "AL" else int(m.group(2)))
        r = by_key.get(key)
        if not r or r["race_type"] == "la_jungle": continue
        final = "final round" in title.lower(); first = "1st round" in title.lower() or "first round" in title.lower()
        if r["rcv"] == "1" and first: continue            # competition scores the final round
        tl = title.lower()
        def match(names):  # full-name token match beats surname-only
            full = [n for n in names.split(";") if n.strip()]
            return any(all(t in tl for t in name_tokens(n)) for n in full) or any(n in tl for n in lastnames(names))
        side = "D" if match(r["dem_candidate"]) else ("R" if match(r["rep_candidate"]) else None)
        if side is None: continue
        dist = candidate_dist(e["markets"])
        if not dist: continue
        if not (dist["xmin"] - 6 <= dist["mu"] <= dist["xmax"] + 6) or not (0.5 <= dist["sd"] <= 15) or dist["mu"] < 5: continue
        rec = out.setdefault(r["race_id"], {})
        prev = rec.get(side)
        if prev and not (final and "Final" not in prev["event"]) and prev["mu"] >= dist["mu"]: continue
        dist["event"] = et; rec[side] = dist
    res = {}
    for rid, rec in out.items():
        D, R = rec.get("D"), rec.get("R")
        if D and R:
            if not (80 <= D["mu"] + R["mu"] <= 106): continue
            share = D["mu"] / (D["mu"] + R["mu"]); how = "both"
        elif D: share = D["mu"] / 97.0; how = "D only"
        else: share = 1 - R["mu"] / 97.0; how = "R only"
        res[rid] = {"share": float(share), "how": how, "D": D, "R": R, "vol": float((D["vol"] if D else 0) + (R["vol"] if R else 0)),
                    "sd_share": math.sqrt(((D["sd"] if D else 4) ** 2 + (R["sd"] if R else 4) ** 2)) / 200}
    return res
if __name__ == "__main__":
    races = list(csv.DictReader(open(os.path.join(HERE, "..", "data (1)", "races_2026.csv"))))
    ev = json.load(open(os.path.join(HERE, "raw", "kalshi_votegeneral_2026.json")))
    res = race_shares(ev, races)
    det = {r["race_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "forecast_detail.csv")))}
    print("races with a ladder share:", len(res), {k: sum(1 for v in res.values() if v["how"] == k) for k in ("both", "D only", "R only")})
    print("by current path:", {p: sum(1 for k in res if det[k]["path"] == p) for p in ("p+mov", "p+pvi", "p", "fixed")})
    vols = np.array([v["vol"] for v in res.values()]); print("ladder volume $ quantiles:", [int(np.percentile(vols, q)) for q in (10, 25, 50, 75, 90)])
    diffs = [(res[k]["share"] - float(det[k]["pred"]), k) for k in res if det[k]["path"] != "fixed"]
    d = np.array([x for x, _ in diffs]); print(f"ladder share vs current forecast: mean {d.mean()*100:+.2f}, MAE {np.mean(np.abs(d))*100:.2f}, sd {d.std()*100:.2f} pts")
    for p in ("p+mov", "p+pvi"):
        dd = np.array([x for x, k in diffs if det[k]["path"] == p]); print(f"   vs {p:6s} n={len(dd)} mean {dd.mean()*100:+.2f} MAE {np.mean(np.abs(dd))*100:.2f}")
    print("largest disagreements:", [(k, round(float(det[k]["pred"]), 3), round(res[k]["share"], 3), res[k]["how"], int(res[k]["vol"])) for x, k in sorted(diffs, key=lambda t: -abs(t[0]))[:12]])
    for rid in ("HOU_CA_45_2026", "HOU_CA_26_2026", "HOU_CA_27_2026", "SEN_TX_2026", "SEN_ME_2026", "HOU_NY_17_2026", "HOU_WA_07_2026", "SEN_WY_2026"):
        v = res.get(rid); 
        if v: print(f"  {rid}: ladder share {v['share']:.3f} ({v['how']}, vol ${v['vol']:,.0f}; D mu {v['D']['mu'] if v['D'] else None}, R mu {v['R']['mu'] if v['R'] else None}) vs current {det[rid]['pred']} [{det[rid]['path']}]")
    json.dump(res, open(os.path.join(HERE, "ladder_shares.json"), "w"), indent=0, default=float)
