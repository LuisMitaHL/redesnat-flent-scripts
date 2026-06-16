#!/usr/bin/env python3
import sys
import re
import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.formula.api import ols
from statsmodels.stats.anova import anova_lm

warnings.filterwarnings("ignore", category=FutureWarning)

CONNECTION_ORDER = ["1d-1u", "50d-50u", "100d-100u", "150d-150u"]

FILENAME_RE = re.compile(
    r"\.(?P<firmware>cudystock|owrtredesnat)"
    r"-(?P<band>24g|5g)"
    r"-(?P<connections>\d+d-\d+u)"
    r"-\d+dbm"
    r"-(?P<run>run\d+)"
    r"\.csv$"
)

PING_COLUMNS = {
    "icmp": "Ping (ms) ICMP",
    "udp": "Ping (ms) UDP BE",
}


def parse_filename(path: Path):
    m = FILENAME_RE.search(path.name)
    if not m:
        return None
    return {
        "firmware": m.group("firmware"),
        "band": m.group("band"),
        "connections": m.group("connections"),
        "run": int(m.group("run")[3:]),
        "path": path,
    }


def extract_loss_rates(csv_path: Path):
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"  WARNING: could not read {csv_path.name}: {e}", file=sys.stderr)
        return None

    tcp_col = None
    for c in df.columns:
        if c.strip() == "TCP totals":
            tcp_col = c
            break

    if tcp_col is None:
        print(f"  WARNING: 'TCP totals' column not found in {csv_path.name}", file=sys.stderr)
        return None

    under_load = df[df[tcp_col].notna() & (df[tcp_col] != "")]
    if len(under_load) == 0:
        print(f"  WARNING: no TCP load data in {csv_path.name}", file=sys.stderr)
        return None

    total = len(under_load)

    result = {"n_samples": total}

    for key, col_name in PING_COLUMNS.items():
        if col_name not in df.columns:
            print(f"  WARNING: '{col_name}' column not found in {csv_path.name}", file=sys.stderr)
            return None

        col_data = under_load[col_name]
        nan_count = int(col_data.isna().sum())
        loss_rate = nan_count / total if total > 0 else 0.0
        result[f"loss_rate_{key}"] = loss_rate

    return result


def collect_data(csv_dir: str, band: str):
    p = Path(csv_dir)
    if not p.is_dir():
        print(f"Error: {csv_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    rows = []
    for csv_path in sorted(p.glob("*.csv")):
        info = parse_filename(csv_path)
        if info is None:
            continue
        if info["band"] != band:
            continue

        stats_result = extract_loss_rates(csv_path)
        if stats_result is None:
            continue

        rows.append({
            "firmware": info["firmware"],
            "connections": info["connections"],
            "run": info["run"],
            "loss_rate_icmp": stats_result["loss_rate_icmp"],
            "loss_rate_udp": stats_result["loss_rate_udp"],
            "n_samples": stats_result["n_samples"],
        })

    if not rows:
        print(f"Error: no data found for band '{band}'", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(rows)
    df["connections"] = pd.Categorical(
        df["connections"], categories=CONNECTION_ORDER, ordered=True
    )
    return df


def run_anova(data, metric_col):
    formula = f"{metric_col} ~ C(firmware) + C(connections) + C(firmware):C(connections)"
    model = ols(formula, data=data).fit()
    table = anova_lm(model, typ=2)
    return model, table


def print_markdown(data, band):
    print(f"# Two-Way ANOVA: Packet Loss Under TCP Load ({band.upper()} Band)\n")

    print("## Data Summary\n")
    print(f"- **Band:** `{band}`")
    print(f"- **Firmwares:** {', '.join(f'`{f}`' for f in sorted(data['firmware'].unique()))}")
    print(f"- **Connection levels:** {', '.join(f'`{c}`' for c in CONNECTION_ORDER)}")
    print(f"- **Runs per combination:** {data['run'].nunique()}")
    print(f"- **Total observations:** {len(data)}\n")

    print("### Methodology\n")
    print("Packet loss is measured on two independent ping streams that run concurrently with TCP load:")
    print("- **ICMP ping:** Standard ICMP echo requests.")
    print("- **UDP BE ping:** UDP Best Effort ping (DSCP 0), sharing the bottleneck queue with TCP flows.\n")
    print("The loss rate for each CSV file is calculated as:\n")
    print("```")
    print("loss_rate = count(NaN rows in ping column under TCP load) / total_rows_under_TCP_load")
    print("```\n")
    print("The TCP load window is identified using the `TCP totals` column: only rows where TCP")
    print("traffic is active are included, since TCP flows start ~5 s after the test begins and")
    print("finish ~5 s before the test ends, while pings run continuously throughout.\n")

    ping_configs = [
        ("loss_rate_icmp", "ICMP", "ICMP Ping Loss Rate"),
        ("loss_rate_udp", "UDP BE", "UDP BE Ping Loss Rate"),
    ]

    print("## Descriptive Statistics\n")

    for metric_col, short_label, long_label in ping_configs:
        print(f"### {long_label}\n")

        summary = data.groupby(["firmware", "connections"], observed=False)[metric_col].agg(
            ["mean", "std", "min", "max"]
        ).round(3)
        print(summary.to_markdown())
        print()

    print("## ANOVA Results\n")

    for metric_col, short_label, long_label in ping_configs:
        print(f"### Metric: {long_label} (`{short_label}`)\n")
        print(f"**Model:** `{metric_col} ~ C(firmware) + C(connections) + C(firmware):C(connections)`\n")

        model, table = run_anova(data, metric_col)

        formatted = table.round(5)
        print(formatted.to_markdown())
        print()

        for effect, row_label in [
            ("C(firmware)", "Firmware"),
            ("C(connections)", "Connections"),
            ("C(firmware):C(connections)", "Firmware × Connections"),
        ]:
            p_val = formatted.loc[effect, "PR(>F)"]
            sig = "SIGNIFICANT" if p_val < 0.05 else "NOT significant"
            print(f"- **{row_label}:** {sig} (p = {p_val:.5e})")

        print(f"\n**Residual standard error:** {np.sqrt(model.mse_resid):.6f}")
        print(f"**R-squared:** {model.rsquared:.4f}")
        print(f"**Adj R-squared:** {model.rsquared_adj:.4f}\n")

        print("#### Model Coefficients\n")
        coef_df = pd.DataFrame({
            "coefficient": model.params,
            "std_error": model.bse,
            "t_value": model.tvalues,
            "p_value": model.pvalues,
        }).round(5)
        print(coef_df.to_markdown())
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Two-way ANOVA on flent RRUL packet loss (ICMP and UDP BE pings)"
    )
    parser.add_argument(
        "--band", required=True, choices=["24g", "5g"],
        help="Frequency band to analyze (24g or 5g)"
    )
    parser.add_argument(
        "--csv-dir", default=".",
        help="Directory containing flent CSV files (default: current dir)"
    )
    args = parser.parse_args()

    data = collect_data(args.csv_dir, args.band)
    print_markdown(data, args.band)


if __name__ == "__main__":
    main()
