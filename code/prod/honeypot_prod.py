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


# Tested models hosted on RunPod via vLLM
# ------------------------------------------------------------------

TESTED_MODELS = {
    "llama-3.1-8b": {
        "model_string": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "base_url_env": "RUNPOD_LLAMA_URL",
    },
    "qwen-2.5-7b": {
        "model_string": "Qwen/Qwen2.5-7B-Instruct",
        "base_url_env": "RUNPOD_QWEN_URL",
    },
    "mistral-7b": {
        "model_string": "mistralai/Mistral-7B-Instruct-v0.3",
        "base_url_env": "RUNPOD_MISTRAL_URL",
    },
    "llama-3.1-8b-ft": {
        "model_string": "marmag0/llama-3.1-8b-honeypot-ft",
        "base_url_env": "RUNPOD_LLAMA_FT_URL",
    },
    "qwen-2.5-7b-ft": {
        "model_string": "marmag0/qwen-2.5-7b-honeypot-ft",
        "base_url_env": "RUNPOD_QWEN_FT_URL",
    },
    "mistral-7b-ft": {
        "model_string": "marmag0/mistral-7b-honeypot-ft",
        "base_url_env": "RUNPOD_MISTRAL_FT_URL",
    },
}


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
    Captures a single turn (one full run of a test scenario) into a temporary file to ensure data safety.
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


def finalize_session(session_id: str, metadata: dict, master_path: Path):
    """
    Collapses all temporary turn logs into a single master JSONL line.
    The master file is determined by the caller (init_model) based on
    model_id and scenario, so multiple parallel batches don't collide.
    """

    tmp_path = Path(f"results/tmp_{session_id}.jsonl")
    
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
        
        master_path.parent.mkdir(parents=True, exist_ok=True)
        with open(master_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(session_record, ensure_ascii=False) + "\n")
            
        tmp_path.unlink()
    except Exception as e:
        print(f"[!] Error finalizing session {session_id}: {e}")


# Response Parsing
# ------------------------------------------------------------------


def parse_response(raw: str) -> tuple[dict | None, bool]:
    """
    Strips markdown fences if present, then attempts JSON parse.
    Returns (parsed_dict, parse_failed_bool).
    Keeping the raw string regardless lets the judge score
    Schema Adherence even on completely malformed responses.
    """

    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        return json.loads(cleaned), False
    except json.JSONDecodeError:
        return None, True


# Single LLM Turn (SystemMessage + InjectedContext + HumanMessage)
# ------------------------------------------------------------------


def run_turn(chat: ChatOpenAI, vfs: VirtualFileSystem, system_prompt: str, command: str) -> tuple[str, dict | None, dict, bool]:
    """
    Builds context from VFS state, calls LLM, parses and applies response.
    Returns (raw, parsed, vfs_rejected, parse_failed).

    Intentionally stateless from the model's perspective:
    each call is SystemMessage + single HumanMessage only.
    State continuity is handled entirely by VFS.
    """

    context = vfs.build_context(command)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=context)
    ]

    response = chat.invoke(messages)
    raw = response.content

    parsed, parse_failed = parse_response(raw)
    vfs_rejected = {"state_rejected": [], "fs_rejected": []}

    if parsed:
        vfs_rejected = vfs.apply_response(parsed)

    return raw, parsed, vfs_rejected, parse_failed


# Human In The Loop Testing
# ------------------------------------------------------------------


def human_in_the_loop(chat: ChatOpenAI, vfs: VirtualFileSystem, system_prompt: str, session_id: str):
    """Interactive mode for manual testing and system prompt development."""

    turn = 0
    print("Interactive mode on - /quit to quit | /vfs to inspect filesystem\n")

    while True:
        command = input("$ ").strip()

        if command == "/quit":
            break
        
        if command == "/vfs":
            print(json.dumps(vfs.snapshot(), indent=2))
            continue

        if not command:
            continue

        turn += 1
        raw, parsed, vfs_rejected, parse_failed = run_turn(chat, vfs, system_prompt, command)

        if parsed:
            stdout = parsed.get("stdout", "")
            stderr = parsed.get("stderr", "")
            if stdout:
                print(stdout, end="" if stdout.endswith("\n") else "\n")
            if stderr:
                print(stderr, end="" if stderr.endswith("\n") else "\n")
        else:
            print(f"[PARSE FAIL]\n{raw}")

        if vfs_rejected["state_rejected"] or vfs_rejected["fs_rejected"]:
            print(f"[VFS REJECTED] {json.dumps(vfs_rejected, indent=2)}")

        log_turn(session_id, turn, command, raw, parsed, vfs_rejected)


# Automated Testing
# ------------------------------------------------------------------


