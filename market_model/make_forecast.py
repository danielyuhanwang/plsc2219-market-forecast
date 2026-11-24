"""Market-only 2026 forecast: combine Polymarket + Kalshi win probabilities (calibrated map -> share)
with Polymarket margin-of-victory bucket markets; write forecast.csv, seat_sims.csv, diagnostics."""
import csv, json, os, re, math, datetime
import numpy as np
import mm
HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.join(HERE, "..")
DATA = os.path.join(TOP, "data (1)")
races = list(csv.DictReader(open(os.path.join(DATA, "races_2026.csv"))))
cal = json.load(open(os.path.join(HERE, "calibration.json")))
PM = json.load(open(os.path.join(HERE, "raw", "polymarket_2026.json")))
KS = json.load(open(os.path.join(HERE, "raw", "kalshi_2026.json")))
B, SIG = cal["b"], cal["sigma"]
CUB = cal["cubic_lad"]; RESID = CUB["resid_sd"]   # probability->share map chosen by grouped LOO (see compare_models.py)
OTHER_SHARE = 0.03          # two-party conversion of a margin in % of all votes
MOV_V0 = 5000.0             # blend weight w = vol/(vol+V0)
AT_LARGE = {"AK", "DE", "ND", "SD", "VT", "WY"}

def lastnames(s):
    out = []
    for n in (s or "").split(";"):
        toks = [t.strip(" .,") for t in n.strip().split()]
        toks = [t for t in toks if t.lower() not in ("jr", "sr", "ii", "iii", "iv")]
        if toks: out.append(toks[-1].lower())
    return out

def fnum(x):
    try: return float(x)
    except Exception: return None

# ---------------- Polymarket ----------------
def pm_price(m):
    bb, ba = fnum(m.get("bestBid")), fnum(m.get("bestAsk"))
    if bb is not None and ba is not None and 0 < ba - bb <= 0.12:
        return (bb + ba) / 2
    try: return float(json.loads(m["outcomePrices"])[0])
    except Exception: return None

def placeholder(m):
    q = m.get("question") or ""
    return bool(re.search(r"\bPerson [A-Z]\b|\bCandidate [A-Z]\b|^Will [A-Z] win|not listed above", q)) or ((m.get("volumeNum") or 0) == 0 and pm_price(m) == 0.5)

def classify(text, dn, rn):
    t = text.lower()
    if any(n in t for n in dn): return "Dname"
    if any(n in t for n in rn): return "Rname"
    if "democrat" in t: return "Dparty"
    if "republican" in t: return "Rparty"
    if "independent" in t or "another party" in t or "third party" in t: return "other"
    return None

def side_prob(cls_price, r):
    """D-side probability from classified prices {cls: price}; returns (p, used_1minusR)."""
    dsp, rsp = r["d_side_party"], r["r_side_party"]
    pD = None
    if dsp == "D":
        pD = cls_price.get("Dparty", cls_price.get("Dname"))
    elif dsp == "I":
        pD = cls_price.get("Dname", cls_price.get("other"))
    elif dsp == "D;I":   # Montana: Democrat + independent
        parts = [cls_price.get("Dparty", cls_price.get("Dname")), cls_price.get("other")]
        parts = [p for p in parts if p is not None]
        pD = sum(parts) if parts else None
    pR = None
    if rsp == "R": pR = cls_price.get("Rparty", cls_price.get("Rname"))
    elif rsp == "I": pR = cls_price.get("Rname", cls_price.get("other"))
    third = any(v > 0.03 for k, v in cls_price.items() if k == "other") and dsp == "D" and rsp == "R"
    if pD is not None and pR is not None and not third and dsp in ("D",) and rsp == "R":
        return (pD + (1 - pR)) / 2
    if pD is not None: return pD
    if pR is not None and not third: return 1 - pR
    return None

