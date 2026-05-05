import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from vfs_prod import VirtualFileSystem


# Logging Handlers
# ------------------------------------------------------------------


def setup_automated_logger(tested_model_name: str, test_case_id: str) -> logging.Logger:
    """Sets up logger for automated tests only
    - tested_model_name: tested model name
    - test_case_id: number based on test scenario ID"""

    Path("results").mkdir(exist_ok=True)
    Path(f"results/{tested_model_name}").mkdir(exist_ok=True)

    logger = logging.getLogger(f"{tested_model_name}_{test_case_id}")
    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(f"results/{tested_model_name}/test_case_{test_case_id}.jsonl", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    
    return logger


def setup_hitl_logger(tested_model_name: str, session_id: str) -> logging.Logger:
    """Sets up logger for human-in-the-loop tests only
    - tested_model_name: tested model name
    - session_id: time-based ID for HITL session"""
    
    Path("results").mkdir(exist_ok=True)
    Path(f"results/{tested_model_name}").mkdir(exist_ok=True)

    logger = logging.getLogger(f"{tested_model_name}_{session_id}")
    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(f"results/{tested_model_name}/session_{session_id}.jsonl", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    
    return logger


# Universal Multi-Turn Logging Tools
# ------------------------------------------------------------------


def log_turn(session_id: str, turn_idx: int, command: str, raw_response: str, parsed: dict | None, rejected: list):
    """
    Captures a single turn (one full run of test scenario) into a temporary file to ensure data safety.
    This is a universal helper to build session history turn-by-turn.
    """
    tmp_path = Path(f"results/tmp_{session_id}.jsonl")
    tmp_path.parent.mkdir(exist_ok=True)

    entry = {
        "turn": turn_idx,
        "timestamp": datetime.now().isoformat(),
        "input": command,
        "output_raw": raw_response,
        "output_parsed": parsed,
        "vfs_rejected": rejected
    }

    with open(tmp_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def finalize_session(session_id: str, metadata: dict):
    """
    Collapses all temporary turn logs into a single master JSONL line.
    Enables efficient LLM-as-a-judge evaluation of the entire scenario.
    """

    tmp_path = Path(f"results/tmp_{session_id}.jsonl")
    master_path = Path("results/master_results.jsonl")
    
    if not tmp_path.exists():
        return

    try:
        lines = tmp_path.read_text(encoding="utf-8").splitlines()
        history = [json.loads(line) for line in lines]
        
        session_record = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            **metadata,
            "history": history
        }
        
        with open(master_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(session_record, ensure_ascii=False) + "\n")
            
        tmp_path.unlink()
    except Exception as e:
        print(f"Error finalizing session {session_id}: {e}")


# Response parsing
# ------------------------------------------------------------------


pass


# Response parsing
# ------------------------------------------------------------------
