import json
from pathlib import Path
from collections import defaultdict
from statistics import mean, stdev

"""
Aggregate statistics from results/judgements/.

Produces:
  - results/analysis/summary_table.md — main table for paper
  - results/analysis/per_scenario.md — model x scenario x metric breakdown
  - results/analysis/ft_delta.md — pre-FT vs post-FT comparison
  - results/analysis/score_distribution.md — % of each score per metric
  - results/analysis/raw_aggregated.csv — flat CSV for plotting in matplotlib/excel
"""

JUDGEMENTS_DIR = Path("results/judgements")
OUTPUT_DIR = Path("summary")

METRICS = [
    "persona_adoption_stability",
    "censorship_and_refusal_rates",
    "structural_formatting_reliability",
    "hallucination_realism",
]

METRIC_SHORT = {
    "persona_adoption_stability": "persona",
    "censorship_and_refusal_rates": "censor",
    "structural_formatting_reliability": "format",
    "hallucination_realism": "halluc",
}



# Loading
# ------------------------------------------------------------------


def load_all_judgements() -> list[dict]:
    """Load every judgement record from results/judgements/<model>/<scenario>.jsonl
    Returns flat list of dicts with model_id, test_case_id, metrics scores, judge_failed."""
    
    if not JUDGEMENTS_DIR.exists():
        print(f"[ERROR] Judgements dir not found: {JUDGEMENTS_DIR}")
        return []
    
    records = []
    for model_dir in sorted(JUDGEMENTS_DIR.iterdir()):
        if not model_dir.is_dir():
            continue
        model_id = model_dir.name
        for jsonl in sorted(model_dir.glob("*.jsonl")):
            scenario = jsonl.stem.replace(f"{model_id}_", "")
            with open(jsonl, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    records.append({
                        "model_id": model_id,
                        "scenario": scenario,
                        "session_id": rec.get("session_id"),
                        "judge_failed": rec.get("judge_failed", False),
                        "scores": rec.get("scores"),
                    })
    
    return records


# Aggregation Helpers
# ------------------------------------------------------------------


def aggregate_by_model(records: list[dict]) -> dict:
    """Returns {model_id: {metric: [list of scores]}} for valid (non-failed) records."""
    
    by_model = defaultdict(lambda: defaultdict(list))
    for rec in records:
        if rec["judge_failed"] or rec["scores"] is None:
            continue
        for metric in METRICS:
            score = rec["scores"].get(metric, {}).get("score")
            if score is not None:
                by_model[rec["model_id"]][metric].append(score)
    return dict(by_model)


def aggregate_by_model_scenario(records: list[dict]) -> dict:
    """Returns {(model_id, scenario): {metric: [scores]}}."""
    
    by_pair = defaultdict(lambda: defaultdict(list))
    for rec in records:
        if rec["judge_failed"] or rec["scores"] is None:
            continue
        key = (rec["model_id"], rec["scenario"])
        for metric in METRICS:
            score = rec["scores"].get(metric, {}).get("score")
            if score is not None:
                by_pair[key][metric].append(score)
    return dict(by_pair)


def count_failures(records: list[dict]) -> dict:
    """Returns {model_id: {"total": N, "failed": M}}."""
    
    counts = defaultdict(lambda: {"total": 0, "failed": 0})
    for rec in records:
        counts[rec["model_id"]]["total"] += 1
        if rec["judge_failed"]:
            counts[rec["model_id"]]["failed"] += 1
    return dict(counts)


def score_distribution(records: list[dict]) -> dict:
    """Returns {model_id: {metric: {0: count, 1: count, ..., 5: count}}}."""
    
    dist = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for rec in records:
        if rec["judge_failed"] or rec["scores"] is None:
            continue
        for metric in METRICS:
            score = rec["scores"].get(metric, {}).get("score")
            if score is not None:
                dist[rec["model_id"]][metric][score] += 1
    return dict(dist)


# Markdown Rendering
# ------------------------------------------------------------------


def render_summary_table(by_model: dict) -> str:
    """Main paper table: model x metric averages + overall."""
    
    lines = ["# Summary Table — Mean Scores per Model\n"]
    lines.append("| Model | Persona | Censor | Format | Halluc | **Overall** |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    
    for model_id in sorted(by_model.keys()):
        row = [model_id]
        all_means = []
        for metric in METRICS:
            scores = by_model[model_id][metric]
            if scores:
                m = mean(scores)
                all_means.append(m)
                row.append(f"{m:.2f}")
            else:
                row.append("—")
        if all_means:
            row.append(f"**{mean(all_means):.2f}**")
        else:
            row.append("—")
        lines.append("| " + " | ".join(row) + " |")
    
    return "\n".join(lines) + "\n"


def render_per_scenario(by_pair: dict) -> str:
    """Per scenario breakdown — separate table per metric."""
    
    lines = ["# Per-Scenario Breakdown\n"]
    
    models = sorted(set(k[0] for k in by_pair.keys()))
    scenarios = sorted(set(k[1] for k in by_pair.keys()))
    
    for metric in METRICS:
        lines.append(f"## {metric.replace('_', ' ').title()}\n")
        header = "| Model | " + " | ".join(scenarios) + " |"
        sep = "|---|" + "---:|" * len(scenarios)
        lines.append(header)
        lines.append(sep)
        
        for model_id in models:
            row = [model_id]
            for scenario in scenarios:
                scores = by_pair.get((model_id, scenario), {}).get(metric, [])
                if scores:
                    row.append(f"{mean(scores):.2f}")
                else:
                    row.append("—")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    
    return "\n".join(lines)


def render_ft_delta(by_model: dict) -> str:
    """Pre-FT vs Post-FT — pair models by base name, compute delta."""
    
    lines = ["# Fine-Tuning Effect (Δ = post-FT − pre-FT)\n"]
    lines.append("Positive values indicate improvement after fine-tuning.\n")
    lines.append("| Base Model | ΔPersona | ΔCensor | ΔFormat | ΔHalluc | **ΔOverall** |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    
    # Pair models by stripping -ft suffix
    base_models = sorted(set(
        m for m in by_model.keys()
        if not m.endswith("-ft")
    ))
    
    for base in base_models:
        ft_name = f"{base}-ft"
        if ft_name not in by_model:
            continue
        
        row = [base]
        all_deltas = []
        for metric in METRICS:
            pre = by_model[base][metric]
            post = by_model[ft_name][metric]
            if pre and post:
                delta = mean(post) - mean(pre)
                all_deltas.append(delta)
                sign = "+" if delta >= 0 else ""
                row.append(f"{sign}{delta:.2f}")
            else:
                row.append("—")
        if all_deltas:
            d = mean(all_deltas)
            sign = "+" if d >= 0 else ""
            row.append(f"**{sign}{d:.2f}**")
        else:
            row.append("—")
        lines.append("| " + " | ".join(row) + " |")
    
    return "\n".join(lines) + "\n"


def render_score_distribution(dist: dict) -> str:
    """Histogram of scores per (model, metric) — % of sessions at each score level."""
    
    lines = ["# Score Distribution\n"]
    lines.append("Percentage of sessions receiving each score level (0-5).\n")
    
    for model_id in sorted(dist.keys()):
        lines.append(f"## {model_id}\n")
        lines.append("| Metric | 0 | 1 | 2 | 3 | 4 | 5 |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        
        for metric in METRICS:
            counts = dist[model_id][metric]
            total = sum(counts.values())
            if total == 0:
                continue
            row = [METRIC_SHORT[metric]]
            for score in range(6):
                pct = 100 * counts.get(score, 0) / total
                row.append(f"{pct:.0f}%")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    
    return "\n".join(lines)


def render_failures(failures: dict) -> str:
    """Judge failure rate per model."""
    
    lines = ["# Judge Failure Rate\n"]
    lines.append("Sessions where the judge could not produce parseable scores.\n")
    lines.append("| Model | Total | Failed | Rate |")
    lines.append("|---|---:|---:|---:|")
    
    for model_id in sorted(failures.keys()):
        c = failures[model_id]
        rate = 100 * c["failed"] / c["total"] if c["total"] else 0
        lines.append(f"| {model_id} | {c['total']} | {c['failed']} | {rate:.1f}% |")
    
    return "\n".join(lines) + "\n"


# CSV export
# ------------------------------------------------------------------


def export_raw_csv(by_pair: dict, output_path: Path):
    """One row per (model, scenario, metric) with mean, std, n."""
    
    lines = ["model_id,scenario,metric,mean,std,n"]
    for (model_id, scenario), metrics_data in sorted(by_pair.items()):
        for metric in METRICS:
            scores = metrics_data.get(metric, [])
            if not scores:
                continue
            m = mean(scores)
            s = stdev(scores) if len(scores) > 1 else 0.0
            lines.append(f"{model_id},{scenario},{metric},{m:.4f},{s:.4f},{len(scores)}")
    
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# Main
# ------------------------------------------------------------------


def main():
    print(f"[*] Loading judgements from {JUDGEMENTS_DIR}")
    records = load_all_judgements()
    
    if not records:
        print("[ERROR] No records found")
        return
    
    print(f"[+] Loaded {len(records)} judgement records")
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Aggregations
    by_model = aggregate_by_model(records)
    by_pair = aggregate_by_model_scenario(records)
    failures = count_failures(records)
    dist = score_distribution(records)
    
    # Render markdown
    (OUTPUT_DIR / "summary_table.md").write_text(
        render_summary_table(by_model), encoding="utf-8"
    )
    (OUTPUT_DIR / "per_scenario.md").write_text(
        render_per_scenario(by_pair), encoding="utf-8"
    )
    (OUTPUT_DIR / "ft_delta.md").write_text(
        render_ft_delta(by_model), encoding="utf-8"
    )
    (OUTPUT_DIR / "score_distribution.md").write_text(
        render_score_distribution(dist), encoding="utf-8"
    )
    (OUTPUT_DIR / "failures.md").write_text(
        render_failures(failures), encoding="utf-8"
    )
    
    # CSV for plotting
    export_raw_csv(by_pair, OUTPUT_DIR / "raw_aggregated.csv")
    
    print(f"[+] Reports written to {OUTPUT_DIR}/")
    print(f"    - summary_table.md       (main paper table)")
    print(f"    - per_scenario.md        (model x scenario breakdown)")
    print(f"    - ft_delta.md            (pre-FT vs post-FT)")
    print(f"    - score_distribution.md  (% per score level)")
    print(f"    - failures.md            (judge failure rate)")
    print(f"    - raw_aggregated.csv     (flat CSV for plots)")


if __name__ == "__main__":
    main()