def polymarket(r):
    rec = PM["races"].get(r["race_id"]) or {}
    w = rec.get("winner")
    dn, rn = lastnames(r["dem_candidate"]), lastnames(r["rep_candidate"])
    p = vol = None
    if w:
        cp = {}; vol = 0.0
        for m in w["markets"]:
            if placeholder(m): continue
            c = classify(m["question"], dn, rn); pr = pm_price(m)
            if c and pr is not None:
                if c in cp and c.endswith("name"): cp[c] += pr   # two D-side names (Montana)
                else: cp[c] = pr
                vol += float(m.get("volumeNum") or 0)
        p = side_prob(cp, r)
    mov = rec.get("mov"); mov_fit = None; mov_vol = 0.0; mov_note = ""
    if mov:
        bks, mov_vol = mm.mov_buckets_from_markets(mov["markets"], dn + (["democrat"] if r["d_side_party"] != "I" else []), rn)
        tot = sum(b[2] for b in bks)
        if len(bks) >= 4 and 0.8 <= tot <= 1.25 and mov_vol >= 500:
            fit = mm.fit_normal_to_buckets(bks)
            if fit: mov_fit = fit
        else:
            mov_note = f"mov skipped (n={len(bks)}, sum={tot:.2f}, vol={mov_vol:.0f})"
    return p, vol, mov_fit, mov_vol, mov_note

# ---------------- Kalshi ----------------
def kalshi_index():
    idx = {}
    for et, e in KS["events"].items():
        key = None
        m = re.match(r"^KXHOUSERACE-([A-Z]{2})(\d{2}|AL)-26$", et)
        if m: key = ("house", m.group(1), 1 if m.group(2) == "AL" else int(m.group(2)))
        elif re.match(r"^SENATE([A-Z]{2})(S?)-26$", et):
            mm_ = re.match(r"^SENATE([A-Z]{2})(S?)-26$", et); key = ("senate", mm_.group(1), 1 if mm_.group(2) else 0)
        elif et == "KXALASKAHOUSE-26": key = ("house", "AK", 1)
        else:
            t = re.search(r"\b([A-Z]{2})-(\d{2})\b", e.get("title") or "") or re.match(r"^(?:KX)?HOUSE([A-Z]{2})(\d{1,2})-26$", et)
            if t: key = ("house", t.group(1), int(t.group(2)))
        if key: idx.setdefault(key, []).append(e)
    return idx
KIDX = kalshi_index()

def kalshi(r):
    key = ("senate", r["state"], int(r["special"])) if r["office"] == "senate" else ("house", r["state"], int(float(r["district"])))
    evs = KIDX.get(key, [])
    dn, rn = lastnames(r["dem_candidate"]), lastnames(r["rep_candidate"])
    dsp, rsp = r["d_side_party"], r["r_side_party"]
    ps, vs = [], []
    for e in evs:
        D = R = T = 0.0; vol = 0.0; any_price = False
        for m in e["markets"]:
            bid, ask, last = fnum(m.get("yes_bid_dollars")), fnum(m.get("yes_ask_dollars")), fnum(m.get("last_price_dollars"))
            if bid is not None and ask is not None and ask - bid <= 0.12 and ask > 0: pr = (bid + ask) / 2
            elif last is not None: pr = last
            else: continue
            any_price = True
            vol += fnum(m.get("volume_fp")) or 0
            name = (m.get("yes_sub_title") or "").lower(); suf = (m.get("ticker") or "").split("-")[-1]
            side = None
            if any(n in name for n in dn): side = "D"
            elif any(n in name for n in rn): side = "R"
            elif "democratic party" in name: side = "D" if dsp == "D" else None
            elif "republican party" in name: side = "R" if rsp == "R" else None
            elif suf == "D" or suf == "DEM": side = "D" if dsp == "D" else None
            elif suf == "R" or suf == "GOP": side = "R" if rsp == "R" else None
            T += pr
            if side == "D": D += pr
            elif side == "R": R += pr
        if not any_price or (D == 0 and R == 0): continue
        if 0.85 <= T <= 1.15: D, R = D / T, R / T
        p = D if D > 0 else 1 - R
        if D > 0 and R > 0 and dsp == "D" and rsp == "R" and T >= 0.85: p = (D + 1 - R) / 2
        ps.append(p); vs.append(max(vol, 1.0))
    if not ps: return None, None
    return sum(p * v for p, v in zip(ps, vs)) / sum(vs), sum(vs)

