"""Fit share = 0.5 + sigma * Phi^-1(expit(b * logit p)) by minimising MAE; leave-one-out error.
Uses training.csv (Polymarket) and, if present, training_predictit.csv. Fits per source and pooled,
writes calibration.json from the pooled fit (or Polymarket-only if --polymarket-only)."""
import csv, json, os, sys, statistics
import mm
HERE = os.path.dirname(os.path.abspath(__file__))
def load(fn, source):
    if not os.path.exists(os.path.join(HERE, fn)): return []
    return [(float(r["p_t2"]), float(r["label_share"]), r["kind"], r["slug"], source) for r in csv.DictReader(open(os.path.join(HERE, fn)))]
pm = load("training.csv", "polymarket"); ka = load("training_kalshi.csv", "kalshi"); pi = load("training_predictit.csv", "predictit")

def fit(d):
    def loss(x):
        b, s = x
        if b <= 0.05 or s <= 0.005: return 1e9
        return sum(abs(mm.share_from_p(p, b, s) - y) for p, y, *_ in d) / len(d)
    best = None
    for b0 in (0.3, 0.8, 1.3):
        for s0 in (0.05, 0.1, 0.2):
            x, v = mm.nelder_mead(loss, [b0, s0], step=0.05)
            if best is None or v < best[1]: best = (x, v)
    return best

def loo(d):
    errs = []
    for i in range(len(d)):
        (bi, si), _ = fit(d[:i] + d[i + 1:]); p, y = d[i][0], d[i][1]
        errs.append(mm.share_from_p(p, bi, si) - y)
    return errs

report = {}
for name, d in (("polymarket", pm), ("kalshi", ka), ("pooled", pm + ka)):
    if len(d) < 10: continue
    (b, s), mae = fit(d); errs = loo(d) if len(d) <= 400 else None
    mae_loo = sum(abs(e) for e in errs) / len(errs) if errs else None
    comp = [abs(e) for e, (p, *_ ) in zip(errs, d) if 0.15 <= p <= 0.85] if errs else []
    report[name] = {"b": b, "sigma": s, "n": len(d), "mae_insample": mae, "mae_loo": mae_loo, "resid_sd": statistics.pstdev(errs) if errs else None,
                    "mae_loo_competitive": (sum(comp) / len(comp)) if comp else None, "n_competitive": len(comp)}
    print(f"{name:10s} n={len(d):3d}  b={b:.3f} sigma={s:.4f}  MAE in={mae*100:.2f}  LOO={mae_loo*100 if mae_loo else float('nan'):.2f}  LOO competitive={report[name]['mae_loo_competitive']*100 if comp else float('nan'):.2f} (n={len(comp)})")
    # cross-source check: fit on one source, test on the other
if pm and ka:
    for a, b_, na, nb in ((pm, ka, "polymarket", "kalshi"), (ka, pm, "kalshi", "polymarket")):
        (bb, ss), _ = fit(a); e = [abs(mm.share_from_p(p, bb, ss) - y) for p, y, *_ in b_]
        print(f"fit on {na:10s} -> test on {nb:10s}: MAE={sum(e)/len(e)*100:.2f} (n={len(e)})")
# ---- cubic-in-logit LAD map (chosen by grouped leave-one-race-out comparison, see compare_models.py) ----
import numpy as np
pool = pm + ka
grp = [f"{k}:{round(y,4)}" for p, y, k, *_ in pool]
errs = []
for g in set(grp):
    tr = [i for i in range(len(pool)) if grp[i] != g]; te = [i for i in range(len(pool)) if grp[i] == g]
    c = mm.fit_lad_cubic([pool[i][0] for i in tr], [pool[i][1] for i in tr])
    errs += [mm.share_from_p_cubic(pool[i][0], c) - pool[i][1] for i in te]
cub = mm.fit_lad_cubic([p for p, *_ in pool], [y for _, y, *_ in pool])
cub.update(n=len(pool), mae_loo_grouped=float(np.mean(np.abs(errs))), resid_sd=float(np.std(errs)))
print(f"cubic LAD map: n={len(pool)} grouped-LOO MAE={cub['mae_loo_grouped']*100:.2f} pts, resid SD={cub['resid_sd']*100:.2f}")
choice = "polymarket" if "--polymarket-only" in sys.argv or "pooled" not in report else "pooled"
c = report[choice]; c["source"] = choice; c["horizon_days"] = 2; c["cubic_lad"] = cub; c["map"] = "cubic_lad"
json.dump(c, open(os.path.join(HERE, "calibration.json"), "w"), indent=1)
json.dump(report, open(os.path.join(HERE, "calibration_report.json"), "w"), indent=1)
print("calibration.json <-", choice)
