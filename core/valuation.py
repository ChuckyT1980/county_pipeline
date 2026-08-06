"""
core/valuation.py

The valuation + excess-proceeds prediction layer. Trains on real historical
auction sales (Fresno sold lists joined to the roll) to answer, BEFORE the
county publishes anything:

  - what will this parcel fetch at auction?      (predicted_sale_price)
  - will the sale leave excess proceeds?         (p_excess, excess_expected)

Two modes:
  roll-wide screen  — every parcel ranked by predicted sale price (which
                      properties would throw off big surpluses if sold)
  listed            — current auction list joined with known min_bid:
                      excess_expected = max(0, price_pred - min_bid)

INTEGRITY: never invents a price. If the model has no training data for a
county, output is empty rather than fabricated. Backtests are reported in
real dollars vs the county's own published figures.
"""
import csv
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .county import CountyConfig

ROOT = Path(__file__).resolve().parent.parent

NUM_FEATURES = [
    "TOTAL_ASSESSED_VALUE", "ASSESS_LAND_VAL", "ASSESS_IMP_VAL",
    "LOT_AREA", "ACREAGE",
]

CAT_FEATURES = ["USE_PRIMARY", "USE_SECONDARY"]


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return np.nan


def _load_roll(cfg) -> pd.DataFrame:
    roll = cfg.roll_path()
    if not roll.exists():
        return pd.DataFrame()
    df = pd.read_csv(roll, low_memory=False, dtype=str)
    df = df.rename(columns={cfg.assessor.apn_field: "APN"}) \
        if cfg.assessor.apn_field in df.columns and "APN" not in df.columns else df
    apn_col = "APN" if "APN" in df.columns else "apn"
    if apn_col not in df.columns:
        return pd.DataFrame()
    df["apn"] = df[apn_col].astype(str).str.replace("-", "", regex=False)
    return df


def _labeled_sales(cfg) -> pd.DataFrame:
    """Historical sold results for this county with roll features joined.
    Standard location: data/counties/<county>/sold_results.csv, but also
    picks up fresno/fresno_historical_sales.csv (legacy path)."""
    paths = [cfg.data_dir() / "sold_results.csv",
             ROOT / "fresno" / "fresno_historical_sales.csv",
             ROOT / "tax_pipeline" / "fresno_historical_sales.csv"]
    roll = _load_roll(cfg)
    parts = []
    for p in paths:
        if not p.exists():
            continue
        df = pd.read_csv(p, dtype=str)
        if "apn" not in df.columns:
            continue
        df["apn"] = df["apn"].astype(str).str.replace("-", "", regex=False)
        df["county"] = cfg.county
        if roll is not None and len(roll):
            df = df.merge(roll, on="apn", how="left",
                          suffixes=("", "_roll"))
        parts.append(df)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    out["sales_price"] = out["sales_price"].map(_num)
    out["min_bid"] = out["min_bid"].map(_num)
    out["excess_proceeds"] = out["excess_proceeds"].map(_num)
    out = out[out["sales_price"].notna() & out["sales_price"] > 0]
    # dedupe across overlapping source paths (sold_results.csv vs the
    # legacy fresno_historical_sales.csv can carry the same sales twice)
    out = out.drop_duplicates(subset=["county", "apn", "auction_date",
                                      "sales_price"])
    return out


def pooled_sales() -> pd.DataFrame:
    """Every county's sold results on disk, one training frame. The pool
    is the point of the unified engine: one price model across counties
    instead of 58 models trained on a handful of sales each. Auction
    platforms (RealAuction/GovEase/bid4assets archives) feed this pool."""
    parts = []
    for d in sorted((ROOT / "data" / "counties").glob("*/sold_results.csv")):
        df = pd.read_csv(d, dtype=str)
        df["county"] = d.parent.name
        df["apn"] = df["apn"].astype(str).str.replace("-", "", regex=False)
        parts.append(df)
    legacy = ROOT / "fresno" / "fresno_historical_sales.csv"
    if legacy.exists():
        df = pd.read_csv(legacy, dtype=str)
        df["county"] = "fresno"
        df["apn"] = df["apn"].astype(str).str.replace("-", "", regex=False)
        parts.append(df)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    out["sales_price"] = out["sales_price"].map(_num)
    out["min_bid"] = out["min_bid"].map(_num)
    out["excess_proceeds"] = out["excess_proceeds"].map(_num)
    out = out[out["sales_price"].notna() & out["sales_price"] > 0]
    return out


