import os
import json
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

"""
LLM-as-a-judge for honeypot SLM evaluation.
Iterates over each session in master jsonl files (results/<model>/<scenario>.jsonl)
and produces per-session scores on 4 metrics, written to results/judgements/<model>/<scenario>.jsonl.

Resume-safe: counts existing judgement lines per file, continues from there.
"""

# Configuration
# ------------------------------------------------------------------

JUDGE_MODEL = "gpt-5-nano-2025-08-07"
JUDGE_TEMPERATURE = 0
RESULTS_DIR = Path("results")
JUDGEMENTS_DIR = RESULTS_DIR / "judgements"
JUDGE_SYSTEM_PROMPT = "system_judge_prod.xml"



# Loading System Prompt
# ------------------------------------------------------------------


def load_judge_system_prompt() -> str:
    """Load judge system prompt from file. Path stored in JUDGE_SYSTEM_PROMPT."""

    path = Path(JUDGE_SYSTEM_PROMPT)
    
    if not path.exists():
        print(f"[ERROR] Judge system prompt file not found: {path}")
        sys.exit(1)
    
    return path.read_text(encoding="utf-8")


# JSON Schema for Strict Mode (gpt-5-nano Structured Outputs)
# ------------------------------------------------------------------


def _metric_schema():
    """Schema fragment for a single metric (reasoning + score)."""

    return {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": "Concise justification, max 100 words"
            },
            "score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 5
            }
        },
        "required": ["reasoning", "score"],
        "additionalProperties": False
    }


OUTPUT_SCHEMA = {
    "name": "session_evaluation",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "persona_adoption_stability": _metric_schema(),
            "censorship_and_refusal_rates": _metric_schema(),
            "structural_formatting_reliability": _metric_schema(),
            "hallucination_realism": _metric_schema()
        },
        "required": [
            "persona_adoption_stability",
            "censorship_and_refusal_rates",
            "structural_formatting_reliability",
            "hallucination_realism"
        ],
        "additionalProperties": False
    }
}


# Session Loading and Prompt Building
# ------------------------------------------------------------------


def build_judge_input(session: dict) -> str:
    """Format a session record as input for the judge.
    
    The session dict comes from master jsonl: contains session_id, model_id,
    metadata, and history (list of turn dicts).
    """
    
    history = session.get("history", [])
    lines = [f"<session_meta>"]
    lines.append(f"  total_turns: {len(history)}")
    lines.append(f"</session_meta>")
    lines.append("")
    lines.append("<turns>")
    
    for turn in history:
        idx = turn.get("turn", "?")
        cmd = turn.get("input", "")
        raw = turn.get("output_raw", "")
        parsed = turn.get("output_parsed")
        rejected = turn.get("vfs_rejected", {})
        
        lines.append(f"  <turn n=\"{idx}\">")
        lines.append(f"    <user_command>{cmd}</user_command>")
        lines.append(f"    <model_raw_output>{raw}</model_raw_output>")
        if parsed is not None:
            lines.append(f"    <parsed_status>OK</parsed_status>")
        else:
            lines.append(f"    <parsed_status>PARSE_FAILED</parsed_status>")
        if rejected and (rejected.get("state_rejected") or rejected.get("fs_rejected")):
            lines.append(f"    <vfs_rejected>{json.dumps(rejected)}</vfs_rejected>")
        lines.append(f"  </turn>")
    
    lines.append("</turns>")
    return "\n".join(lines)


# Judge Call
# ------------------------------------------------------------------


