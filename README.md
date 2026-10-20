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

## 显卡显存与模型组合建议

下表按**单张 NVIDIA 显卡**估算，型号是显存档位的例子，实际选择主要看可用显存。模型体积按 Ollama 页面列出的下载大小取近似值；下载大小不等于运行时显存占用。两个模型需要同时驻留时，还要给运行时、上下文 KV cache、Windows 桌面和其他 GPU 程序留空间。建议先把上下文限制在 4K，确认稳定后再逐步增加。

| 显存档位（显卡例子） | Qwen 主模型 | DeepSeek-R1 专家模型 | 适用情况 |
|---|---|---|---|
| 4 GB（GTX 1650 4GB 等） | Qwen2.5 1.5B Q4（约 1 GB） | DeepSeek-R1 1.5B Q4（约 1.1 GB） | 入门测试；推理和工具规划能力有限，使用 2K–4K 上下文 |
| 6 GB（GTX 1660 6GB 等） | Qwen2.5 3B Q3（约 1.6 GB） | DeepSeek-R1 1.5B Q4（约 1.1 GB） | 轻量本地助手；建议 4K 上下文 |
| 8 GB（RTX 4060 / RTX 5060 8GB 等） | Qwen2.5 3B Q3（约 1.6–1.7 GB） | DeepSeek-R1 7B Q4_K_M（约 4.7 GB） | 推荐的入门双模型组合；上下文先设 4K，并给桌面和其他程序留显存 |
| 12 GB（RTX 3060 12GB 等） | Qwen2.5 3B Q4（约 1.8 GB） | DeepSeek-R1 7B Q4_K_M（约 4.7 GB） | 比 8GB 更宽松；可尝试 4K–8K 上下文 |
| 16 GB（RTX 4060 Ti 16GB / RTX 5070 Ti 16GB 等） | Qwen2.5 7B Q3_K_M（约 3.8 GB） | DeepSeek-R1 7B Q4_K_M（约 4.7 GB） | 主模型工具调用更强，R1 保持 7B；可尝试 4K–8K |
| 24 GB（RTX 3090 / RTX 4090 24GB 等） | Qwen2.5 7B Q4（约 4.4 GB） | DeepSeek-R1 14B Q4_K_M（约 9 GB） | 更强的专家推理；可尝试 8K 上下文，观察实际占用 |
| 32 GB（RTX 5090 32GB 等） | Qwen2.5 7B Q4（约 4.4 GB） | DeepSeek-R1 32B Q4_K_M（约 20 GB） | 复杂推理能力更强；建议先从 4K 上下文开始 |
| 48 GB（RTX A6000 / RTX 6000 Ada 48GB 等） | Qwen2.5 14B Q4（约 9 GB） | DeepSeek-R1 32B Q4_K_M（约 20 GB） | 高质量双模型组合；能为更长上下文留出较多空间 |
| 80 GB 及以上 | Qwen2.5 14B Q4 或更大 | DeepSeek-R1 70B Q4_K_M（约 43 GB） | 适合高端单卡/多卡服务器；具体是否全量驻留取决于上下文和推理后端 |

**按你当前的 8GB 显卡**，建议先用本项目 `.env.example` 中的组合：`qwen2.5:3b-q3_k_m` + `deepseek-r1:7b-qwen-distill-q4_K_M`，上下文保持约 4K。你这台机器之前同时运行这两个模型时，显存占用约 7.3GB；如果显存不足，可关闭占用 GPU 的程序，或让 Ollama 一次只驻留一个模型。后者会在模型切换时多花加载时间，但不用改工作流逻辑。

这些只是起步建议，不是硬性保证：实际可用显存会受显卡输出桌面、上下文长度、并行请求、Ollama 配置和模型版本影响。模型较大不代表每种任务都更好；工具调用主模型优先选支持 Function Calling 的 Instruct 版本。Apple Silicon 应参考统一内存容量，AMD/Intel 显卡还需确认当前操作系统与 Ollama/推理后端支持情况，不能仅按显存数字套用。

参考： [Ollama Qwen2.5 模型标签与体积](https://ollama.com/library/qwen2.5/tags)、[Ollama DeepSeek-R1 模型标签与体积](https://ollama.com/library/deepseek-r1/tags)、[NVIDIA RTX 3060 规格](https://www.nvidia.com/en-us/geforce/graphics-cards/30-series/rtx-3060-3060ti/)、[RTX 4060 系列规格](https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/rtx-4060-4060ti/)、[RTX 5070 系列规格](https://www.nvidia.com/en-au/geforce/graphics-cards/50-series/rtx-5070-family/)、[RTX 5090 规格](https://www.nvidia.com/en-gb/geforce/graphics-cards/50-series/rtx-5090/)、[RTX A6000 规格](https://www.nvidia.com/en-au/products/workstations/rtx-a6000/)。
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

