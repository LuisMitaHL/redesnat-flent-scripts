#!/usr/bin/env python3
import sys
import re
import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

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


def classify_test(csv_path: Path, stall_gap: int):
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

    upload_cols = [c for c in df.columns if c.strip().startswith("TCP upload BE::")]
    download_cols = [c for c in df.columns if c.strip().startswith("TCP download BE::")]
    all_be_cols = upload_cols + download_cols
    total_conn = len(all_be_cols)

    if total_conn == 0:
        print(f"  WARNING: no TCP BE columns in {csv_path.name}", file=sys.stderr)
        return None

    stalled = 0
    never_transmitted = 0

    for c in all_be_cols:
        s = under_load[c]
        has_data = pd.to_numeric(s, errors="coerce").notna()

        if not has_data.any():
            never_transmitted += 1
            continue

        first_idx = has_data[has_data].index[0]
        after_start = has_data.loc[first_idx:]

        groups = (after_start != after_start.shift()).cumsum()
        run_lengths = after_start.groupby(groups, sort=False).transform("size")
        empty_run_lengths = run_lengths[~after_start]

        if len(empty_run_lengths) > 0 and (empty_run_lengths >= stall_gap).any():
            stalled += 1

    stalled_pct = stalled / total_conn

    return {
        "passed": True,
        "stalled_pct": stalled_pct,
        "stalled_connections": stalled,
        "never_transmitted": never_transmitted,
        "total_connections": total_conn,
    }


