"""
push_to_hub.py — Upload locally merged model to HF Hub via hf CLI.

Robust against flaky network: hf upload-large-folder retries shards
individually and resumes from last successful upload.

Usage:
    MODEL_ID=qwen-2.5-7b python3 push_to_hub.py
"""
import os
import sys
import subprocess
from pathlib import Path

# same MODELS dict as train_qlora.py
MODELS = {
    "llama-3.1-8b": {
        "output_dir": "ft_llama_3.1_8b",
        "hub_id": "marmag0/llama-3.1-8b-honeypot-ft",
    },
    "qwen-2.5-7b": {
        "output_dir": "ft_qwen_2.5_7b",
        "hub_id": "marmag0/qwen-2.5-7b-honeypot-ft",
    },
    "mistral-7b": {
        "output_dir": "ft_mistral_7b",
        "hub_id": "marmag0/mistral-7b-honeypot-ft",
    },
}

MODEL_ID = os.getenv("MODEL_ID")
if MODEL_ID not in MODELS:
    print(f"[ERROR] Set MODEL_ID env var to one of: {list(MODELS.keys())}")
    sys.exit(1)

cfg = MODELS[MODEL_ID]
local_dir = Path(cfg["output_dir"] + "_merged")

if not local_dir.exists():
    print(f"[ERROR] Local merged directory not found: {local_dir}")
    print(f"        Run train_qlora.py first.")
    sys.exit(1)

print(f"[*] Pushing {local_dir} to HF Hub: {cfg['hub_id']}")
print(f"[INFO] Using hf upload-large-folder for resumable upload")

# create repo if not exists (idempotent)
subprocess.run([
    "hf", "repo", "create",
    cfg["hub_id"],
    "--type", "model",
    "--private",
], check=False)  # ignore error if exists

# upload with resumable retry
result = subprocess.run([
    "hf", "upload-large-folder",
    cfg["hub_id"],
    str(local_dir),
    "--repo-type", "model",
], check=False)

if result.returncode == 0:
    print(f"[+] Done. Model at: https://huggingface.co/{cfg['hub_id']}")
else:
    print(f"\n[ERROR] Upload failed with code {result.returncode}")
    print(f"[INFO] Re-run this script — it will resume from last successful shard.")
    sys.exit(1)