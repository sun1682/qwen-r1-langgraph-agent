from __future__ import annotations

import re
import sqlite3
import uuid
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt, Command

from .config import Settings
from .tools import build_tools, record_shell_request


def _append_messages(left: list[BaseMessage], right: list[BaseMessage]) -> list[BaseMessage]:
    return left + right


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], _append_messages]
    route: str
    expert_question: str
    expert_answer: str
    expert_calls: int


def _needs_expert(message: AIMessage) -> bool:
    value = message.additional_kwargs.get("route_to_r1")
    if isinstance(value, bool):
        return value
    text = str(message.content)
    return "<delegate_to_r1>" in text.lower()


def _expert_question(message: AIMessage) -> str:
    value = message.additional_kwargs.get("r1_question")
    if value:
        return str(value)
    content = str(message.content)
    match = re.search(r"<delegate_to_r1>(.*?)</delegate_to_r1>", content, re.I | re.S)
    return match.group(1).strip() if match else content


def build_graph(settings: Settings):
    settings.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
    tools = build_tools(settings)
    tool_node = ToolNode(tools)
    qwen = ChatOpenAI(model=settings.qwen_model, base_url=settings.qwen_base_url,
                      api_key=settings.qwen_api_key, temperature=0).bind_tools(tools)
    r1 = ChatOpenAI(model=settings.r1_model, base_url=settings.r1_base_url,
                    api_key=settings.r1_api_key, temperature=0)
    system = SystemMessage(content=(
        "You are the main Qwen agent. Use tools for workspace tasks. For difficult reasoning, "
        "complex math, algorithm design, or when uncertain, delegate to DeepSeek-R1 by emitting "
        "<delegate_to_r1>your precise question and relevant context</delegate_to_r1> in your response. "
        "After the R1 answer is returned, continue the task and use tools as needed. "
        "The shell tool always requires a separate human approval; never claim it ran until a result returns. "
        "All file tools are restricted to WORKSPACE_ROOT."
    ))

    def main_agent(state: AgentState):
        messages = [system, *state.get("messages", [])]
        if state.get("expert_answer"):
            messages.append(SystemMessage(content="DeepSeek-R1 analysis result (verify it, then continue):\n" + state["expert_answer"]))
        response = qwen.invoke(messages)
        for call in response.tool_calls:
            if call.get("name") == "shell":
                args = call.get("args", {})
                request_id = str(uuid.uuid4())
                record_shell_request(settings, request_id, str(args.get("command", "")))
                call["id"] = request_id
        return {"messages": [response], "route": "r1" if _needs_expert(response) else "tools" if response.tool_calls else "done",
                "expert_question": _expert_question(response) if _needs_expert(response) else "",
                "expert_answer": ""}

    def approval_gate(state: AgentState):
        pending = []
        with sqlite3.connect(settings.approval_db) as conn:
            for message in reversed(state.get("messages", [])):
                if not isinstance(message, AIMessage):
                    continue
                for call in message.tool_calls:
                    if call.get("name") != "shell":
                        continue
                    request_id = call.get("id")
                    row = conn.execute("SELECT command, status FROM shell_approvals WHERE request_id=?", (request_id,)).fetchone()
                    if row and row[1] == "pending":
                        pending.append((request_id, row[0]))
                if pending or message.tool_calls:
                    break
        if not pending:
            return {}
        request_id, command = pending[0]
        decision = interrupt({"type": "shell_approval", "request_id": request_id, "command": command,
                              "instructions": f"Review the command, then run: agent approve {request_id}; resume with the same thread id."})
        with sqlite3.connect(settings.approval_db) as conn:
            current = conn.execute("SELECT status FROM shell_approvals WHERE request_id=?", (request_id,)).fetchone()
        cli_approved = current and current[0] == "approved"
        if decision is not True and not (isinstance(decision, dict) and decision.get("approved") is True) and not cli_approved:
            with sqlite3.connect(settings.approval_db) as conn:
                conn.execute("UPDATE shell_approvals SET status='rejected' WHERE request_id=? AND status='pending'", (request_id,))
            return {"messages": [AIMessage(content="Shell command was rejected by the human; I will not run it.")]}
        with sqlite3.connect(settings.approval_db) as conn:
            conn.execute("UPDATE shell_approvals SET status='approved' WHERE request_id=? AND status='pending'", (request_id,))
        return {}

    def expert(state: AgentState):
        question = state.get("expert_question", "")
        answer = r1.invoke([
            SystemMessage(content="You are DeepSeek-R1, a specialist reasoning model. Analyze carefully and return a concise, checkable answer. Do not claim to execute tools."),
            HumanMessage(content=question),
        ])
        content = str(answer.content)
        return {"messages": [AIMessage(content="[DeepSeek-R1 specialist result]\n" + content)],
                "expert_answer": content, "expert_calls": state.get("expert_calls", 0) + 1,
                "route": "main"}

    def after_main(state: AgentState) -> Literal["r1", "tools", "done"]:
        route = state.get("route", "done")
        if route == "r1" and state.get("expert_calls", 0) >= 3:
            return "done"
        return route if route in ("r1", "tools") else "done"

    builder = StateGraph(AgentState)
    builder.add_node("main_agent", main_agent)
    builder.add_node("r1_expert", expert)
    builder.add_node("tools", tool_node)
    builder.add_node("approval_gate", approval_gate)
    builder.add_edge(START, "main_agent")
    builder.add_conditional_edges("main_agent", after_main, {"r1": "r1_expert", "tools": "approval_gate", "done": END})
    builder.add_edge("approval_gate", "tools")
    builder.add_edge("r1_expert", "main_agent")
    builder.add_edge("tools", "main_agent")
    conn = sqlite3.connect(settings.checkpoint_db, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS shell_approvals (request_id TEXT PRIMARY KEY, command TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '')")
    conn.commit()
    return builder.compile(checkpointer=SqliteSaver(conn))


def extract_shell_approval(text: str):
    match = re.search(r"APPROVAL_REQUIRED request_id=([0-9a-f-]+).*?command: (.*)", text, re.S)
    if match:
        return match.group(1), match.group(2)
    return None

