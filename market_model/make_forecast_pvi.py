"""EXPERIMENT (not the submission): add district/state PVI to the market model and compare.
Variant: races without a usable margin market get share from cubic(logit p) + beta*PVI, fitted on the 330 races
that have both market types; margin-market races are unchanged. Also a PVI-only baseline that uses the market's
national House popular-vote margin for the swing. Writes forecast_with_pvi.csv and a comparison."""
import csv, json, os, numpy as np, mm
HERE = os.path.dirname(os.path.abspath(__file__))
races = {r["race_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "..", "data (1)", "races_2026.csv")))}
det = {r["race_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "forecast_detail.csv")))}
tmpl = list(csv.DictReader(open(os.path.join(HERE, "forecast_template.csv"))))
K = json.load(open(os.path.join(HERE, "raw", "kalshi_2026.json")))
def lad(X, y, iters=60):
    w = np.ones(len(y)); c = None
    for _ in range(iters):
        c = np.linalg.lstsq(X * w[:, None], y * w, rcond=None)[0]; w = 1 / np.sqrt(np.maximum(np.abs(y - X @ c), 1e-4))
    return c
both = [(mm.logit(float(d["p_blend"])), float(d["share_mov"]), float(races[k]["pvi"])) for k, d in det.items() if d["path"] == "p+mov"]
L = np.array([b[0] for b in both]); y = np.array([b[1] for b in both]); pv = np.array([b[2] for b in both])
F0 = lambda L_, pv_: np.c_[np.ones_like(L_), L_, L_**2, L_**3]
F1 = lambda L_, pv_: np.c_[np.ones_like(L_), L_, L_**2, L_**3, pv_]
rng = np.random.default_rng(0); folds = rng.integers(0, 10, len(y))
for name, F in (("cross-market cubic (market only)", F0), ("cross-market cubic + PVI", F1)):
    err = np.zeros(len(y))
    for f in range(10):
        tr, te = folds != f, folds == f
        c = lad(F(L[tr], pv[tr]), y[tr]); err[te] = F(np.clip(L[te], L[tr].min(), L[tr].max()), pv[te]) @ c - y[te]
    print(f"{name:36s} 10-fold CV MAE vs margin-implied share: {np.mean(np.abs(err))*100:.2f} pts")
c1 = lad(F1(L, pv), y); lo, hi = L.min(), L.max()
print(f"PVI coefficient in the 2026 cross-market fit: {c1[-1]*100:.3f} share pts per PVI pt")
# national margin implied by Kalshi's House popular-vote ladder (median of P(D margin >= x))
lad_pts = sorted((float(m["yes_sub_title"].split("≥")[1].rstrip("%")), (float(m["yes_bid_dollars"]) + float(m["yes_ask_dollars"])) / 2) for m in K["house_popvote_margin"] if "≥" in m["yes_sub_title"])
nat = next((x for x, p in lad_pts if p <= 0.5), lad_pts[-1][0])
# linear interpolation for the median
for (x0, p0), (x1, p1) in zip(lad_pts, lad_pts[1:]):
    if p0 >= 0.5 >= p1: nat = x0 + (p0 - 0.5) / (p0 - p1) * (x1 - x0); break
print(f"market-implied national House margin (Kalshi ladder median): D+{nat:.1f}")
out = {}; rows = []
for rid, d in det.items():
    r = races[rid]; pvi = float(r["pvi"]); base = float(d["pred"])
    pvi_only = min(max(0.5 + (pvi + nat) / 200.0, 0.02), 0.98) if d["path"] != "fixed" else base
    if d["path"] == "p(cross)":
        x = min(max(mm.logit(float(d["p_blend"])), lo), hi); v = float(np.clip(c1 @ np.r_[1, x, x**2, x**3, pvi], 0.02, 0.98))
    else:
        v = base
    out[rid] = v; rows.append((rid, d["path"], base, v, pvi_only, pvi))
with open(os.path.join(HERE, "forecast_with_pvi.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["race_id", "race", "dem_side", "rep_side", "pred_dem_share", "note"]); w.writeheader()
    for t in tmpl:
        if t["pred_dem_share"].strip() == "": t["pred_dem_share"] = f"{out[t['race_id']]:.4f}"
        w.writerow({k: t.get(k, "") for k in w.fieldnames})
ch = [(abs(v - b), rid, b, v, pvi) for rid, path, b, v, po, pvi in rows if path == "p(cross)"]
print(f"\nraces changed (cross path): {len(ch)}; mean abs change {np.mean([c[0] for c in ch])*100:.2f} pts; >2 pts in {sum(c[0]>0.02 for c in ch)}")
for a, rid, b, v, pvi in sorted(ch, reverse=True)[:10]: print(f"  {rid:15s} PVI {pvi:+6.2f}  market-only {b:.3f} -> with PVI {v:.3f}")
scored = [t for t in rows if t[1] != "fixed"]
print(f"\nPVI-only baseline (0.5 + (PVI + D+{nat:.1f})/200) vs market-only forecast over {len(scored)} scored races: mean abs diff {np.mean([abs(t[2]-t[4]) for t in scored])*100:.2f} pts")
print("  by path:", {p: round(np.mean([abs(t[2]-t[4]) for t in scored if t[1]==p])*100, 2) for p in ("p+mov", "p(cross)", "p")})
big = sorted(((abs(t[2]-t[4]), t[0], t[2], t[4], t[5]) for t in scored), reverse=True)[:10]
print("  largest market-vs-PVI disagreements (race, market, PVI-only, PVI):"); [print(f"    {k:15s} {m:.3f} vs {pp:.3f}  PVI {pv:+.1f}") for _, k, m, pp, pv in big]
hs = [t for t in rows if t[0].startswith("HOU")]
print(f"\nHouse seats with share>0.5: market-only {sum(t[2]>0.5 for t in hs)}, with-PVI variant {sum(t[3]>0.5 for t in hs)}, PVI-only baseline {sum(t[4]>0.5 for t in hs)}")
