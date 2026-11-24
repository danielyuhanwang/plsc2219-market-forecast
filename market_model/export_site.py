"""Write the forecast-site files into the template folder: forecast.csv with p_dem_win/lo_80/hi_80 (the site
needs these for ratings and ranges) and seat_sims.csv. The submission file at the top level stays six columns."""
import csv, os, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); TOP = os.path.join(HERE, ".."); SITE = os.path.join(TOP, "plsc2219-forecast-template-main")
det = {r["race_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "forecast_detail.csv")))}
sub = list(csv.DictReader(open(os.path.join(TOP, "forecast.csv"))))
with open(os.path.join(SITE, "forecast.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["race_id", "pred_dem_share", "p_dem_win", "lo_80", "hi_80"])
    for r in sub:
        d = det[r["race_id"]]; p = float(r["pred_dem_share"])
        if d["path"] == "fixed":
            w.writerow([r["race_id"], r["pred_dem_share"], r["pred_dem_share"], r["pred_dem_share"], r["pred_dem_share"]]); continue
        pw = 0.0 if r["race_id"] == "SEN_MT_2026" else float(d["p_win"])
        lo, hi = min(float(d["lo"]), p), max(float(d["hi"]), p)
        w.writerow([r["race_id"], f"{p:.4f}", f"{pw:.4f}", f"{lo:.4f}", f"{hi:.4f}"])
shutil.copy(os.path.join(HERE, "seat_sims.csv"), os.path.join(SITE, "seat_sims.csv"))
print("site files written to", SITE)
