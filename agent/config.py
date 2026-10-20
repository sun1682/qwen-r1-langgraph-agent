from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    qwen_base_url: str
    qwen_api_key: str
    qwen_model: str
    r1_base_url: str
    r1_api_key: str
    r1_model: str
    workspace_root: Path
    checkpoint_db: Path
    approval_db: Path
    max_tool_output_chars: int


def load_settings() -> Settings:
    load_dotenv()
    root = Path(os.getenv("WORKSPACE_ROOT", ".")).expanduser().resolve()
    checkpoint = Path(os.getenv("CHECKPOINT_DB", "./.agent/checkpoints.sqlite")).expanduser()
    approval = Path(os.getenv("APPROVAL_DB", "./.agent/approvals.sqlite")).expanduser()
    if not checkpoint.is_absolute():
        checkpoint = root / checkpoint
    if not approval.is_absolute():
        approval = root / approval
    return Settings(
        qwen_base_url=os.getenv("QWEN_BASE_URL", "http://localhost:8000/v1"),
        qwen_api_key=os.getenv("QWEN_API_KEY", "local"),
        qwen_model=os.getenv("QWEN_MODEL", "Qwen/Qwen2.5-14B-Instruct"),
        r1_base_url=os.getenv("R1_BASE_URL", "http://localhost:8001/v1"),
        r1_api_key=os.getenv("R1_API_KEY", "local"),
        r1_model=os.getenv("R1_MODEL", "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B"),
        workspace_root=root,
        checkpoint_db=checkpoint.resolve(),
        approval_db=approval.resolve(),
        max_tool_output_chars=max(1000, int(os.getenv("MAX_TOOL_OUTPUT_CHARS", "20000"))),
    )
