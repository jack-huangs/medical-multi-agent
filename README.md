# MDAgents 医疗 multi-agent 方法复现环境

本项目用于在隔离、可复现的本地 Python 环境中运行官方 MDAgents 实现，并将模型后端配置为 DeepSeek Flash 的 OpenAI 兼容 API。

上游来源：

- 官方仓库：https://github.com/mitmedialab/MDAgents
- 本项目中的源码位置：`external/MDAgents`
- 由于当前 Windows Git 缺少 HTTPS remote helper，源码通过 GitHub `main.zip` 下载并解包，而不是用 `git clone` 完成。

详细安装与验证记录见 `docs/reproduction-log.md`。

## 重要边界

原论文实验使用的是论文设定中的模型和数据流程。本项目若使用 `deepseek-flash`，只能称为“MDAgents 方法复现”或“使用 DeepSeek Flash 的方法迁移复现”，不能称为论文指标复现，也不能把运行输出伪装成论文原始结果。

医疗问答输出只适合研究复现实验，不构成医学建议。

## 环境

本项目已迁移到 Miniconda 专用环境 `mdagents`，环境位置为：

```text
C:\Users\Administrator\miniconda3\envs\mdagents
```

Python 版本：

```text
Python 3.12.14
```

如果环境还不存在，可用以下命令重建：

```powershell
conda env create -f environment.yml
```

进入环境：

```powershell
conda activate mdagents
```

安装或刷新依赖：

```powershell
python -m pip install -r requirements.txt
```

离线健康检查：

```powershell
python scripts\health_check.py --check-env-name
python external\MDAgents\main.py --help
```

## DeepSeek Flash 配置

复制示例环境文件：

```powershell
Copy-Item .env.example .env
```

`.env.example` 只提供变量名和默认端点，不包含任何密钥：

```text
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
```

程序只读取项目根目录的 `.env` 文件，不读取系统环境变量。请只在该文件中保存真实 `DEEPSEEK_API_KEY`；`.gitignore` 会忽略它。不要把 API key 写入 README、脚本、提交记录或聊天消息。如果旧密钥已经出现在聊天中，应立即在 DeepSeek 控制台撤销并轮换。

## 数据与运行

上游代码默认从 `../data/{dataset}/test.jsonl` 和 `../data/{dataset}/train.jsonl` 读取数据。因此从 `external/MDAgents` 目录运行时，数据应放在项目根目录的 `data/{dataset}/` 下：

```text
data/
  medqa/
    train.jsonl
    test.jsonl
```

示例运行命令：

```powershell
Push-Location external\MDAgents
python main.py --model deepseek-flash --dataset medqa --difficulty adaptive --num_samples 10
Pop-Location
```

若需要在命令行显示每一次模型调用的进度，并保存完整的提示词、回复和耗时，追加 `--verbose`：

```powershell
python main.py --model deepseek-flash --dataset medqa --difficulty basic --num_samples 1 --verbose
```

运行结果会写入 `external/MDAgents/output/`。每次运行会生成：

- `{model}_{dataset}_{difficulty}.json`：最新一轮的简化结果文件，每次同配置运行会更新它；
- `{model}_{dataset}_{difficulty}_{day-time}.json`：本轮结果的完整归档，时间戳避免覆盖历史实验；
- `{model}_{dataset}_{difficulty}_{day-time}_trace.jsonl`：本轮逐次 Agent 调用的结构化追踪日志。日志不包含 API key。

例如，15 日 14:30:25 开始的基础 MedQA 实验会先生成 `deepseek-flash_medqa_basic.json`，再归档为 `deepseek-flash_medqa_basic_15-143025.json`，并写入对应的 `_trace.jsonl` 日志。

根目录 `.gitignore` 已忽略 `.env`、`.venv`、`data/`、`output/`、`runs/`、`results/` 和 `logs/` 等本地实验产物。
