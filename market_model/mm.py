"""Shared helpers: normal distribution, probability->share calibration, margin-of-victory bucket parsing."""
import math, re, json

def phi(x):      # standard normal CDF
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def phi_inv(p):  # Acklam's inverse-normal approximation (|rel err| < 1.2e-9)
    p = min(max(p, 1e-9), 1 - 1e-9)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5; r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)

def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6); return math.log(p / (1 - p))

def expit(x):
    return 1 / (1 + math.exp(-x))

def calibrate_p(p, b):
    """Favourite-longshot correction: p_cal = expit(b * logit(p))."""
    return expit(b * logit(p))

def share_from_p(p, b, sigma):
    """Probability -> expected D two-party share: 0.5 + sigma * Phi^-1(p_cal)."""
    return 0.5 + sigma * phi_inv(calibrate_p(p, b))

def nelder_mead(f, x0, step=0.1, tol=1e-6, iters=2000):
    n = len(x0); pts = [list(x0)]
    for i in range(n):
        x = list(x0); x[i] += step; pts.append(x)
    vals = [f(x) for x in pts]
    for _ in range(iters):
        order = sorted(range(n + 1), key=lambda i: vals[i]); pts = [pts[i] for i in order]; vals = [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) < tol: break
        c = [sum(p[i] for p in pts[:-1]) / n for i in range(n)]
        xr = [c[i] + (c[i] - pts[-1][i]) for i in range(n)]; fr = f(xr)
        if fr < vals[0]:
            xe = [c[i] + 2 * (c[i] - pts[-1][i]) for i in range(n)]; fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = [c[i] + 0.5 * (pts[-1][i] - c[i]) for i in range(n)]; fc = f(xc)
            if fc < vals[-1]: pts[-1], vals[-1] = xc, fc
            else:
                for j in range(1, n + 1):
                    pts[j] = [pts[0][i] + 0.5 * (pts[j][i] - pts[0][i]) for i in range(n)]; vals[j] = f(pts[j])
    i = min(range(n + 1), key=lambda i: vals[i]); return pts[i], vals[i]

# ---------------- margin-of-victory buckets ----------------
_RANGE = re.compile(r"(?:by\s+|between\s+)(\d+(?:\.\d+)?)%?\s*(?:[-–]|to|and)\s*(\d+(?:\.\d+)?)%", re.I)
_ATLEAST = re.compile(r"(?:by\s+(?:at\s+least\s+)?(\d+(?:\.\d+)?)%\s+or\s+more|by\s+at\s+least\s+(\d+(?:\.\d+)?)%|at\s+least\s+(\d+(?:\.\d+)?)%)", re.I)
_LESS = re.compile(r"by\s+(?:less\s+than|under)\s+(\d+(?:\.\d+)?)%", re.I)

def parse_bucket(question, d_names=(), r_names=()):
    """Return (side, lo, hi) with side in {'D','R'} and margin interval in points (hi may be inf), or None."""
    q = question
    ql = q.lower()
    side = None
    if "democratic" in ql or "democrat" in ql: side = "D"
    elif "republican" in ql: side = "R"
    else:
        for n in d_names:
            if n and n.lower() in ql: side = "D"
        for n in r_names:
            if n and n.lower() in ql: side = "R"
    if side is None: return None
    m = _RANGE.search(q)
    if m: return side, float(m.group(1)), float(m.group(2))
    m = _ATLEAST.search(q)
    if m:
        v = next(g for g in m.groups() if g); return side, float(v), float("inf")
    m = _LESS.search(q)
    if m: return side, 0.0, float(m.group(1))
    if "win" in ql and "%" not in q: return side, 0.0, float("inf")   # catch-all "will the D candidate win the election?"
    return None

def fit_normal_to_buckets(buckets):
    """buckets: list of (lo, hi, prob) on the signed D-margin axis (points). Least-squares normal fit -> (mu, sd)."""
    tot = sum(p for _, _, p in buckets)
    if tot <= 0: return None
    bk = [(lo, hi, p / tot) for lo, hi, p in buckets]
    def loss(x):
        mu, ls = x; sd = math.exp(ls)
        return sum((p - (phi((hi - mu) / sd) - phi((lo - mu) / sd))) ** 2 for lo, hi, p in bk)
    # crude start from bucket midpoints
    mid = sum(((lo if lo > -1e9 else hi - 10) + (hi if hi < 1e9 else lo + 10)) / 2 * p for lo, hi, p in bk)
    best = None
    for s0 in (5.0, 10.0, 20.0):
        x, v = nelder_mead(loss, [mid, math.log(s0)], step=2.0)
        if best is None or v < best[1]: best = (x, v)
    mu, ls = best[0]; return mu, math.exp(ls), best[1]

def mov_buckets_from_markets(markets, d_names=(), r_names=()):
    """Turn a Polymarket MOV event's markets into signed-margin buckets. Skips placeholder markets."""
    out = []; vol = 0.0
    for m in markets:
        q = m.get("question") or ""
        if re.search(r"Person [A-Z]\b|not listed above|\bPerson\b", q): continue
        try:
            yes = float(json.loads(m["outcomePrices"])[0])
        except Exception:
            continue
        pb = parse_bucket(q, d_names, r_names)
        if not pb: continue
        side, lo, hi = pb
        if side == "D": out.append((lo, hi, yes))
        else: out.append((-hi, -lo, yes))
        vol += float(m.get("volumeNum") or 0)
    return out, vol


# ---------------- cubic-in-logit map fitted by least absolute deviations (IRLS) ----------------
def fit_lad_cubic(ps, ys, iters=60):
    import numpy as np
    L = np.array([logit(p) for p in ps]); y = np.array(ys)
    X = np.c_[np.ones(len(L)), L, L ** 2, L ** 3]; w = np.ones(len(L)); c = None
    for _ in range(iters):
        c = np.linalg.lstsq(X * w[:, None], y * w, rcond=None)[0]
        w = 1 / np.sqrt(np.maximum(np.abs(y - X @ c), 1e-4))
    return {"coef": [float(v) for v in c], "lo": float(L.min()), "hi": float(L.max())}

def share_from_p_cubic(p, cal):
    x = min(max(logit(p), cal["lo"]), cal["hi"])
    c = cal["coef"]; return c[0] + c[1] * x + c[2] * x ** 2 + c[3] * x ** 3