def backtest(cfg: CountyConfig, test_year: int | None = None) -> dict:
    """Train on sales BEFORE test_year, predict the test-year sales, and
    compare predicted excess vs the county's published excess. This is the
    'see it before the county prints it' proof."""
    labels = _labeled_sales(cfg)
    if not len(labels):
        print(f"[valuation:{cfg.county}] no labeled sales")
        return {}
    if "auction_date" not in labels.columns:
        print(f"[valuation:{cfg.county}] no auction_date — can't split")
        return {}
    dates = pd.to_datetime(labels["auction_date"], errors="coerce")
    test_year = test_year or int(dates.dropna().dt.year.max())
    train = labels[dates.dt.year < test_year]
    test = labels[dates.dt.year == test_year]
    if len(train) < 10 or len(test) < 3:
        print(f"[valuation:{cfg.county}] split too thin: train={len(train)} "
              f"test={len(test)}")
        return {}

    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, median_absolute_error

    Xt = _features(train)
    Xe = _features(test).reindex(columns=Xt.columns, fill_value=0)
    reg = HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.06, max_leaf_nodes=15,
        l2_regularization=1.0, random_state=7)
    reg.fit(Xt, np.log(train["sales_price"].values))
    pred = np.exp(reg.predict(Xe))

    test = test.assign(pred_price=pred)
    test["pred_excess"] = (pred - test["min_bid"]).clip(lower=0)
    test["actual_excess"] = test["excess_proceeds"].fillna(
        test["sales_price"] - test["min_bid"])

    mae = mean_absolute_error(test["sales_price"], pred)
    mdae = median_absolute_error(test["sales_price"], pred)
    # excess needs a min bid — rows without one (e.g. 2006/2008 summaries
    # that omitted it) are priced but not excess-evaluable
    ev = test[test["min_bid"].notna()]
    excess_mae = mean_absolute_error(ev["actual_excess"], ev["pred_excess"])
    rank_corr = ev["pred_excess"].rank().corr(ev["actual_excess"].rank())

    print(f"[valuation:{cfg.county}] BACKTEST train={len(train)} "
          f"(<= {test_year - 1}) -> test={len(test)} ({test_year})")
    print(f"  price MAE ${mae:,.0f} | median ${mdae:,.0f} | "
          f"excess MAE ${excess_mae:,.0f} | rank corr {rank_corr:.2f}")
    top = test.nlargest(6, "actual_excess")[
        ["apn", "min_bid", "sales_price", "actual_excess",
         "pred_price", "pred_excess"]]
    print(top.to_string(index=False))
    return {"n_train": len(train), "n_test": len(test), "price_mae": mae,
            "excess_mae": excess_mae, "rank_corr": rank_corr}


def _features(df: pd.DataFrame) -> pd.DataFrame:
    feats = {}
    for f in NUM_FEATURES:
        if f in df.columns:
            feats[f] = df[f].map(_num)
    feats["price_over_land"] = np.log1p(
        feats.get("TOTAL_ASSESSED_VALUE", pd.Series(0, index=df.index))) - \
        np.log1p(feats.get("ASSESS_LAND_VAL", pd.Series(0, index=df.index)))
    for f in CAT_FEATURES:
        if f in df.columns:
            feats[f] = df[f].fillna("").astype(str)
    X = pd.DataFrame(feats)
    # one-hot categoricals
    X = pd.get_dummies(X, columns=[f for f in CAT_FEATURES if f in X.columns])
    return X


