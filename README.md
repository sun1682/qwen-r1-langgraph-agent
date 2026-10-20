# Qwen + DeepSeek-R1 LangGraph Agent

A local Python agent scaffold with a Qwen tool-calling node, a DeepSeek-R1 expert branch, SQLite checkpoints, and an explicit approval step for every shell command.

## Requirements

- Python 3.10 or newer
- Two local services that expose OpenAI-compatible chat-completions APIs (for example, vLLM or Ollama)

## Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item .env.example .env
```

Edit `.env` so both base URLs and model IDs match the services you started. For Ollama's OpenAI-compatible endpoint, the base URL is commonly `http://localhost:11434/v1`; the exact model name is whatever `ollama list` reports.

Start the agent with `agent chat` (or `python -m agent.cli chat`). Each chat prints a thread ID. Supply that same ID after restarting to resume the saved graph state.

## Shell approval and resume

The graph pauses before running a shell tool and displays the exact command and approval ID. Review the command. In another terminal, run:

```powershell
agent approve <request-id>
```

Then type `/resume` in the agent chat. The checkpointed graph resumes at the approval gate and runs that tool call. Every command gets a separate approval. File paths are constrained to `WORKSPACE_ROOT`; shell and Python code run with that directory as their current directory.

## Expert routing

Qwen decides when to invoke R1 and emits a `<delegate_to_r1>...</delegate_to_r1>` marker. The graph sends the question to the configured R1 endpoint, places the result in the conversation, and calls Qwen again to continue tool use and answer. The R1 branch is capped at three delegations per graph state to prevent an infinite loop.

## Notes

- Checkpoints and approval records are stored under `.agent/`, which is ignored by Git.
- `run_python` executes arbitrary Python code and `shell` executes commands, so use this scaffold only in a workspace where the configured model endpoints and user prompts are trusted. Shell still requires explicit per-command approval.
- Keep API keys and local endpoint configuration in `.env`, never in source control.

## Local Ollama configuration

The current `.env` targets the local Ollama OpenAI-compatible endpoint at `http://127.0.0.1:11434/v1`, with `qwen2.5:3b-q3_k_m` as the tool-calling main model and `deepseek-r1:7b-qwen-distill-q4_K_M` as the specialist. The Qwen 3B Q3_K_M and R1 7B Q4_K_M models are configured with 4K context. `OLLAMA_MAX_LOADED_MODELS=2` is set in the Windows user environment. Both models were verified loaded together on the RTX 5060 8 GB; observed total GPU use was about 7.3 GB, so heavy GPU applications may still force Ollama to unload one.



