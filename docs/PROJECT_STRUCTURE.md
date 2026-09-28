# 项目文件树与用途

整理日期：2026-09-24。当前研究代码与旧复现分开；共享数据、密钥和运行环境保持稳定位置。

```text
multi-agent医疗项目/
├── README.md                       项目入口
├── .env / .env.example / .gitignore 配置、模板与忽略规则
├── requirements-evidence.txt       当前研究依赖
├── scripts/                        当前研究脚本（见下表）
├── docs/                           研究协议、进展、文件索引与整理记录
│   └── maintenance/                本次一次性整理脚本存档，不再执行
├── examples/evidence_dependency/   虚构离线测试输入、标签、证据
├── data/
│   ├── medqa/                      两套研究共享原始题库
│   └── medxpertqa/                 固定版本官方困难题库
├── runs/evidence_dependency/
│   ├── .venv/                      当前研究 Python 环境，未移动
│   ├── dev30/ / hard_dev30/         MedQA / MedXpertQA 开发集
│   ├── corpus_smoke/               单题原型文献库
│   ├── hard_corpus_v1/             困难题共享文献库与原始 XML
│   ├── difficulty_probe_20260924/   60 题单 Agent 难度探测
│   ├── hard_check3_20260925/        三题协作、单 Agent 对照与审计
│   ├── corpus_gap_candidates_20260925/  语料缺口候选搜索，未并入实验
│   ├── offline_smoke/              假后端流程检查，不作实验结果
│   ├── live_smoke_001..003/         早期调试及失败记录
│   └── live_smoke_004_debug/        调试恢复结果，不作正式对照
├── baselines/mdagents/             旧 MDAgents 复现集中目录
│   ├── README.md / environment.yml / requirements.txt
│   ├── upstream/                   上游源码、本地修复及原始输出
│   ├── scripts/                    路由实验、复核、审计及测试
│   ├── docs/                       复现记录、旧实验设计与流程图
│   └── runs/                       原两批 100 题、冻结分组及复核产物
└── references/
    ├── notes/                      论文阅读笔记
    └── presentations/              分享规划、PPT 源码及输出版本
```

## 每个维护文件的用途

下表逐项列出活动代码、配置、说明与人工资料。数千个实验产物按目录/文件类型解释，并在 `FILE_INVENTORY.jsonl` 中逐文件列出路径、大小和用途；不展开第三方环境与 Git 内部文件。