def call_judge(chat: ChatOpenAI, system_prompt: str, judge_input: str, retry: bool = True) -> tuple[dict | None, str]:
    """
    Call the judge with the formatted session input.
    Returns (parsed_scores_dict_or_None, raw_response_str).
    
    On parse failure or API error, retries once with bumped temperature.
    """

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=judge_input)
    ]
    
    # first attempt
    parsed, raw = _single_judge_call(chat, messages)
    if parsed is not None:
        return parsed, raw
    
    if not retry:
        return None, raw
    
    # retry with bumped temperature to avoid deterministic re-failure
    print(" [retry]", end="", flush=True)
    retry_chat = ChatOpenAI(
        model=chat.model_name,
        api_key=chat.openai_api_key.get_secret_value() if hasattr(chat.openai_api_key, 'get_secret_value') else chat.openai_api_key,
        temperature=0.3,
        model_kwargs={
            "response_format": {"type": "json_schema", "json_schema": OUTPUT_SCHEMA}
        },
    )

    parsed_retry, raw_retry = _single_judge_call(retry_chat, messages)
    if parsed_retry is not None:
        return parsed_retry, raw_retry
    
    # still failed - return last raw for logging
    return None, raw_retry


def _single_judge_call(chat: ChatOpenAI, messages: list) -> tuple[dict | None, str]:
    """One API call attempt. Returns (parsed_or_None, raw_str)."""

    try:
        response = chat.invoke(messages)
        raw = response.content
    except Exception as e:
        return None, f"[API ERROR] {type(e).__name__}: {e}"
    
    try:
        parsed = json.loads(raw)
        return parsed, raw
    except json.JSONDecodeError:
        return None, raw


# Per-file Judging
# ------------------------------------------------------------------


def count_existing_judgements(judgement_path: Path) -> int:
    """Number of session judgements already written. Used for resume."""

    if not judgement_path.exists():
        return 0
    with open(judgement_path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)


