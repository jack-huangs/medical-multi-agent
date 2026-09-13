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

请只在本机环境中设置真实 `DEEPSEEK_API_KEY`。不要把 API key 写入 README、脚本、提交记录或聊天消息。如果旧密钥已经出现在聊天中，应立即在 DeepSeek 控制台撤销并轮换。

PowerShell 临时设置示例：

```powershell
$env:DEEPSEEK_API_KEY = '...'
$env:DEEPSEEK_BASE_URL = 'https://api.deepseek.com'
$env:DEEPSEEK_MODEL = 'deepseek-flash'
```

不要把上面的占位符替换为真实密钥后提交。

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

运行结果会写入 `external/MDAgents/output/`；根目录 `.gitignore` 已忽略 `.env`、`.venv`、`data/`、`output/`、`runs/`、`results/` 和 `logs/` 等本地实验产物。