# ---------------- main ----------------
rows = []; detail = []
for r in races:
    rid = r["race_id"]
    p_pm, v_pm, mov_fit, mov_vol, mov_note = polymarket(r)
    p_k, v_k = kalshi(r)
    fixed = r["fixed_prediction"].strip()
    d = {"race_id": rid, "p_pm": p_pm, "vol_pm": v_pm, "p_kalshi": p_k, "vol_kalshi": v_k,
         "mov_mu": mov_fit[0] if mov_fit else None, "mov_sd": mov_fit[1] if mov_fit else None, "mov_vol": mov_vol, "note": mov_note}
    if fixed:
        f = float(fixed)
        d.update(pred=f, p_win=f, lo=f, hi=f, path="fixed", share_p=None, share_mov=None, w=0)
        rows.append(d); detail.append(d); continue
    # blended market probability
    parts = [(p, max(v or 0, 1000.0)) for p, v in ((p_pm, v_pm), (p_k, v_k)) if p is not None]
    p = sum(p * v for p, v in parts) / sum(v for _, v in parts) if parts else None
    share_p = mm.share_from_p_cubic(p, CUB) if p is not None else None
    share_mov = p_mov = None; w = 0.0
    if mov_fit and r["race_type"] != "combined_D_side":   # Montana MOV prices Alme vs runner-up, not the combined share
        mu, sd, _ = mov_fit
        share_mov = 0.5 + mu / (200.0 * (1 - OTHER_SHARE)); p_mov = mm.phi(mu / sd)
        # margin-only where the margin book is usable; fall back to a volume-weighted blend with the
        # win-probability path only when the two markets disagree by more than 15 points (stale/mispriced book)
        w = 1.0
        if p is not None:
            diff = abs(p_mov - p); w_floor = 0.3 * mov_vol / (mov_vol + MOV_V0)
            if diff > 0.05: w = max(w_floor, 1.0 - (diff - 0.05) / 0.10) if diff < 0.15 else w_floor
    if share_p is None and share_mov is None:
        d.update(pred=None, path="fallback"); rows.append(d); detail.append(d); continue
    if share_p is None: w = 1.0
    pred = w * (share_mov or 0) + (1 - w) * (share_p or 0)
    pred = min(max(pred, 0.02), 0.98)
    p_win = w * (p_mov or 0) + (1 - w) * (p if p is not None else p_mov)
    sd_mov = (mov_fit[1] / (200.0 * (1 - OTHER_SHARE))) if (mov_fit and share_mov is not None) else RESID
    sd = max(0.015, w * sd_mov + (1 - w) * RESID)
    if r["race_type"] == "combined_D_side": p_win = 0.0
    lo, hi = max(0.0, pred - 1.2816 * sd), min(1.0, pred + 1.2816 * sd)
    path = "p+mov" if (share_mov is not None and share_p is not None) else ("mov" if share_p is None else "p")
    d.update(pred=pred, p_win=p_win, lo=lo, hi=hi, path=path, share_p=share_p, share_mov=share_mov, w=w, p_blend=p, sd=sd)
    rows.append(d); detail.append(d)

# fallback: regress market-implied share on PVI across covered standard races
fb = [d for d in rows if d.get("path") == "fallback"]
if fb:
    X = [(float(r["pvi"]), d["pred"]) for r, d in zip(races, rows) if d.get("path") in ("p", "p+mov", "mov") and r["race_type"] == "standard"]
    xs, ys = np.array([x for x, _ in X]), np.array([y for _, y in X]); a, b0 = np.polyfit(xs, ys, 1)
    for r, d in zip(races, rows):
        if d.get("path") == "fallback":
            d["pred"] = float(np.clip(a * float(r["pvi"]) + b0, 0.02, 0.98)); d["p_win"] = float(d["pred"] > 0.5); d["sd"] = RESID
            d["lo"], d["hi"] = max(0, d["pred"] - 1.2816 * RESID), min(1, d["pred"] + 1.2816 * RESID)
            print("FALLBACK (PVI regression) used for", r["race_id"])