def judge_file(master_path: Path, judgement_path: Path, chat: ChatOpenAI):
    """
    Iterate over all sessions in a master jsonl file, judge each, write to
    judgement jsonl. Skip sessions already judged (resume).
    """
    
    if not master_path.exists():
        print(f"  [SKIP] Master file not found: {master_path}")
        return
    
    with open(master_path, "r", encoding="utf-8") as f:
        sessions = [json.loads(line) for line in f if line.strip()]
    
    total = len(sessions)
    already_done = count_existing_judgements(judgement_path)
    remaining = total - already_done
    
    print(f"  Master: {total} sessions | Done: {already_done} | Remaining: {remaining}")
    
    if remaining <= 0:
        print(f"  [SKIP] All sessions already judged")
        return
    
    judgement_path.parent.mkdir(parents=True, exist_ok=True)
    
    for i, session in enumerate(sessions[already_done:], start=already_done + 1):
        print(f"  [{i}/{total}]", end="  ", flush=True)
        start = datetime.now()
        
        judge_input = build_judge_input(session)
        scores, raw = call_judge(chat, judge_input, system_prompt=load_judge_system_prompt())
        
        elapsed = (datetime.now() - start).total_seconds()
        
        record = {
            "session_id": session.get("session_id"),
            "model_id": session.get("model_id"),
            "test_case_id": session.get("test_case_id"),
            "timestamp_judged": datetime.now().isoformat(),
            "scores": scores,
            "judge_failed": scores is None,
            "raw_judge_output": raw if scores is None else None,
        }
        
        with open(judgement_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        
        if scores is None:
            print(f"FAIL ({elapsed:.1f}s) — judge output not parseable, logged raw")
        else:
            score_summary = " ".join(
                f"{k[:3]}={v['score']}" for k, v in scores.items()
            )
            print(f"OK ({elapsed:.1f}s) — {score_summary}")


# Main: Iterate Over All model/scenario Master Files
# ------------------------------------------------------------------


def discover_master_files(target_dirs: list[str] | None = None) -> list[Path]:
    """Find master jsonl files.
    
    If target_dirs is provided, scan only those (e.g. ["./results/qwen-2.5-7b"]).
    Otherwise, discover all model dirs under results/, excluding judgements/.
    """
    
    if target_dirs is not None:
        dirs = [Path(d) for d in target_dirs]
    else:
        if not RESULTS_DIR.exists():
            return []
        dirs = [
            d for d in RESULTS_DIR.iterdir()
            if d.is_dir() and d.name != "judgements"
        ]
    
    masters = []
    for model_dir in dirs:
        if not model_dir.exists() or not model_dir.is_dir():
            print(f"[WARN] Skipping non-existent dir: {model_dir}")
            continue
        for jsonl in model_dir.glob("*.jsonl"):
            if jsonl.name.startswith("tmp_"):
                continue
            masters.append(jsonl)
    
    return sorted(masters)


def main(target_dirs: list[str] | None = None, test_single_line: tuple[str, int] | None = None):
    """
    target_dirs: list of model directories to evaluate (e.g. ["./results/qwen-2.5-7b"]). If None, discover all model dirs under results/.
    test_single_line: tuple (master_path, line_index_1_based) for single-session test. Output goes to stdout, NOT to judgement file. Use for prompt iteration.
    """
    
    load_dotenv()
    api_key = os.getenv("API_KEY")
    if not api_key:
        print("[ERROR] Missing API_KEY in .env")
        sys.exit(1)
    
    chat = ChatOpenAI(
        model=JUDGE_MODEL,
        api_key=api_key,
        temperature=JUDGE_TEMPERATURE,
        model_kwargs={
            "response_format": {"type": "json_schema", "json_schema": OUTPUT_SCHEMA}
        },
    )
    
    system_prompt_text = load_judge_system_prompt()
    
    # single-line test mode: judge one specific session, dump to stdout
    if test_single_line is not None:
        master_path_str, line_idx = test_single_line
        master_path = Path(master_path_str)
        if not master_path.exists():
            print(f"[ERROR] File not found: {master_path}")
            sys.exit(1)
        
        with open(master_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        if line_idx < 1 or line_idx > len(lines):
            print(f"[ERROR] Line {line_idx} out of range (file has {len(lines)} lines)")
            sys.exit(1)
        
        session = json.loads(lines[line_idx - 1])
        print(f"Testing single session from {master_path}, line {line_idx}")
        print(f"  session_id: {session.get('session_id')}")
        print(f"  test_case_id: {session.get('test_case_id')}")
        print(f"  turns: {len(session.get('history', []))}\n")
        
        judge_input = build_judge_input(session)
        scores, raw = call_judge(chat, system_prompt_text, judge_input)
        
        if scores is None:
            print(f"\n[FAIL] Judge output not parseable.\nRaw output:\n{raw}")
        else:
            print("Scores:")
            print(json.dumps(scores, indent=2, ensure_ascii=False))
        return
    
    # batch mode: discover or use specified dirs
    masters = discover_master_files(target_dirs)
    
    if not masters:
        print("[!] No master jsonl files found")
        return
    
    print(f"Judge run config:")
    print(f"  Judge model: {JUDGE_MODEL} (temp={JUDGE_TEMPERATURE})")
    print(f"  Master files found: {len(masters)}")
    print(f"  Started at: {datetime.now().isoformat()}\n")
    
    for idx, master_path in enumerate(masters, start=1):
        rel = master_path.relative_to(RESULTS_DIR)
        judgement_path = JUDGEMENTS_DIR / rel
        
        print(f"[{idx}/{len(masters)}] {master_path}")
        try:
            judge_file(master_path, judgement_path, chat, system_prompt_text)
        except KeyboardInterrupt:
            print("\n[!] Interrupted by user. Resume by re-running.")
            sys.exit(0)
        except Exception as e:
            print(f"  [ERROR] {type(e).__name__}: {e}")
        print()
    
    print(f"\nJudgement complete at {datetime.now().isoformat()}")



# Main Function - Debug
# ------------------------------------------------------------------

if __name__ == "__main__":
    # Case 1: full sweep
    #main()
    
    # Case 2: specified models
    #main(target_dirs=["./results/qwen-2.5-7b", "./results/llama-3.1-8b"])
    
    # Case 3: smoke test of single session
    main(test_single_line=("./results/qwen-2.5-7b/qwen-2.5-7b_01_schema_adherence.jsonl", 1))