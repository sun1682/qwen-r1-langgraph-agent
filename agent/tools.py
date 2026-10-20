from __future__ import annotations

import ast
import operator
import os
import sqlite3
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from .config import Settings

_SAFE_MATH = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_SHELL_RUN_LOCK = threading.Lock()


def _eval_math(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_math(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_MATH:
        return _SAFE_MATH[type(node.op)](_eval_math(node.left), _eval_math(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_MATH:
        return _SAFE_MATH[type(node.op)](_eval_math(node.operand))
    raise ValueError("Only numeric literals and basic arithmetic operators are allowed")


def _resolve(root: Path, raw: str) -> Path:
    candidate = (root / raw).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Path must stay inside WORKSPACE_ROOT")
    return candidate


def build_tools(settings: Settings):
    root = settings.workspace_root
    approvals = settings.approval_db
    output_limit = settings.max_tool_output_chars

    @tool
    def read_file(path: str) -> str:
        """Read a UTF-8 text file under the configured workspace root."""
        target = _resolve(root, path)
        return target.read_text(encoding="utf-8")[:output_limit]

    @tool
    def write_file(path: str, content: str) -> str:
        """Write a UTF-8 text file under the configured workspace root, creating parent folders."""
        target = _resolve(root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} characters to {target.relative_to(root)}"

    @tool
    def run_python(code: str) -> str:
        """Run Python code in an isolated subprocess with the workspace as its current directory."""
        result = subprocess.run(
            [sys.executable, "-I", "-c", code], cwd=root, capture_output=True,
            text=True, timeout=60, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        stdout = result.stdout[-output_limit:]
        stderr = result.stderr[-output_limit:]
        return f"exit_code={result.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"

    @tool
    def calculate(expression: str) -> str:
        """Evaluate basic arithmetic without executing Python code."""
        tree = ast.parse(expression, mode="eval")
        return str(_eval_math(tree))

    @tool
    def shell(command: str) -> str:
        """Run a shell command in the workspace. Every command requires a separately approved request id."""
        # Approval requests are inserted by the graph node before ToolNode runs. Pick
        # the oldest exact-match request that is still pending or approved.
        with _SHELL_RUN_LOCK, sqlite3.connect(approvals) as conn:
            row = conn.execute("SELECT request_id, status, output FROM shell_approvals WHERE command=? AND status IN ('approved','done') ORDER BY CASE status WHEN 'approved' THEN 0 ELSE 1 END, rowid LIMIT 1", (command,)).fetchone()
            if row is None:
                return "Command is not approved. Ask the agent to request approval before retrying."
            request_id, status, recorded_output = row
            if status == "done":
                return recorded_output
            completed = subprocess.run(command, cwd=root, shell=True, capture_output=True,
                                       text=True, timeout=120)
            output = f"exit_code={completed.returncode}\nstdout:\n{completed.stdout[-output_limit:]}\nstderr:\n{completed.stderr[-output_limit:]}"
            conn.execute("UPDATE shell_approvals SET status='done', output=? WHERE request_id=?",
                         (output, request_id))
            return output

    return [read_file, write_file, run_python, calculate, shell]


def request_shell_approval(settings: Settings, request_id: str) -> str:
    settings.approval_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.approval_db) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS shell_approvals (request_id TEXT PRIMARY KEY, command TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '')")
        row = conn.execute("SELECT command, status FROM shell_approvals WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            return f"Unknown approval request: {request_id}"
        if row[1] != "pending":
            return f"Request is already {row[1]}"
        conn.execute("UPDATE shell_approvals SET status='approved' WHERE request_id=?", (request_id,))
        return f"Approval recorded for exact command: {row[0]} (resume the same thread to execute it)"


def record_shell_request(settings: Settings, request_id: str, command: str) -> None:
    settings.approval_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.approval_db) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS shell_approvals (request_id TEXT PRIMARY KEY, command TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '')")
        conn.execute("INSERT OR IGNORE INTO shell_approvals(request_id, command, status) VALUES (?, ?, 'pending')",
                     (request_id, command))