# ---- races with no usable MOV market: win price + district/state PVI -> share ----
# A win price above ~95% says who wins but not by how much, so for these races the share comes from a map
# fitted (least absolute deviations) on the races that have BOTH a win market and a usable margin market tonight:
#   margin-implied share ~ cubic(logit p) + beta * PVI.   PVI is the only non-market input and is used only here.
bothrows = [(mm.logit(d["p_blend"]), d["share_mov"], float(r["pvi"]), d["mov_vol"]) for r, d in zip(races, rows) if d.get("path") == "p+mov"]
if len(bothrows) >= 50:
    xb = np.array([x for x, _, _, _ in bothrows]); yb = np.array([y for _, y, _, _ in bothrows]); pb = np.array([v for _, _, v, _ in bothrows])
    def lad_fit(X, y, iters=60):
        w = np.ones(len(y)); c = None
        for _ in range(iters):
            c = np.linalg.lstsq(X * w[:, None], y * w, rcond=None)[0]; w = 1 / np.sqrt(np.maximum(np.abs(y - X @ c), 1e-4))
        return c
    F = lambda x, v: np.c_[np.ones_like(x), x, x ** 2, x ** 3, v]
    coef = lad_fit(F(xb, pb), yb); lo_x, hi_x = xb.min(), xb.max()
    rng_cv = np.random.default_rng(0); folds = rng_cv.integers(0, 10, len(yb)); err = np.zeros(len(yb))
    for f_ in range(10):
        tr, te = folds != f_, folds == f_
        c_ = lad_fit(F(xb[tr], pb[tr]), yb[tr]); err[te] = F(np.clip(xb[te], xb[tr].min(), xb[tr].max()), pb[te]) @ c_ - yb[te]
    cross_resid = float(np.sqrt(np.mean(err ** 2)))
    json.dump({"coef": [float(c) for c in coef], "features": ["1", "logit p", "logit p^2", "logit p^3", "pvi"], "x_range": [float(lo_x), float(hi_x)],
               "cv_mae": float(np.mean(np.abs(err))), "cv_rmse": cross_resid, "n": len(bothrows)}, open(os.path.join(HERE, "cross_market_fit.json"), "w"), indent=1)
    for r, d in zip(races, rows):
        if d.get("path") == "p" and r["race_type"] != "combined_D_side":
            xv = min(max(mm.logit(d["p_blend"]), lo_x), hi_x)
            d["share_cross"] = float((F(np.array([xv]), np.array([float(r["pvi"])])) @ coef)[0]); d["pred"] = float(np.clip(d["share_cross"], 0.02, 0.98))
            d["sd"] = max(0.015, cross_resid); d["lo"], d["hi"] = max(0.0, d["pred"] - 1.2816 * d["sd"]), min(1.0, d["pred"] + 1.2816 * d["sd"])
            d["path"] = "p+pvi"
    print(f"win-price + PVI map: n={len(bothrows)} 10-fold CV MAE={np.mean(np.abs(err))*100:.2f} pts (PVI coef {coef[-1]*100:.2f} share pts/PVI pt); applied to {sum(1 for d in rows if d.get('path')=='p+pvi')} races")

# ---- Kalshi vote-percentage ladders (KXVOTEGENERAL): a direct market price for each candidate's vote share ----
# Combined with the existing estimate by traded volume: margin-market races weight by MOV volume vs ladder volume;
# win-price+PVI races use w = vol/(vol + 2000). Ladders that disagree with the current estimate by >15 pts are
# ignored as parse failures. Louisiana jungle races and first-round ladders in ranked-choice races are excluded.
import ladders as _lad
try:
    LAD = _lad.race_shares(json.load(open(os.path.join(HERE, "raw", "kalshi_votegeneral_2026.json"))), races)
except FileNotFoundError:
    LAD = {}
n_lad = 0
for r, d in zip(races, rows):
    L_ = LAD.get(r["race_id"])
    if not L_ or d["path"] in ("fixed", "fallback") or r["race_type"] == "combined_D_side" or d.get("pred") is None: continue
    if abs(L_["share"] - d["pred"]) > 0.15 or L_["vol"] <= 0: continue
    if d["path"] == "p+mov": wl = L_["vol"] / (L_["vol"] + d["mov_vol"])
    else: wl = L_["vol"] / (L_["vol"] + 2000.0)
    d["pred_before_ladder"] = d["pred"]; d["ladder_share"] = L_["share"]; d["ladder_vol"] = L_["vol"]; d["w_ladder"] = wl
    d["pred"] = float(np.clip(wl * L_["share"] + (1 - wl) * d["pred"], 0.02, 0.98))
    d["sd"] = wl * L_["sd_share"] + (1 - wl) * d["sd"]; d["lo"], d["hi"] = max(0.0, d["pred"] - 1.2816 * d["sd"]), min(1.0, d["pred"] + 1.2816 * d["sd"])
    d["path"] += "+ladder"; n_lad += 1
print(f"vote-share ladders: {len(LAD)} races parsed, combined into {n_lad}")

# write forecast.csv: the original template (columns A-F, original row order), with only pred_dem_share filled.
# Prefilled fixed races keep the template's own value.
pred_by_id = {r["race_id"]: d["pred"] for r, d in zip(races, rows)}
tmpl_rows = list(csv.DictReader(open(os.path.join(HERE, "forecast_template.csv"))))
with open(os.path.join(TOP, "forecast.csv"), "w", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=["race_id", "race", "dem_side", "rep_side", "pred_dem_share", "note"])
    wr.writeheader()
    for t in tmpl_rows:
        if t["pred_dem_share"].strip() == "":
            t["pred_dem_share"] = f"{pred_by_id[t['race_id']]:.4f}"
        wr.writerow({k: t.get(k, "") for k in wr.fieldnames})
