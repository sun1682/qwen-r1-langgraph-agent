from __future__ import annotations

import argparse
import uuid

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from .config import load_settings
from .graph import build_graph
from .tools import request_shell_approval


def _display(content):
    if isinstance(content, str):
        return content
    return str(content)


def run_chat():
    settings = load_settings()
    graph = build_graph(settings)
    print("Qwen + DeepSeek-R1 LangGraph agent. Type /exit to quit; use the same thread id to resume.")
    thread_id = input("Thread id (blank for new): ").strip() or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    print(f"Thread id: {thread_id}")
    resume_pending = False
    while True:
        try:
            text = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text in ("/exit", "/quit"):
            break
        if text == "/resume":
            if not resume_pending:
                print("No interrupted approval is waiting to resume.")
                continue
            try:
                result = graph.invoke(Command(resume=True), config=config)
                resume_pending = False
            except Exception as exc:
                print(f"Resume failed: {exc}")
                continue
        else:
            result = None
        if not text:
            continue
        if result is None:
            try:
                result = graph.invoke({"messages": [HumanMessage(content=text)]}, config=config)
            except Exception as exc:
                # LangGraph exposes interrupt payloads in the saved graph state.
                state = graph.get_state(config)
                for task in getattr(state, "tasks", []):
                    for item in getattr(task, "interrupts", []):
                        value = getattr(item, "value", {})
                        if value.get("type") == "shell_approval":
                            print(f"\nHuman approval required. Review command:\n{value['command']}\n")
                            print(f"Approve in another terminal: agent approve {value['request_id']}")
                            print(f"Then type /resume here. Thread id: {thread_id}")
                            resume_pending = True
                if resume_pending:
                    continue
                print(f"Agent error: {exc}")
                continue
        for message in result.get("messages", []):
            if isinstance(message, AIMessage) and message.content:
                value = _display(message.content)
                if not value.startswith("[DeepSeek-R1 specialist result]"):
                    print(f"\nAgent> {value}")
            if getattr(message, "type", "") == "tool" and isinstance(message.content, str) and "APPROVAL_REQUIRED" in message.content:
                print(f"\n{message.content}")


def main():
    parser = argparse.ArgumentParser(prog="agent", description="Qwen + DeepSeek-R1 LangGraph agent")
    sub = parser.add_subparsers(dest="command")
    approve = sub.add_parser("approve", help="approve one exact shell command requested by the agent")
    approve.add_argument("request_id")
    sub.add_parser("chat", help="start an interactive chat")
    args = parser.parse_args()
    settings = load_settings()
    if args.command == "approve":
        print(request_shell_approval(settings, args.request_id))
    else:
        run_chat()


if __name__ == "__main__":
    main()
