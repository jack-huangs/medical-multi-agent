# 复现环境配置记录

记录时间：2026-09-11 17:39 Asia/Shanghai 附近。

## 仓库初始状态

初始检查命令：

```powershell
Get-ChildItem -Force
git status --short --branch
rg --files -g 'README*' -g 'AGENTS*' -g '.gitignore' -g 'pyproject.toml' -g 'requirements*.txt' -g 'environment*.yml' -g 'setup.py' -g 'setup.cfg' -g '.env*'
```

结果：

- 工作区只有 `.git` 目录。
- `git status --short --branch` 输出 `## No commits yet on master`。
- 未发现 README、AGENTS、依赖文件或环境文件。

## Python 与 Git 状态

检查命令：

```powershell
python --version
py --list
conda --version
git --version
```

结果：

- `python`：未识别。
- `py`：未识别。
- `conda`：未识别。
- `git`：`git version 2.53.0.windows.3`。

Codex 工作区依赖提供的 Python：

```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
```

版本检查结果：

```text
Python 3.12.14
```

## 上游源码准备

优先尝试官方仓库：

```powershell
git clone https://github.com/mitmedialab/MDAgents external/MDAgents
```

失败结果：

```text
git: 'remote-https' is not a git command. See 'git --help'.
fatal: remote helper 'https' aborted session
```

使用 Codex 运行时 Git 再试，结果相同。随后尝试 `curl.exe` 下载源码压缩包：

```powershell
curl.exe -L https://github.com/mitmedialab/MDAgents/archive/refs/heads/main.zip -o external\MDAgents-main.zip
```

失败结果：

```text
curl: (35) schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030e)
```

改用 Codex Python 的 HTTPS 栈下载成功：

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import urllib.request; url='https://github.com/mitmedialab/MDAgents/archive/refs/heads/main.zip'; out=r'external\MDAgents-main.zip'; print('downloading', url); urllib.request.urlretrieve(url, out); print('saved', out)"
tar.exe -xf external\MDAgents-main.zip -C external
Rename-Item external\MDAgents-main MDAgents
```

结果：

- 源码已放置在 `external/MDAgents`。
- 官方项目包含 `main.py`、`utils.py`、`requirements.txt`、论文 PDF 和图片资源。
- 尝试用 GitHub API 查询 `main` 提交 SHA 时收到 `HTTP Error 403: rate limit exceeded`，因此本记录不声明精确提交 SHA。

## 依赖安装

创建项目内虚拟环境：

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv .venv
```

升级 pip：

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

结果：

```text
Successfully installed pip-26.2.1
```

首次安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

遇到 `pptree` 构建 wheel 时访问用户级 pip 缓存被拒绝：

```text
WARNING: Building wheel for pptree failed: [WinError 5]
Failed to build installable wheels for some pyproject.toml based projects
pptree
```

使用无默认缓存安装后成功：

```powershell
$env:PIP_CACHE_DIR = (Join-Path (Get-Location) '.pip-cache')
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.txt
```

随后验证发现两个兼容性问题：

- `climage==0.2.0` 需要 `pkg_resources`，因此补充 `setuptools==80.9.0`。
- `openai==1.14.2` 与 `httpx==0.28.1` 不兼容，初始化时报 `Client.__init__() got an unexpected keyword argument 'proxies'`，因此补充 `httpx<0.28`。

最终安装命令：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

结果：

```text
Successfully installed httpx-0.27.2 setuptools-80.9.0
```

依赖一致性检查：

```powershell
.\.venv\Scripts\python.exe -m pip check
```

结果：

```text
No broken requirements found.
```

## 离线验证

导入检查：

```powershell
.\.venv\Scripts\python.exe scripts\health_check.py --check-env-name
```

结果：

```text
OK import openai
OK import google.generativeai
OK import tqdm
OK import prettytable
OK import termcolor
OK import pptree
OK import climage
OK import utils
OK .env.example documents DEEPSEEK_API_KEY
OK no API key value was read
OK upstream source: C:\Users\Administrator\Documents\ChatGPT\multi-agent医疗专家团\external\MDAgents
```