with open(os.path.join(HERE, "forecast_detail.csv"), "w", newline="") as f:
    keys = ["race_id", "path", "pred", "p_win", "lo", "hi", "p_pm", "vol_pm", "p_kalshi", "vol_kalshi", "p_blend", "share_p", "share_cross", "mov_mu", "mov_sd", "mov_vol", "share_mov", "w", "ladder_share", "ladder_vol", "w_ladder", "pred_before_ladder", "sd", "note"]
    wr = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore"); wr.writeheader()
    for d in detail: wr.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()})

# seat simulations: shared national shock + race-specific noise
rng = np.random.default_rng(2026); N = 10000
pred = np.array([d["pred"] for d in rows]); sd = np.array([d.get("sd") or 0.0 for d in rows])
nat = 0.02; race_sd = np.sqrt(np.clip(sd ** 2 - nat ** 2, 0.005 ** 2, None))
fixedmask = np.array([d["path"] == "fixed" for d in rows]); race_sd[fixedmask] = 0.0
shock = rng.normal(0, nat, size=(N, 1)) * (~fixedmask)
sims = pred[None, :] + shock + rng.normal(0, 1, size=(N, len(rows))) * race_sd[None, :]
house = np.array([r["office"] == "house" for r in races]); senate = ~house
mt = np.array([r["race_type"] == "combined_D_side" for r in races])
win = sims > 0.5; win[:, mt] = False
house_seats = win[:, house].sum(1); senate_seats = 34 + win[:, senate].sum(1)
with open(os.path.join(HERE, "seat_sims.csv"), "w", newline="") as f:
    wr = csv.writer(f); wr.writerow(["sim", "house_dem_seats", "senate_dem_seats"])
    for i in range(N): wr.writerow([i + 1, int(house_seats[i]), int(senate_seats[i])])

# diagnostics
from collections import Counter
print("paths:", Counter(d["path"] for d in rows))
print(f"House: expected D seats {sum(d['p_win'] for r, d in zip(races, rows) if r['office']=='house'):.1f}, sim median {np.median(house_seats):.0f}, 80% {np.percentile(house_seats,10):.0f}-{np.percentile(house_seats,90):.0f}, P(218+)={np.mean(house_seats>=218):.3f}")
print(f"Senate: expected D seats {34+sum(d['p_win'] for r, d in zip(races, rows) if r['office']=='senate'):.1f}, sim median {np.median(senate_seats):.0f}, 80% {np.percentile(senate_seats,10):.0f}-{np.percentile(senate_seats,90):.0f}, P(51+)={np.mean(senate_seats>=51):.3f}")
print("\nSenate:")
for r, d in zip(races, rows):
    if r["office"] == "senate":
        print(f"  {r['race_id']:12s} {r['dem_candidate'][:22]:22s} vs {r['rep_candidate'][:18]:18s} pred={d['pred']:.3f} pwin={d['p_win']:.2f} pPM={d['p_pm'] if d['p_pm'] is None else round(d['p_pm'],3)} pK={d['p_kalshi'] if d['p_kalshi'] is None else round(d['p_kalshi'],3)} mov_mu={d['mov_mu'] if d['mov_mu'] is None else round(d['mov_mu'],1)} w={d['w']:.2f} {d['note']}")
print("\nClosest 25 House races:")
close = sorted([(abs(d["pred"] - 0.5), r, d) for r, d in zip(races, rows) if r["office"] == "house" and d["path"] != "fixed"], key=lambda t: t[0])[:25]
for _, r, d in close:
    print(f"  {r['race_id']:15s} pred={d['pred']:.3f} pwin={d['p_win']:.2f} pPM={d['p_pm'] if d['p_pm'] is None else round(d['p_pm'],3)} pK={d['p_kalshi'] if d['p_kalshi'] is None else round(d['p_kalshi'],3)} share_p={d.get('share_p') and round(d['share_p'],3)} share_mov={d.get('share_mov') and round(d['share_mov'],3)} w={d['w']:.2f}")
print("\nMOV notes (skipped):", sum(1 for d in rows if d["note"]))