def train_value_model(cfg: CountyConfig, min_train: int = 20) -> dict:
    """Train sale-price + excess models on this county's historical sales.
    Returns metadata (n, cv error, model refs) or empty dict if labels are
    too few — the caller then falls back to nothing, never to guesses."""
    labels = _labeled_sales(cfg)
    if len(labels) < min_train:
        print(f"[valuation:{cfg.county}] only {len(labels)} labeled sales "
              f"(need {min_train}) — no model, no fabricated prices")
        return {}

    X = _features(labels)
    y_price = labels["sales_price"].map(math.log)
    has_minbid = labels["min_bid"].notna()
    y_excess = (labels["sales_price"] > labels["min_bid"]).astype(int)

    from sklearn.ensemble import HistGradientBoostingRegressor, \
        HistGradientBoostingClassifier
    from sklearn.model_selection import cross_val_predict
    from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score

    reg = HistGradientBoostingRegressor(
        max_iter=200, learning_rate=0.06, max_leaf_nodes=15,
        l2_regularization=1.0, random_state=7)
    pred_log = cross_val_predict(reg, X, y_price, cv=min(5, len(labels)))
    pred_price = np.exp(pred_log)
    mae = mean_absolute_error(labels["sales_price"], pred_price)
    r2 = r2_score(labels["sales_price"], pred_price)
    # train final models on all data
    reg.fit(X, y_price)
    clf = None
    auc = None
    if has_minbid.any() and y_excess.sum() > 0:
        clf = HistGradientBoostingClassifier(
            max_iter=200, learning_rate=0.06, max_leaf_nodes=15,
            l2_regularization=1.0, random_state=7)
        Xb = X[has_minbid]
        yb = y_excess[has_minbid]
        if yb.sum() >= 5 and (len(yb) - yb.sum()) >= 5:
            try:
                auc = roc_auc_score(yb, cross_val_predict(
                    clf, Xb, yb, cv=min(4, len(yb)), method="predict_proba")[:, 1])
                clf.fit(Xb, yb)
            except Exception:
                clf = None
                auc = None

    print(f"[valuation:{cfg.county}] trained on {len(labels)} sales: "
          f"MAE ${mae:,.0f}, R2 {r2:.2f}" + (f", excess AUC {auc:.2f}" if auc else ""))
    return {"n": len(labels), "mae": mae, "r2": r2, "auc": auc,
            "reg": reg, "clf": clf, "cat_columns": list(X.columns)}


def score_roll(cfg: CountyConfig, model: dict,
               out_path: Path | None = None) -> Path:
    """Screen the whole roll: predicted sale price + excess-potential flags
    per parcel (which properties would throw off big surpluses if sold)."""
    out_path = out_path or cfg.data_dir() / "excess_prediction.csv"
    roll = _load_roll(cfg)
    if not len(roll) or not model:
        print(f"[valuation:{cfg.county}] nothing to score")
        return out_path

    X = _features(roll)
    X = X.reindex(columns=model["cat_columns"], fill_value=0)
    pred = np.exp(model["reg"].predict(X))

    # residuals from training -> honest surplus probability on a log scale
    resid_std = model.get("resid_std")
    if resid_std is None:
        labels = _labeled_sales(cfg)
        rl = model["reg"].predict(_features(labels)
                                  .reindex(columns=model["cat_columns"], fill_value=0))
        resid_std = np.std(np.log(labels["sales_price"].values) - rl)
        model["resid_std"] = resid_std

    rows = []
    for i, row in roll.iterrows():
        apn = row["apn"]
        if not apn:
            continue
        p = pred[i]
        p_surplus_50k = float(1 - _log_norm_cdf(math.log(max(p - 50_000, 1)), resid_std))
        rows.append({
            "county": cfg.county,
            "apn": apn,
            "predicted_sale_price": f"{p:,.0f}",
            "p_excess_over_50k": f"{p_surplus_50k:.3f}",
            "total_assessed_value": row.get("TOTAL_ASSESSED_VALUE") or "",
            "situs": row.get("SITEADDRESS1") or row.get("Situs_Address") or "",
            "use": row.get("USE_PRIMARY") or "",
        })
    rows.sort(key=lambda r: float(r["predicted_sale_price"].replace(",", "")),
              reverse=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"[valuation:{cfg.county}] scored {len(rows):,} parcels -> "
          f"{out_path}")
    return out_path


def _log_norm_cdf(z: float, sigma: float) -> float:
    from math import erf, sqrt
    if sigma <= 0:
        return 1.0 if z >= 0 else 0.0
    return 0.5 * (1 + erf(z / (sigma * sqrt(2))))
