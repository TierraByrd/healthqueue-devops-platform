"""
Generate 90 days of synthetic deployment data for HealthQueue and print
the four DORA metrics.  All data is synthetic; seed is fixed for reproducibility.

Output: data/dora_deployments.csv
"""

import csv
import math
import random
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 42
DAYS = 90
# Window ends on the reporting date; back-fill 90 days.
END_DATE = datetime(2026, 10, 25, tzinfo=timezone.utc)
START_DATE = END_DATE - timedelta(days=DAYS)

# Inter-deploy mean: ~4 days (realistic for a two-engineer team with automated CI).
MEAN_INTER_DEPLOY_HOURS = 4.0 * 24

# Lead time: log-normal, median ~42 min (commit → image signed → Argo sync).
LEAD_TIME_LOG_MU = math.log(42)
LEAD_TIME_LOG_SIGMA = 0.45

# Change failure rate: ~20 % (medium DORA tier; not yet using feature flags).
INCIDENT_PROBABILITY = 0.20

# MTTR: log-normal, median ~185 min (~3 h); incidents resolved same-day.
MTTR_LOG_MU = math.log(185)
MTTR_LOG_SIGMA = 0.50


def main() -> None:
    rng = random.Random(SEED)
    rows: list[dict] = []

    current = START_DATE
    while True:
        # Poisson inter-arrival: exponential inter-deploy gaps.
        gap_hours = rng.expovariate(1.0 / MEAN_INTER_DEPLOY_HOURS)
        current += timedelta(hours=gap_hours)
        if current >= END_DATE:
            break

        lead_minutes = math.exp(rng.gauss(LEAD_TIME_LOG_MU, LEAD_TIME_LOG_SIGMA))
        commit_time = current - timedelta(minutes=lead_minutes)

        caused_incident = rng.random() < INCIDENT_PROBABILITY
        mttr_minutes = (
            math.exp(rng.gauss(MTTR_LOG_MU, MTTR_LOG_SIGMA)) if caused_incident else None
        )

        rows.append(
            {
                "deploy_timestamp": current.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "commit_timestamp": commit_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "lead_time_minutes": round(lead_minutes, 1),
                "caused_incident": str(caused_incident).lower(),
                "mttr_minutes": round(mttr_minutes, 1) if mttr_minutes is not None else "",
            }
        )

    Path("data").mkdir(exist_ok=True)
    csv_path = Path("data/dora_deployments.csv")
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "deploy_timestamp",
                "commit_timestamp",
                "lead_time_minutes",
                "caused_incident",
                "mttr_minutes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    # ── Compute the four DORA metrics ──────────────────────────────────────────

    n = len(rows)
    weeks = DAYS / 7.0

    # 1. Deployment Frequency (deploys per week)
    deploy_freq = n / weeks

    # 2. Lead Time for Changes (median, in minutes)
    lead_times = [r["lead_time_minutes"] for r in rows]
    median_lead_min = statistics.median(lead_times)
    median_lead_hr = median_lead_min / 60.0

    # 3. Change Failure Rate (%)
    incident_rows = [r for r in rows if r["caused_incident"] == "true"]
    cfr_pct = len(incident_rows) / n * 100.0

    # 4. Mean Time to Restore (median of incident MTTR, in minutes)
    mttr_vals = [r["mttr_minutes"] for r in rows if r["mttr_minutes"] != ""]
    median_mttr_min = statistics.median(mttr_vals) if mttr_vals else 0.0
    median_mttr_hr = median_mttr_min / 60.0

    print("=" * 58)
    print(f"  HealthQueue — DORA Baseline  ({DAYS}-day window)")
    print("=" * 58)
    print(f"  Deployments logged      : {n}")
    print(f"  Incidents               : {len(incident_rows)}")
    print()
    print(f"  1. Deployment Frequency : {deploy_freq:.2f} deploys/week")
    print(f"  2. Lead Time (median)   : {median_lead_min:.1f} min  ({median_lead_hr:.2f} h)")
    print(f"  3. Change Failure Rate  : {cfr_pct:.1f}%")
    print(f"  4. MTTR (median)        : {median_mttr_min:.1f} min  ({median_mttr_hr:.2f} h)")
    print("=" * 58)
    print(f"\n  CSV written to {csv_path}")


if __name__ == "__main__":
    main()
