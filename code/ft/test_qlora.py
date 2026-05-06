import os
import sys
import json
from pathlib import Path

import torch
from unsloth import FastLanguageModel
from unsloth.chat_templates import get_chat_template
from trl import SFTTrainer, SFTConfig
from datasets import Dataset

"""
train_qlora.py - QLoRA fine-tuning for honeypot SLM evaluation.
Run on RunPod A100. One model at a time, controlled by MODEL_ID env var.

Usage:
    MODEL_ID=qwen-2.5-7b python3 train_qlora.py
    MODEL_ID=llama-3.1-8b python3 train_qlora.py
    MODEL_ID=mistral-7b python3 train_qlora.py
"""

# Configuration
# ------------------------------------------------------------------

MODELS = {
    "llama-3.1-8b": {
        "base": "unsloth/Meta-Llama-3.1-8B-Instruct",
        "chat_template": "llama-3.1",
        "output_dir": "ft_llama_3.1_8b",
        "hub_id": "marmag0/llama-3.1-8b-honeypot-ft",
    },
    "qwen-2.5-7b": {
        "base": "unsloth/Qwen2.5-7B-Instruct",
        "chat_template": "qwen-2.5",
        "output_dir": "ft_qwen_2.5_7b",
        "hub_id": "marmag0/qwen-2.5-7b-honeypot-ft",
    },
    "mistral-7b": {
        "base": "unsloth/mistral-7b-instruct-v0.3",
        "chat_template": "mistral",
        "output_dir": "ft_mistral_7b",
        "hub_id": "marmag0/mistral-7b-honeypot-ft",
    },
}

MODEL_ID = os.getenv("MODEL_ID")
if MODEL_ID not in MODELS:
    print(f"[ERROR] Set MODEL_ID env var to one of: {list(MODELS.keys())}")
    sys.exit(1)

cfg = MODELS[MODEL_ID]
DATASET_PATH = "dataset_test.jsonl"
MAX_SEQ_LEN = 8192
BATCH_SIZE = 1
GRAD_ACCUM = 8
EPOCHS = 2
LR = 2e-4
RANK = 16

print(f"[*] Training {MODEL_ID}")
print(f"[INFO] Base: {cfg['base']}")
print(f"[INFO] Output: {cfg['output_dir']}")
print(f"[INFO] Hub: {cfg['hub_id']}")



# Load model + tokenizer (4-bit)
# ------------------------------------------------------------------

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=cfg["base"],
    max_seq_length=MAX_SEQ_LEN,
    dtype=None,
    load_in_4bit=True,
)

tokenizer = get_chat_template(tokenizer, chat_template=cfg["chat_template"])

model = FastLanguageModel.get_peft_model(
    model,
    r=RANK,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha=RANK * 2,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
    use_rslora=False,
)


# Load dataset
# ------------------------------------------------------------------

def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

raw = load_jsonl(DATASET_PATH)
print(f"Loaded {len(raw)} examples")


def format_example(ex):
    text = tokenizer.apply_chat_template(
        ex["messages"],
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}

dataset = Dataset.from_list(raw).map(format_example, remove_columns=["messages"])


# Training
# ------------------------------------------------------------------

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LEN,
    args=SFTConfig(
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        warmup_steps=10,
        num_train_epochs=EPOCHS,
        learning_rate=LR,
        bf16=True,
        logging_steps=5,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=42,
        output_dir=cfg["output_dir"],
        save_strategy="epoch",
        save_total_limit=1,
        report_to="none",
    ),
)

trainer.train()


# Merge LoRA into base BF16 and push to HF Hub
# ------------------------------------------------------------------

print("[*] Merging LoRA into base BF16")
model.save_pretrained_merged(
    cfg["output_dir"] + "_merged",
    tokenizer,
    save_method="merged_16bit",
)

print("[+] Local merge complete. Model saved!")
print("[INFO] Next step: run push_to_hub.py to upload to HF Hub")