def collect_data(csv_dir: str, band: str, stall_gap: int, stall_threshold: float):
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

        result = classify_test(csv_path, stall_gap)
        if result is None:
            continue

        result["passed"] = result["stalled_pct"] < stall_threshold

        rows.append({
            "firmware": info["firmware"],
            "connections": info["connections"],
            "run": info["run"],
            "passed": result["passed"],
            "stalled_pct": result["stalled_pct"],
            "stalled_connections": result["stalled_connections"],
            "never_transmitted": result["never_transmitted"],
            "total_connections": result["total_connections"],
        })

    if not rows:
        print(f"Error: no data found for band '{band}'", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(rows)
    df["connections"] = pd.Categorical(
        df["connections"], categories=CONNECTION_ORDER, ordered=True
    )
    return df


def print_markdown(data, band, stall_gap, stall_threshold):
    print(f"# Chi-Square Test: TCP Connection Success/Failure ({band.upper()} Band)\n")

    print("## Data Summary\n")
    print(f"- **Band:** `{band}`")
    firmwares = sorted(data["firmware"].unique())
    print(f"- **Firmwares:** {', '.join(f'`{f}`' for f in firmwares)}")
    print(f"- **Connection levels:** {', '.join(f'`{c}`' for c in CONNECTION_ORDER)}")
    print(f"- **Runs per combination:** {data['run'].nunique()}")
    print(f"- **Stall criterion:** ≥ {stall_gap} consecutive empty samples after first transmission")
    print(f"- **Failure criterion:** ≥ {stall_threshold*100:.0f}% of TCP connections stalled")
    print(f"- **Total observations:** {len(data)}\n")

    print("## Per-Firmware Summary\n")

    for fw in firmwares:
        fw_data = data[data["firmware"] == fw]
        n_pass = fw_data["passed"].sum()
        n_fail = (~fw_data["passed"]).sum()
        print(f"### Firmware: `{fw}`\n")
        print(f"- **Passed:** {n_pass} / {len(fw_data)}")
        print(f"- **Failed:** {n_fail} / {len(fw_data)}\n")

        summary_rows = []
        for conn in CONNECTION_ORDER:
            sub = fw_data[fw_data["connections"] == conn]
            if len(sub) > 0:
                n_pass_conn = sub["passed"].sum()
                n_total_conn = len(sub)
                avg_stalled = sub["stalled_pct"].mean() * 100
                summary_rows.append({
                    "connections": conn,
                    "passed": f"{n_pass_conn}/{n_total_conn}",
                    "avg_stalled_pct": f"{avg_stalled:.2f}%",
                })
        if summary_rows:
            summary_df = pd.DataFrame(summary_rows)
            print(summary_df.to_markdown(index=False))
            print()

    print("## Contingency Table (Firmware × Result)\n")

    ct = pd.crosstab(data["firmware"], data["passed"])
    contingency = pd.DataFrame(index=ct.index)
    contingency["Pass"] = ct.get(True, 0)
    contingency["Fail"] = ct.get(False, 0)
    contingency.index.name = "Firmware"
    print(contingency.to_markdown())
    print()

    print("## Chi-Square Test of Independence\n")

    if contingency["Fail"].sum() == 0:
        print("All tests passed. No variation in outcome — chi-square cannot be computed.\n")
    elif contingency["Fail"].sum() == len(data):
        print("All tests failed. No variation in outcome — chi-square cannot be computed.\n")
    else:
        chi2, p_value, dof, expected = stats.chi2_contingency(contingency)
        print(f"- **Null hypothesis:** Firmware and test outcome (pass/fail) are independent")
        print(f"- **Chi-square statistic:** {chi2:.4f}")
        print(f"- **Degrees of freedom:** {dof}")
        print(f"- **p-value:** {p_value:.5e}")
        sig = "SIGNIFICANT" if p_value < 0.05 else "NOT significant"
        print(f"- **Result:** {sig} (α = 0.05)\n")

        print("### Expected Frequencies\n")
        expected_df = pd.DataFrame(
            expected,
            index=contingency.index,
            columns=["Pass (exp)", "Fail (exp)"]
        )
        print(expected_df.round(2).to_markdown())
        print()

        if (expected < 5).any():
            print("**Note:** Some expected frequencies are < 5. Computing Fisher's exact test.\n")
            if contingency.shape == (2, 2):
                odds_ratio, fisher_p = stats.fisher_exact(contingency)
                print(f"- **Fisher's exact p-value:** {fisher_p:.5e}")
                sig_f = "SIGNIFICANT" if fisher_p < 0.05 else "NOT significant"
                print(f"- **Fisher's result:** {sig_f}\n")

    print("## Analysis by Connection Level\n")

    for conn in CONNECTION_ORDER:
        sub = data[data["connections"] == conn]
        if len(sub) == 0:
            continue

        print(f"### Connection Level: `{conn}`\n")

        raw = pd.crosstab(sub["firmware"], sub["passed"])
        sub_cont = pd.DataFrame(index=raw.index)
        sub_cont["Pass"] = raw.get(True, 0)
        sub_cont["Fail"] = raw.get(False, 0)
        sub_cont.index.name = "Firmware"

        print(sub_cont.to_markdown())
        print()

        if sub_cont["Fail"].sum() == 0:
            print("All tests passed. No statistical test applicable.\n")
        elif sub_cont["Fail"].sum() == len(sub):
            print("All tests failed. No statistical test applicable.\n")
        else:
            try:
                chi2_c, p_c, dof_c, exp_c = stats.chi2_contingency(sub_cont)
                sig_c = "SIGNIFICANT" if p_c < 0.05 else "NOT significant"
                print(f"- **Chi-square:** {chi2_c:.4f}, **df:** {dof_c}, **p:** {p_c:.5e}")
                print(f"- **Result:** {sig_c}\n")
            except Exception as e:
                print(f"- Could not compute chi-square: {e}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Chi-square test of independence on flent RRUL TCP connection stall rates"
    )
    parser.add_argument(
        "--band", required=True, choices=["24g", "5g"],
        help="Frequency band to analyze (24g or 5g)"
    )
    parser.add_argument(
        "--csv-dir", default=".",
        help="Directory containing flent CSV files (default: current dir)"
    )
    parser.add_argument(
        "--stall-gap", type=int, default=15,
        help="Consecutive empty samples to consider a connection stalled (default: 15)"
    )
    parser.add_argument(
        "--stall-threshold", type=float, default=0.05,
        help="Fraction of connections that must be stalled to fail the test (default: 0.05 = 5%%)"
    )
    args = parser.parse_args()

    data = collect_data(args.csv_dir, args.band, args.stall_gap, args.stall_threshold)
    print_markdown(data, args.band, args.stall_gap, args.stall_threshold)


if __name__ == "__main__":
    main()
