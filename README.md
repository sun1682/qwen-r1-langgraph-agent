# Qwen + DeepSeek-R1 LangGraph Agent

一个运行在本机的双模型 LangGraph Agent 示例：Qwen 负责对话、Function Calling 和工具调度；遇到复杂推理时，流程会切到本地 DeepSeek-R1，取回分析结果后再交给 Qwen 继续执行。

## 功能简介

- **Qwen 主节点**：调用本地 Ollama 或其他 OpenAI 兼容的聊天接口。
- **R1 专家分支**：Qwen 可通过 `<delegate_to_r1>问题</delegate_to_r1>` 请求 DeepSeek-R1 分析数学、算法或复杂问题。
- **工具调用**：在工作区内读取/写入文件、运行 Python；shell 命令执行前必须人工批准。
- **状态保存**：LangGraph 使用 SQLite 保存对话图状态；输入原 thread ID 可以恢复已有会话。当前 CLI 尚未支持在进程重启后继续一个停在 shell 审批处的中断。
- **命令审批记录**：保存于本地 `.agent/` 目录，不会提交到 Git。

## 工作流程

```text
用户输入 → Qwen 主节点
               ├─ 普通问题 → 组织答案
               ├─ 需要工具 → 审批检查 → 工具执行 → Qwen 继续
               └─ 复杂推理 → DeepSeek-R1 分析 → Qwen 继续
```

## 环境要求

- Python 3.10 或更新版本
- Git（克隆仓库时需要）
- 两个可访问的 OpenAI 兼容 Chat Completions API。可以都由 Ollama 提供，也可以分别使用不同服务。
- 至少一个 Qwen 模型和一个 DeepSeek-R1 模型已下载并由对应服务提供

> 本项目只连接模型 API，不负责下载或启动模型。请先启动 Ollama/vLLM 等服务，并确认模型可以从本机访问。

## 安装

在 PowerShell 中执行：

```powershell
git clone <GitHub仓库地址>
cd <仓库目录>
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
Copy-Item .env.example .env
```

如果 PowerShell 阻止激活虚拟环境，也可以不激活，直接调用虚拟环境里的 Python 和命令：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\agent.exe chat
```

## 配置模型

编辑项目根目录的 `.env`。Ollama 通常使用 `http://127.0.0.1:11434/v1`；模型名要与 `ollama list` 输出完全一致。

```dotenv
QWEN_BASE_URL=http://127.0.0.1:11434/v1
QWEN_API_KEY=ollama
QWEN_MODEL=qwen2.5:3b-q3_k_m

R1_BASE_URL=http://127.0.0.1:11434/v1
R1_API_KEY=ollama
R1_MODEL=deepseek-r1:7b-qwen-distill-q4_K_M

WORKSPACE_ROOT=.
CHECKPOINT_DB=./.agent/checkpoints.sqlite
APPROVAL_DB=./.agent/approvals.sqlite
MAX_TOOL_OUTPUT_CHARS=20000
```

对于其他 OpenAI 兼容服务，将两个 `*_BASE_URL`、`*_API_KEY` 和 `*_MODEL` 改为该服务实际使用的地址、密钥和模型名。即使是本地服务，也应按本地部署的接口配置修改。

**不要提交 `.env` 或真实 API 密钥。** `.env` 已加入 `.gitignore`；分享配置时请使用 `.env.example` 中的占位/示例值。

## 启动和基本使用

确认模型服务正在运行后，在项目目录启动：

```powershell
agent chat
```

也可以使用：

```powershell
python -m agent.cli chat
```

启动后按提示输入 thread ID：

- 留空：创建新会话，并记下终端显示的 thread ID。
- 输入已有 ID：尝试从 SQLite checkpoint 恢复该会话。
- 输入 `/exit`：退出聊天。

给 Agent 提出任务即可。Qwen 会自行决定直接回答、调用工具，或把难题交给 R1。R1 只负责分析，不会执行工具；分析结果返回后，Qwen 才会继续。

## Shell 命令审批与恢复

当 Agent 请求执行 shell 命令时，流程会暂停并显示**完整命令**、审批 ID 和当前 thread ID。先检查命令及其影响，再在项目目录的另一个 PowerShell 窗口执行：

```powershell
agent approve <审批ID>
```

回到聊天窗口输入：

```text
/resume
```

审批针对每条命令单独生效。拒绝或不批准时，不要执行审批命令。当前 CLI 只允许在同一运行进程中对已捕获的 shell 中断执行 `/resume`。普通会话状态保存在 SQLite，可在重启后输入原 thread ID 恢复；但如果进程在 shell 审批中断期间退出，CLI 目前没有跨进程继续该中断的入口。

## 工具范围与安全说明

- 文件工具将路径限制在 `WORKSPACE_ROOT` 下。
- Python 工具会运行模型提供的 Python 代码；shell 工具会执行模型提出的命令。Shell 有人工审批门，但**批准前仍要逐条检查命令**。
- 只对你信任的模型服务和提示词使用这些工具。不要让 Agent 接触不应读取或修改的文件。
- 将 `WORKSPACE_ROOT` 指向专门的项目目录，避免设置为整个用户目录或磁盘根目录。
- 本项目不是操作系统级沙箱；人工 shell 审批不能替代权限隔离、备份或安全审查。

## 本地数据与文件

- `.env`：本机模型端点和配置，不纳入 Git。
- `.agent/checkpoints.sqlite`：会话 checkpoint。
- `.agent/approvals.sqlite`：shell 审批记录。
- `.venv/`：Python 虚拟环境。

上述本地文件/目录均由 `.gitignore` 排除。删除 `.agent/` 会清除保存的会话和审批记录。

## 常见问题

**模型连接失败**：检查 Ollama/vLLM 服务状态、`*_BASE_URL` 是否可访问，以及 `.env` 中模型名是否与服务报告的一致。

**Qwen 不调用工具**：确认主模型支持工具调用，并确认 Qwen 接口使用兼容的 Chat Completions / Function Calling 格式。

**无法恢复会话**：确认重启后仍在同一项目目录运行，并输入原 thread ID；checkpoint 默认存放于 `.agent/checkpoints.sqlite`。跨进程恢复停在 shell 审批处的中断目前尚不支持。

**找不到 `agent` 命令**：确认虚拟环境已激活且执行过 `python -m pip install -e .`，或使用 `python -m agent.cli chat`。

## 开发依赖

依赖版本范围见 `pyproject.toml`。当前包括 LangGraph、SQLite checkpoint、LangChain OpenAI 适配器及 `python-dotenv`。

