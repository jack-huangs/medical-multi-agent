# 证据依赖感知的医疗多 Agent 协作

当前研究：追踪多个 Agent 对证据的引用和继承，研究重复证据是否放大错误共识。已有 LangGraph / LangChain RAG 实验原型；尚未证明方法有效性。

## 从这里开始

- [文件树与逐文件用途](docs/PROJECT_STRUCTURE.md)：查看代码、资料、数据及实验记录的职责。
- [研究协议](docs/evidence-dependency-protocol.md)：四组干预、引用约束、评价指标和实验边界。
- [困难数据集与最新实验](docs/hard-benchmark-protocol.md)：MedXpertQA 开发集、难度探测、RAG 语料准备。
- [困难题协作检查](docs/hard-collaboration-check.md)：2026-09-25 三题五种流程检查、引用审计及共识形成分析。
- [早期原型进展](docs/evidence-dependency-progress.md)：单题调试和成本记录。
- [MDAgents 复现](baselines/mdagents/README.md)：旧复现源码、环境、流程图和历史实验集中在此。

## 当前代码与环境

`scripts/` 为当前研究代码，`examples/evidence_dependency/` 为虚构离线测试样例，`data/` 为共享原始数据集，`runs/evidence_dependency/` 保存新研究的开发集、语料、实验及隔离环境。

在项目根目录运行离线测试（不调用模型 API）：

```powershell
& ./runs/evidence_dependency/.venv/Scripts/python.exe -m unittest discover -s scripts -p 'test_*.py'
& C:/Users/Administrator/miniconda3/envs/mdagents/python.exe -m unittest discover -s baselines/mdagents/scripts -p 'test_*.py'
```

新研究依赖见 `requirements-evidence.txt`，已安装环境完整版本见 `runs/evidence_dependency/environment-freeze.txt`。旧复现使用独立 conda 环境，不与新环境混装。

`.env` 保留在根目录，由两套代码共享读取；只在本地保存密钥，不提交。`.env.example` 是配置模板。

## 整理记录（2026-09-24）

旧 `external/MDAgents/` → `baselines/mdagents/upstream/`；旧 `runs/consensus_pilot_20260923/` → `baselines/mdagents/runs/consensus_pilot_20260923/`。复现专用脚本、环境和说明一并迁入 `baselines/mdagents/`。

历史实验配置、提示词、日志、源码快照原样保留，其中的旧绝对路径反映当时运行位置，不应据此删除或重写记录。整理更改了活动脚本，旧冻结配置可能拒绝直接续跑；新实验应建立新输出目录。

共享 MedQA 数据仍保留在 `data/medqa/`；新研究从旧 reserve 集选取开发样本的来源关系仍保留。新研究的 `.venv` 未移动，以免破坏 Windows 环境内的路径。

删除了根目录 7 份论文原文文本、无效 SDK 草稿及 PPT 临时构建/渲染文件；保留阅读笔记、PPT 源码与输出版本。实验 RAG 文献 XML 和来源记录未删除。详细移动/删除清单（含删除文件 SHA256）见 `docs/cleanup-manifest.json`，清单不提供已删文件内容恢复。

验证：当前研究 20 项、旧复现 4 项离线测试通过；旧环境健康检查与主程序帮助入口通过。本次整理没有付费模型调用。