命令行帮助检查：

```powershell
.\.venv\Scripts\python.exe external\MDAgents\main.py --help
```

结果：

```text
usage: main.py [-h] [--dataset DATASET] [--model MODEL]
               [--difficulty DIFFICULTY] [--num_samples NUM_SAMPLES]
```

DeepSeek OpenAI 兼容客户端初始化检查，使用占位符值且不发起 API 请求：

```powershell
$env:DEEPSEEK_API_KEY='dummy-for-offline-init-only'
$env:DEEPSEEK_BASE_URL='https://api.deepseek.com'
$env:DEEPSEEK_MODEL='deepseek-flash'
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, r'external\MDAgents'); import utils; model, client = utils.setup_model('deepseek-flash'); print('OK deepseek client initialized without API request')"
```

结果：

```text
OK deepseek client initialized without API request
```

字节码编译检查：

```powershell
.\.venv\Scripts\python.exe -m compileall -q scripts external\MDAgents
```

结果：退出码为 0，无错误输出。

## 密钥与结果边界

- 未请求、记录、回显或提交任何真实 API key。
- 示例变量名统一为 `DEEPSEEK_API_KEY`。
- 若旧密钥曾出现在聊天中，应立即撤销并轮换。
- 使用 DeepSeek Flash 时只能称为“MDAgents 方法复现”或“方法迁移复现”，不能称为论文指标复现。

## 迁移到 conda 环境

迁移时间：2026-09-11 Asia/Shanghai。

创建环境前检查：

```powershell
conda info --envs
conda --version
```

结果：

- `conda 26.3.2`
- 起初没有 `mdagents` 环境。

首次创建环境时，conda 要求接受默认频道 Terms of Service：

```powershell
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2
```

结果：

```text
accepted Terms of Service for https://repo.anaconda.com/pkgs/main
accepted Terms of Service for https://repo.anaconda.com/pkgs/r
accepted Terms of Service for https://repo.anaconda.com/pkgs/msys2
```

创建 conda 环境：

```powershell
conda create -y -n mdagents python=3.12 pip
```

结果：

```text
environment location: C:\Users\Administrator\miniconda3\envs\mdagents
python-3.12.14
```

安装依赖时，`conda run -n mdagents python -m pip install -r requirements.txt` 安装过程已执行，但 conda 在回显输出时触发 Windows GBK 编码错误：

```text
UnicodeEncodeError: 'gbk' codec can't encode character
```

因此改用环境内 Python 直接安装：

```powershell
& C:\Users\Administrator\miniconda3\envs\mdagents\python.exe -m pip install -r requirements.txt
```

结果：依赖已安装到 `C:\Users\Administrator\miniconda3\envs\mdagents\Lib\site-packages`。

conda 环境验证：

```powershell
& C:\Users\Administrator\miniconda3\envs\mdagents\python.exe --version
& C:\Users\Administrator\miniconda3\envs\mdagents\python.exe -m pip check
& C:\Users\Administrator\miniconda3\envs\mdagents\python.exe scripts\health_check.py --check-env-name
& C:\Users\Administrator\miniconda3\envs\mdagents\python.exe external\MDAgents\main.py --help
```

结果：

```text
Python 3.12.14
No broken requirements found.
OK import openai
OK import google.generativeai
OK import tqdm
OK import prettytable
OK import termcolor
OK import pptree
OK import climage
OK import utils
OK .env.example documents DEEPSEEK_API_KEY
OK no API key value was read
```

DeepSeek OpenAI 兼容客户端初始化检查，使用占位符且不发起 API 请求：

```powershell
$env:DEEPSEEK_API_KEY='dummy-for-offline-init-only'
$env:DEEPSEEK_BASE_URL='https://api.deepseek.com'
$env:DEEPSEEK_MODEL='deepseek-flash'
& C:\Users\Administrator\miniconda3\envs\mdagents\python.exe -c "import sys; sys.path.insert(0, r'external\MDAgents'); import utils; model, client = utils.setup_model('deepseek-flash'); print('OK deepseek client initialized without API request')"
```

结果：

```text
OK deepseek client initialized without API request
```
