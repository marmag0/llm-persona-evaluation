import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from vfs import VirtualFileSystem


# Logging
# ------------------------------------------------------------------


def setup_logger(session_id: str) -> logging.Logger:
    Path("results").mkdir(exist_ok=True)
    logger = logging.getLogger(session_id)
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(f"results/{session_id}.jsonl", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    return logger


def log_turn(logger: logging.Logger, turn: int, command: str, raw: str, parsed: dict | None, rejected: list[dict], parse_failed: bool):
    """
    One JSONL entry per turn. Structure is flat and explicit so the
    judge script can load each line independently without context.

    Fields:
      turn          - sequential turn number within session
      command       - raw user input sent to model
      raw           - exact model response string before any parsing
      parsed        - parsed JSON dict or null if parsing failed
      rejected      - list of fs_changes rejected by VFS validation
      parse_failed  - true if raw could not be parsed as JSON at all
      timestamp     - ISO timestamp for ordering across sessions
    """

    entry = {
        "turn": turn,
        "timestamp": datetime.now().isoformat(),
        "command": command,
        "raw": raw,
        "parsed": parsed,
        "rejected": rejected,
        "parse_failed": parse_failed
    }
    logger.info(json.dumps(entry, ensure_ascii=False))


# Response parsing
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


# Single LLM turn (SystemMessage + context + HumanMessage)
# ------------------------------------------------------------------


def run_turn(chat: ChatOpenAI, vfs: VirtualFileSystem, system_prompt: str, command: str) -> tuple[str, dict | None, list[dict], bool]:
    """
    Builds context from VFS state, calls LLM, parses and applies response.
    Returns (raw, parsed, rejected, parse_failed).

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
    rejected = []

    if parsed:
        rejected = vfs.apply_response(parsed)

    return raw, parsed, rejected, parse_failed


# Modes
# ------------------------------------------------------------------


def human_in_the_loop(chat: ChatOpenAI, vfs: VirtualFileSystem, system_prompt: str, logger: logging.Logger):
    """Interactive mode for manual testing and system prompt development"""

    turn = 0
    print("Interactive mode  -  /exit to quit, /vfs to inspect filesystem\n")

    while True:
        command = input("$ ").strip()

        if command == "/exit":
            break

        if command == "/vfs":
            print(json.dumps(vfs.snapshot(), indent=2))
            continue

        if not command:
            continue

        turn += 1
        raw, parsed, rejected, parse_failed = run_turn(chat, vfs, system_prompt, command)

        if parsed:
            if parsed.get("stdout"):
                print(parsed["stdout"], end="")
            if parsed.get("stderr"):
                print(parsed["stderr"], end="")
        else:
            print(f"[PARSE FAIL]\n{raw}")

        if rejected:
            print(f"[VFS REJECTED] {json.dumps(rejected, indent=2)}")

        if parsed["stdout"] != "" and parsed["stderr"] != "":
            print()
        log_turn(logger, turn, command, raw, parsed, rejected, parse_failed)


def automated_test(chat: ChatOpenAI, vfs: VirtualFileSystem, system_prompt: str, logger: logging.Logger, test_file: str):
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
        raw, parsed, rejected, parse_failed = run_turn(chat, vfs, system_prompt, command)
        log_turn(logger, turn, command, raw, parsed, rejected, parse_failed)

        if parse_failed:
            status = "PARSE FAIL"
        elif rejected:
            status = f"VFS REJ x{len(rejected)}"
        elif parsed and parsed.get("stderr"):
            status = "stderr"
        else:
            status = "OK"

        print(f"{turn:<6} {status:<14} {command[:50]}")

    print("-" * 60)
    print(f"\nDone. Results written to results/\n")


# Entry point
# ------------------------------------------------------------------


def init_model(conversation_type: str = "human_in_the_loop", system_prompt: str = "", test_file: str = None, initial_user: str = "user"):

    # Load API key
    api_key = os.getenv("API_KEY")
    if not api_key:
        load_dotenv()
        api_key = os.getenv("API_KEY")

    # Init chat with model
    chat = ChatOpenAI(
        model="gpt-5-nano-2025-08-07",
        api_key=api_key,
        temperature=0.3
    )

    # Load system prompt
    sp_path = Path(system_prompt)
    SYSTEM_PROMPT = sp_path.read_text(encoding="utf-8") if sp_path.exists() else ""
    if not SYSTEM_PROMPT:
        print("[WARN] System prompt is empty or file not found")

    # Session ID encodes mode + model + timestamp for easy log identification
    session_id = (
        f"{conversation_type}"
        f"_{chat.model_name.replace('/', '-')}"
        f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    vfs    = VirtualFileSystem(initial_user=initial_user)
    logger = setup_logger(session_id)

    print(f"\nSession : {session_id}")
    print(f"Mode    : {conversation_type}")
    print(f"Model   : {chat.model_name}")
    print(f"Log     : results/{session_id}.jsonl\n")

    if conversation_type == "human_in_the_loop":
        human_in_the_loop(chat, vfs, SYSTEM_PROMPT, logger)

    elif conversation_type == "automated_test":
        if not test_file:
            print("[ERROR] automated_test requires test_file parameter")
            return
        automated_test(chat, vfs, SYSTEM_PROMPT, logger, test_file)

    else:
        print(f"[ERROR] Unknown conversation_type: {conversation_type}")


# ------------------------------------------------------------------


if __name__ == "__main__":
    #init_model(conversation_type="human_in_the_loop", system_prompt="../../system_eval.xml", initial_user="user")
    init_model(conversation_type="automated_test", system_prompt="../../system_eval.xml", test_file="tests/01_schema_adherence.txt", initial_user="user")
    init_model(conversation_type="automated_test", system_prompt="../../system_eval.xml", test_file="tests/02_persona_adoption.txt", initial_user="user")
    init_model(conversation_type="automated_test", system_prompt="../../system_eval.xml", test_file="tests/03_alignment_tax.txt", initial_user="user")
    init_model(conversation_type="automated_test", system_prompt="../../system_eval.xml", test_file="tests/04_hallucination_realism.txt", initial_user="user")