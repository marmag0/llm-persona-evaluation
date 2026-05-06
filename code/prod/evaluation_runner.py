import sys
import time
from pathlib import Path
from datetime import datetime
import os

from honeypot_prod import init_model

"""
Batch orchestrator for honeypot SLM evaluation.
Sweeps (models x scenarios x iterations), one session per combination.

Resume-safe: if a master jsonl already has N lines, runner skips
iterations 1..N for that (model, scenario) pair and continues.
"""



# Resume Helper
# ------------------------------------------------------------------

def count_completed_iterations(model_id: str, scenario: str) -> int:
    """Counts existing lines in master jsonl. Each line == one completed session."""
    safe_model = model_id.replace("/", "-")
    master_path = Path("results") / safe_model / f"{safe_model}_{scenario}.jsonl"
    if not master_path.exists():
        return 0
    with open(master_path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)


# Config Validation
# ------------------------------------------------------------------

def validate_config(scenarios: list[str], tests_dir: str, system_prompt: str):
    """Fail fast if test files or system prompt are missing."""
    errors = []
    for scenario in scenarios:
        path = Path(tests_dir) / f"{scenario}.txt"
        if not path.exists():
            errors.append(f"Missing test file: {path}")
    if not Path(system_prompt).exists():
        errors.append(f"Missing system prompt: {system_prompt}")
    if errors:
        for e in errors:
            print(f"[ERROR] {e}")
        sys.exit(1)


# Main Sweep
# ------------------------------------------------------------------

def main(ips: int, temp: float = 0.3):
    iterations_per_scenario = ips

    scenarios = [
        "01_schema_adherence",
        "02_persona_adoption",
        "03_alignment_tax",
        "04_hallucination_realism",
        "05_fs_continuity",
    ]

    # MODEL_OVERRIDE=qwen-2.5-7b-ft python3 evaluation_runner.py
    model_override = os.getenv("MODEL_OVERRIDE")
    if model_override:
        models = [model_override]
        print(f"[INFO] MODEL_OVERRIDE set, sweeping only: {model_override}\n")
    else:
        models = [
            "qwen-2.5-7b",
            "llama-3.1-8b",
            "mistral-7b",
            "qwen-2.5-7b-ft",
            "llama-3.1-8b-ft",
            "mistral-7b-ft",
        ]

    system_prompt = "system_eval_prod.xml"
    tests_dir = "tests_prod"
    temperature = temp

    # Validate before starting any work
    validate_config(scenarios, tests_dir, system_prompt)

    # Print sweep summary
    total_combinations = len(models) * len(scenarios)
    total_sessions = total_combinations * iterations_per_scenario

    print(f"Sweep config:")
    print(f"  Models:     {len(models)}")
    print(f"  Scenarios:  {len(scenarios)}")
    print(f"  Iterations: {iterations_per_scenario} per (model, scenario)")
    print(f"  Total sessions: {total_sessions}")
    print(f"  Started at: {datetime.now().isoformat()}\n")

    # Sweep loop
    combo_idx = 0
    for model_id in models:
        for scenario in scenarios:
            combo_idx += 1
            test_file = f"{tests_dir}/{scenario}.txt"

            already_done = count_completed_iterations(model_id, scenario)
            remaining = iterations_per_scenario - already_done

            print(f"[{combo_idx}/{total_combinations}] {model_id}  |  {scenario}")
            if already_done > 0:
                print(f"  Resuming: {already_done} done, {remaining} remaining")

            if remaining <= 0:
                print(f"  Already complete, skipping.\n")
                continue

            for i in range(already_done + 1, iterations_per_scenario + 1):
                print(f"  Iter {i}/{iterations_per_scenario}", end="  ", flush=True)
                start = datetime.now()
                try:
                    init_model(
                        conversation_type="automated_test",
                        system_prompt=system_prompt,
                        test_file=test_file,
                        model_id=model_id,
                        temperature=temperature
                    )
                    elapsed = (datetime.now() - start).total_seconds()
                    print(f"OK ({elapsed:.1f}s)")
                except KeyboardInterrupt:
                    print("\n[!] Interrupted by user. Resume by re-running.\n")
                    sys.exit(0)
                except Exception as e:
                    print(f"FAIL ({type(e).__name__}: {e})")
            print()

    print(f"\nSweep complete at {datetime.now().isoformat()}")



# Entry Point
# ------------------------------------------------------------------

if __name__ == "__main__":
    main(ips=100, temp=0.3)   # ips = number of iterations per scenario | temp = model temperature