| 文件 | 用途 |
|---|---|
| `.env` | 本地模型 API 配置与密钥；不提交、不展示内容。 |
| `.env.example` | 不含密钥的环境配置模板。 |
| `.gitignore` | 版本控制忽略规则，隔离密钥、数据、环境与实验产物。 |
| `README.md` | 项目入口：研究状态、环境、运行检查和迁移说明。 |
| `requirements-evidence.txt` | 当前证据依赖研究的直接 Python 依赖版本。 |
| `baselines/mdagents/README.md` | 旧 MDAgents 复现使用说明；命令从项目根目录执行。 |
| `baselines/mdagents/environment.yml` | 旧 MDAgents conda 环境声明。 |
| `baselines/mdagents/requirements.txt` | 所在组件的 Python 依赖；复现锁定配置以上层 baselines/mdagents/requirements.txt 为准。 |
| `baselines/mdagents/docs/advanced.drawio` | MDAgents 算法流程图，可用对应编辑器查看或修改。 |
| `baselines/mdagents/docs/basic.drawio` | MDAgents 算法流程图，可用对应编辑器查看或修改。 |
| `baselines/mdagents/docs/consensus-pilot-design.md` | 旧共识研究先导实验设计及日志完整性限制。 |
| `baselines/mdagents/docs/intermediate.drawio` | MDAgents 算法流程图，可用对应编辑器查看或修改。 |
| `baselines/mdagents/docs/main函数逻辑图.png` | 说明文档或流程图图片资源。 |
| `baselines/mdagents/docs/reproduction-log.md` | MDAgents 安装、迁移和复现历史。 |
| `baselines/mdagents/docs/低难度题目处理流程.drawio` | MDAgents 算法流程图，可用对应编辑器查看或修改。 |
| `baselines/mdagents/scripts/audit_pilot_routing.py` | 核验旧实验路由响应和单次运行日志完整性。 |
| `baselines/mdagents/scripts/create_basic_xmind.py` | 生成 MDAgents 基础流程 XMind 图。 |
| `baselines/mdagents/scripts/health_check.py` | 检查旧 MDAgents 环境和源码导入，不调用 API。 |
| `baselines/mdagents/scripts/prepare_consensus_pilot.py` | 冻结旧 MedQA pilot/reserve/demonstrations 分组及标签。 |
| `baselines/mdagents/scripts/review_consensus_pilot.py` | 旧实验答案复核与汇总。 |
| `baselines/mdagents/scripts/run_consensus_pilot.py` | 旧 MDAgents 自适应实验运行器，含隔离 worker、轨迹与评分。 |
| `baselines/mdagents/scripts/test_pilot_offline.py` | 旧路由解析、评分和专家消息传递回归测试。 |
| `baselines/mdagents/upstream/README.md` | 上游项目原始说明，原文路径语境属于上游仓库。 |
| `baselines/mdagents/upstream/main.py` | MDAgents 上游主程序及命令行入口。 |
| `baselines/mdagents/upstream/requirements.txt` | 所在组件的 Python 依赖；复现锁定配置以上层 baselines/mdagents/requirements.txt 为准。 |
| `baselines/mdagents/upstream/utils.py` | MDAgents 模型调用、难度路由和多专家协作实现，包含本地修复。 |
| `baselines/mdagents/upstream/imgs/ablation1.png` | 说明文档或流程图图片资源。 |
| `baselines/mdagents/upstream/imgs/ablation2.png` | 说明文档或流程图图片资源。 |
| `baselines/mdagents/upstream/imgs/ablation4.png` | 说明文档或流程图图片资源。 |
| `baselines/mdagents/upstream/imgs/animation.gif` | 说明文档或流程图图片资源。 |
| `baselines/mdagents/upstream/imgs/case_study.png` | 说明文档或流程图图片资源。 |
| `baselines/mdagents/upstream/imgs/comparison.png` | 说明文档或流程图图片资源。 |
| `baselines/mdagents/upstream/imgs/datasets.png` | 说明文档或流程图图片资源。 |
| `baselines/mdagents/upstream/imgs/image (30).png` | 说明文档或流程图图片资源。 |
| `baselines/mdagents/upstream/imgs/main_table.png` | 说明文档或流程图图片资源。 |
| `baselines/mdagents/upstream/imgs/radar.png` | 说明文档或流程图图片资源。 |
| `baselines/mdagents/upstream/imgs/teaser.png` | 说明文档或流程图图片资源。 |
| `baselines/mdagents/upstream/pdf/paper.pdf` | 上游仓库随附的 MDAgents 论文，属于复现参考，保留在基线目录。 |
| `docs/PROJECT_STRUCTURE.md` | 当前目录树和文件用途导航。 |
| `docs/cleanup-manifest.json` | 此次移动/删除记录；删除项含哈希、大小与原因，不能恢复原文。 |
| `docs/evidence-dependency-progress.md` | 早期原型与单题调试进度及成本；最新困难实验另见 hard-benchmark-protocol。 |
| `docs/evidence-dependency-protocol.md` | 当前研究假设、实验组、数据隔离、指标与边界。 |
| `docs/hard-benchmark-protocol.md` | 困难数据来源、冻结规则、60 题探测结果及 RAG 语料现状。 |
| `docs/hard-collaboration-check.md` | 困难题三题协作检查的预定范围、证据筛查和运行结果。 |
| `docs/maintenance/reorganize_workspace.ps1.txt` | 此次一次性整理操作的源码记录，仅供审计；不要再次执行。 |
| `docs/maintenance/update_layout.py.txt` | 此次一次性整理操作的源码记录，仅供审计；不要再次执行。 |
| `examples/evidence_dependency/corpus.jsonl` | 虚构离线测试样例（输入、标签或证据），不构成医学实验结果。 |
| `examples/evidence_dependency/inputs.jsonl` | 虚构离线测试样例（输入、标签或证据），不构成医学实验结果。 |
| `examples/evidence_dependency/labels.jsonl` | 虚构离线测试样例（输入、标签或证据），不构成医学实验结果。 |
| `references/notes/KAMAC.md` | KAMAC 论文阅读笔记。 |
| `references/notes/rare_disease_traceble_reasoning.md` | 罕见病诊断与可追踪推理阅读笔记。 |
| `references/presentations/build_deck.mjs` | 历史论文分享 PPT 构建源码；依赖当时的演示文稿工具运行时。 |
| `references/presentations/medical_multi_agent_group_meeting_zh_cn_final.pptx` | 历史论文分享演示稿；保留人工成果和不同输出版本。 |
| `references/presentations/多智能体医疗论文分享PPT内容规划.md` | 论文分享 PPT 的内容规划。 |
| `references/presentations/versions/多智能体医疗论文分享.pptx` | 历史论文分享演示稿；保留人工成果和不同输出版本。 |
| `references/presentations/versions/多智能体医疗论文分享_最终版.pptx` | 历史论文分享演示稿；保留人工成果和不同输出版本。 |
| `references/presentations/versions/多智能体医疗论文分享_最终版_v2.pptx` | 历史论文分享演示稿；保留人工成果和不同输出版本。 |
| `references/presentations/versions/多智能体医疗论文分享_连线修正版.pptx` | 历史论文分享演示稿；保留人工成果和不同输出版本。 |
| `references/presentations/versions/多智能体医疗论文分享_连线修正版_v2.pptx` | 历史论文分享演示稿；保留人工成果和不同输出版本。 |
| `scripts/analyze_consensus_mechanism.py` | 区分初始错误一致与讨论后形成的错误一致，单独统计正确专家被带偏。 |
| `scripts/audit_evidence_run.py` | 离线重放引用及来源继承验证，区分截断、无效引用和缺失父观点；不修复答案。 |
| `scripts/build_file_index.py` | 重新生成本文件和逐文件用途清单；不调用 API，不读取密钥内容。 |
| `scripts/build_hard_corpus.py` | 按冻结检索主题建立困难题共享文献库和下载清单。 |
| `scripts/diagnose_hard_retrieval.py` | 比较题目、题目加选项和人工主题查询；仅作覆盖排查，不作医学相关性评分。 |
| `scripts/download_medxpertqa.py` | 下载固定官方 MedXpertQA 版本并记录校验信息。 |
| `scripts/evaluation_stats.py` | 共享 Wilson 比例置信区间计算，避免新研究依赖旧运行器。 |
| `scripts/evidence_core.py` | BM25 检索、结构化意见验证、引用检查、来源账本和重复证据干预。 |
| `scripts/evidence_workflow.py` | LangGraph 工作流：检索、初始独立意见、四组协作条件和单 Agent 对照。 |
| `scripts/import_evidence_article.py` | 导入 Europe PMC 开放许可文章，保留 XML、来源和段落位置。 |
| `scripts/prepare_evidence_pilot.py` | 从旧 reserve 集未使用部分冻结新研究 MedQA 开发样本。 |
| `scripts/prepare_hard_pilot.py` | 筛选困难开发题、去重和拆分模型输入/评估标签。 |
| `scripts/preview_hard_retrieval.py` | 离线比较原始查询与内容词查询的检索结果。 |
| `scripts/resume_evidence_debug.py` | 显式调试续跑与成功响应复用；不同预算调试不作正式对照。 |
| `scripts/run_difficulty_probe.py` | 固定单 Agent 闭卷难度探测；不是 MDAgents 自适应流程。 |
| `scripts/run_evidence_pilot.py` | 证据协作实验入口；模型后端、断点记录、调用日志、预算与失败处理。 |
| `scripts/run_safety.py` | 进程锁、原子 JSON 写入、独立 attempt 目录与长路径处理。 |
| `scripts/score_difficulty_probe.py` | 难度探测分组评分、失败数和置信区间。 |
| `scripts/score_evidence_pilot.py` | 读取隔离标签，计算协作准确率、错误一致和前后转换。 |
| `scripts/search_corpus_gaps.py` | 为已知语料缺口搜索候选文章，保留查询与响应，不修改冻结语料。 |
| `scripts/test_consensus_mechanism.py` | 验证共识形成指标、失败分母和初始观点配对约束。 |
| `scripts/test_difficulty_probe.py` | 难度探测输入约束、选项、模型参数与截断处理测试。 |
| `scripts/test_evidence_audit.py` | 验证引用审计不接受错误引文、截断或缺失的初始专家观点。 |
| `scripts/test_evidence_pilot.py` | 引用、隔离、对照预算、锁、缓存、恢复及指标离线回归测试。 |