def automated_test(chat: ChatOpenAI, vfs: VirtualFileSystem, system_prompt: str, session_id: str, test_file: str):
    """
    Runs commands from a .txt file sequentially, one per line.
    Lines starting with # are treated as comments and skipped.
    Empty lines are skipped.

    Progress is printed to stdout during the run.
    """

    path = Path(test_file)
    if not path.exists():
        print(f"[ERROR] Test file not found: {test_file}")
        return

    commands = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    total = len(commands)
    print(f"Running {total} commands from {test_file}\n")
    print(f"{'Turn':<6} {'Status':<14} Command")
    print("-" * 60)

    for turn, command in enumerate(commands, start=1):
        raw, parsed, vfs_rejected, parse_failed = run_turn(chat, vfs, system_prompt, command)
        log_turn(session_id, turn, command, raw, parsed, vfs_rejected)

        if parse_failed:
            status = "PARSE FAIL"
        elif vfs_rejected["state_rejected"] or vfs_rejected["fs_rejected"]:
            n = len(vfs_rejected["state_rejected"]) + len(vfs_rejected["fs_rejected"])
            status = f"VFS REJ x{n}"
        elif parsed and parsed.get("stderr"):
            status = "stderr"
        else:
            status = "OK"

        print(f"{turn:<6} {status:<14} {command[:50]}")

    print("-" * 60)
    print(f"\nDone.\n")


# Model Initialization
# ------------------------------------------------------------------


def init_model(
    conversation_type: str = "human_in_the_loop",
    system_prompt: str = "",
    test_file: str = None,
    initial_user: str = "user",
    model_id: str = "gpt-5-nano-2025-08-07",
    temperature: float = 0.3,
):
    """
    Entry point for a single session.
    
    For batch runs (3000 sessions), wrap this in an outer loop that
    iterates over (model, state, scenario, iteration_idx).
    """

    load_dotenv()

    # backend selection: tested models go to RunPod vLLM, judges/baselines to OpenAI
    if model_id in TESTED_MODELS:
        cfg = TESTED_MODELS[model_id]
        base_url = os.getenv(cfg["base_url_env"])
        
        if not base_url:
            print(f"[ERROR] Missing env var {cfg['base_url_env']}. "
                  f"Set it to RunPod pod URL in .env")
            return
        
        chat = ChatOpenAI(
            model=cfg["model_string"],
            api_key="dummy",
            base_url=base_url.rstrip("/") + "/v1",
            temperature=temperature,
        )
        safe_model = model_id

    else:
        api_key = os.getenv("API_KEY")
        chat = ChatOpenAI(
            model=model_id,
            api_key=api_key,
            temperature=temperature,
        )
        safe_model = model_id.replace("/", "-")

    # load system prompt
    sp_path = Path(system_prompt)
    SYSTEM_PROMPT = sp_path.read_text(encoding="utf-8") if sp_path.exists() else ""
    if not SYSTEM_PROMPT:
        print("[WARN] System prompt is empty or file not found")

    # determine session_id and test_case_id
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if conversation_type == "automated_test":
        if not test_file:
            print("[ERROR] automated_test requires test_file parameter")
            return
        # test_case_id from filename: tests/01_schema_adherence.txt -> 01_schema_adherence
        test_case_id = Path(test_file).stem
        session_id = f"{safe_model}_{test_case_id}_{timestamp}"
    else:
        session_id = f"hitl_{safe_model}_{timestamp}"

    vfs = VirtualFileSystem(initial_user=initial_user)

    print(f"\nSession: {session_id}")
    print(f"Mode: {conversation_type}")
    print(f"Model: {model_id}")

    if conversation_type == "human_in_the_loop":
        human_in_the_loop(chat, vfs, SYSTEM_PROMPT, session_id)
    elif conversation_type == "automated_test":
        automated_test(chat, vfs, SYSTEM_PROMPT, session_id, test_file)
    else:
        print(f"[ERROR] Unknown conversation_type: {conversation_type}")
        return

    metadata = {
        "model_id": model_id,
        "conversation_type": conversation_type,
        "test_case_id": test_case_id if conversation_type == "automated_test" else None,
        "initial_user": initial_user,
        "temperature": temperature,
        "system_prompt_file": system_prompt,
    }

    # For HITL, group all sessions under the model dir as a single hitl file
    if conversation_type == "automated_test":
        master_path = Path("results") / safe_model / f"{safe_model}_{test_case_id}.jsonl"
    else:
        master_path = Path("results") / safe_model / f"{safe_model}_hitl.jsonl"

    finalize_session(session_id, metadata, master_path)

    print(f"Log: {master_path}\n")



# Main Function - Debug
# ------------------------------------------------------------------

if __name__ == "__main__":
    # HITL - manual testing
    init_model(
        conversation_type="human_in_the_loop",
        system_prompt="system_eval_prod.xml",
        initial_user="user",
        model_id="gpt-5-nano-2025-08-07",
        temperature=0.3,
    )

    # Automated tests
    #init_model(conversation_type="automated_test", system_prompt="system_eval_prod.xml", test_file="tests_prod/01_schema_adherence.txt", model_id="gpt-5-nano-2025-08-07")
    #init_model(conversation_type="automated_test", system_prompt="system_eval_prod.xml", test_file="tests_prod/02_persona_adoption.txt", model_id="gpt-5-nano-2025-08-07")
    #init_model(conversation_type="automated_test", system_prompt="system_eval_prod.xml", test_file="tests_prod/03_alignment_tax.txt", model_id="gpt-5-nano-2025-08-07")
    #init_model(conversation_type="automated_test", system_prompt="system_eval_prod.xml", test_file="tests_prod/04_hallucination_realism.txt", model_id="gpt-5-nano-2025-08-07")
    #init_model(conversation_type="automated_test", system_prompt="system_eval_prod.xml", test_file="tests_prod/05_fs_continuity.txt", model_id="gpt-5-nano-2025-08-07")
