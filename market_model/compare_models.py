"""Leave-one-out comparison of probability->share model families on the training data."""
import csv, os, sys, numpy as np, mm
HERE = os.path.dirname(os.path.abspath(__file__))
files = ["training.csv"] + (["training_kalshi.csv"] if os.path.exists(os.path.join(HERE, "training_kalshi.csv")) and "--polymarket-only" not in sys.argv else [])
rows = [r for f in files for r in csv.DictReader(open(os.path.join(HERE, f)))]
p = np.array([float(r["p_t2"]) for r in rows]); y = np.array([float(r["label_share"]) for r in rows]); n = len(p)
L = np.array([mm.logit(x) for x in p]); Z = np.array([mm.phi_inv(x) for x in p]); comp = np.abs(p - 0.5) < 0.35
def loo(fp):
    err = np.array([fp(np.array([j for j in range(n) if j != i]), i) - y[i] for i in range(n)])
    return np.mean(np.abs(err)) * 100, np.mean(np.abs(err[comp])) * 100
def m_probit(tr, i):
    def loss(x):
        b, s = x
        if b <= 0.05 or s <= 0.005: return 1e9
        return np.mean(np.abs(np.array([mm.share_from_p(p[j], b, s) for j in tr]) - y[tr]))
    best = min((mm.nelder_mead(loss, [b0, s0], step=0.05) for b0 in (0.3, 1.0) for s0 in (0.05, 0.15)), key=lambda t: t[1])
    return mm.share_from_p(p[i], *best[0])
def m_sigma(tr, i):
    g = np.linspace(0.01, 0.3, 300); s = g[np.argmin([np.mean(np.abs(0.5 + gg * Z[tr] - y[tr])) for gg in g])]; return 0.5 + s * Z[i]
def m_knn(tr, i, k=9):
    return np.mean(y[tr[np.argsort(np.abs(L[tr] - L[i]))[:k]]])
def m_lad(tr, i):
    X = np.c_[np.ones(len(tr)), L[tr]]; w = np.ones(len(tr))
    for _ in range(30):
        c = np.linalg.lstsq(X * w[:, None], y[tr] * w, rcond=None)[0]; w = 1 / np.sqrt(np.maximum(np.abs(y[tr] - X @ c), 1e-4))
    return c @ np.r_[1, L[i]]
models = {"probit + longshot, MAE fit (used)": m_probit, "probit, sigma only": m_sigma,
          "linear in logit(p), OLS": lambda tr, i: np.polyval(np.polyfit(L[tr], y[tr], 1), L[i]),
          "linear in logit(p), LAD": m_lad,
          "cubic in logit(p), OLS": lambda tr, i: np.polyval(np.polyfit(L[tr], y[tr], 3), np.clip(L[i], L[tr].min(), L[tr].max())),
          "kNN (k=9) on logit p": m_knn, "linear in p, OLS": lambda tr, i: np.polyval(np.polyfit(p[tr], y[tr], 1), p[i]),
          "constant 0.5": lambda tr, i: 0.5}
res = {k: loo(f) for k, f in models.items()}
print(f"n={n} (competitive n={comp.sum()}) files={files}")
print(f"{'model':40s} LOO MAE all   LOO MAE competitive")
for k, (a, b) in sorted(res.items(), key=lambda t: t[1][0]): print(f"{k:40s} {a:6.2f}        {b:6.2f}")