## 实验记录如何阅读

- `inputs.jsonl`：模型可见题目；`labels.jsonl`：仅评分读取的答案。
- `config.json`、manifest、源码快照：当时参数、版本和来源；包含旧路径属于正常历史记录。
- `cases/<题目ID>/attempts/<尝试ID>/`：隔离调用尝试；结果、检查点与轨迹用于追溯失败和计费。
- `evaluation`、`summary`、`review`：评分与复核；不能脱离协议当作最终论文结果。
- 文献 XML、检索响应、`corpus.jsonl`：RAG 的原始资料和处理产物，已保留。
- MedQA 首批结果为 91/100；第二批保存答案为 97/100，但有日志完整性问题，不作为可靠过程/成本证据。
- 困难探测为 MedQA 30/30、MedXpertQA 16/30（12 个标签不符、2 个截断）；还不是错误共识对照实验。

## 整理边界与验证

删除了 7 份根目录论文原文文本、无效 `apiSDK.py` 和 PPT 临时构建/渲染缓存。保留笔记、分享稿和实验 RAG 文献。详细删除哈希和移动记录见 `cleanup-manifest.json`；清单不能恢复已删除内容。

共享 `.env`、原始数据和新环境没有移动。活动代码路径已更新；历史实验文件没有批量替换路径。旧冻结运行的源码/配置可能不接受当前代码续跑，新实验请使用新目录。

2026-09-24 整理时，当前研究 20 项及旧复现 4 项离线测试通过，旧环境健康检查和 CLI 帮助通过；整理本身没有模型 API 调用。后续模型实验与测试更新见 `hard-collaboration-check.md`。PPT 构建源码仅调整输出目录，没有重新构建演示稿。

更新目录清单：从项目根目录执行 `runs/evidence_dependency/.venv/Scripts/python.exe scripts/build_file_index.py`。
