from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile
from xml.etree.ElementTree import Element, SubElement, tostring


OUTPUT = Path(__file__).resolve().parents[1] / "低难度题目处理流程.xmind"
CONTENT_NS = "urn:xmind:xmap:xmlns:content:2.0"
MANIFEST_NS = "urn:xmind:xmap:xmlns:manifest:1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"


def topic(parent, title, children=None):
    node = SubElement(parent, f"{{{CONTENT_NS}}}topic", {"id": f"topic-{uuid4()}"})
    SubElement(node, f"{{{CONTENT_NS}}}title").text = title
    if children:
        children_node = SubElement(node, f"{{{CONTENT_NS}}}children")
        topics_node = SubElement(children_node, f"{{{CONTENT_NS}}}topics", {"type": "attached"})
        for child_title, child_children in children:
            topic(topics_node, child_title, child_children)
    return node


def build_content():
    root = Element(
        f"{{{CONTENT_NS}}}xmap-content",
        {
            f"{{{XML_NS}}}lang": "zh-CN",
            "version": "2.0",
        },
    )
    sheet = SubElement(root, f"{{{CONTENT_NS}}}sheet", {"id": f"sheet-{uuid4()}"})
    root_topic = SubElement(sheet, f"{{{CONTENT_NS}}}topic", {"id": f"root-{uuid4()}"})
    SubElement(root_topic, f"{{{CONTENT_NS}}}title").text = "低难度题目处理流程（Basic）"

    children = SubElement(root_topic, f"{{{CONTENT_NS}}}children")
    attached = SubElement(children, f"{{{CONTENT_NS}}}topics", {"type": "attached"})

    branches = [
        (
            "1. 输入与低难度路由",
            [
                ("main.py 读取一条测试题、训练示例和命令行参数", []),
                (
                    "create_question(sample, dataset)：拼接题目和选项；MedQA 选项随机打乱；不调用模型",
                    [],
                ),
                ("若 --difficulty basic：直接进入本流程", []),
                (
                    "若 --difficulty adaptive：先运行分诊 Agent",
                    [
                        (
                            "分诊 Agent System Prompt：You are a medical expert who conducts initial assessment and your job is to decide the difficulty/complexity of the medical query.",
                            [],
                        ),
                        (
                            "分诊判断 Prompt：Now, given the medical query as below, you need to decide the difficulty/complexity of it: {question}. Please indicate: 1) basic 2) intermediate 3) advanced.",
                            [],
                        ),
                        ("返回 basic 后进入低难度流程", []),
                    ],
                ),
            ],
        ),
        (
            "2. 创建示例理由 Agent",
            [
                ("创建 Agent；此时只初始化对话历史，不调用模型", []),
                ("System Prompt：You are a helpful medical agent.", []),
                ("随机打乱 train.jsonl 示例，抽取前 5 条；题目、选项和标准答案来自数据集", []),
                (
                    "循环处理 5 条示例",
                    [
                        ("构造示例题：题目 + 随机排列后的选项", []),
                        ("构造已有答案：Answer: ({answer_idx}) {answer}", []),
                        (
                            "实时模型调用 Prompt：You are a helpful medical agent. Below is an example of medical knowledge question and answer. After reviewing the below medical question and answering, can you provide 1-2 sentences of reason that support the answer as you didn't know the answer ahead? Question: {exampler_question} Answer: {exampler_answer}",
                            [],
                        ),
                        ("保存：示例题 + 数据集标准答案 + 模型生成的 1-2 句理由", []),
                    ],
                ),
                ("得到 new_examplers：5 个 Few-shot 示例", []),
            ],
        ),
        (
            "3. 创建真正的答题 Agent",
            [
                (
                    "System Prompt：You are a helpful assistant that answers multiple choice questions about medical knowledge.",
                    [],
                ),
                (
                    "Agent 初始化时把 5 个示例写入 messages：user=示例题；assistant=正确答案 + 示例理由",
                    [],
                ),
                (
                    "额外角色确认 Prompt：You are a helpful assistant that answers multiple choice questions about medical knowledge.",
                    [
                        ("该调用主要是再次确认角色；会额外消耗 1 次 API 调用", []),
                    ],
                ),
            ],
        ),
        (
            "4. 回答当前新问题",
            [
                (
                    "最终模型调用：single_agent.temp_responses(...)",
                    [
                        (
                            "Final Prompt：The following are multiple choice questions (with answers) about medical knowledge. Let's think step by step. **Question:** {question} Answer:",
                            [],
                        ),
                        ("temperature = 0.0：降低随机性，生成当前新问题的答案", []),
                        ("这里生成的是新问题答案，不是示例理由", []),
                    ],
                ),
                ("返回：{0.0: 当前新问题的模型回答}", []),
            ],
        ),
        (
            "5. 结果保存与调用成本",
            [
                ("main.py 保存 question、label、answer、options、response、difficulty", []),
                ("强制 basic + MedQA：约 7 次 API 调用（5 次示例理由 + 1 次角色确认 + 1 次新题回答）", []),
                ("adaptive + basic：约 9 次 API 调用（额外 2 次难度判断）", []),
                ("关键关系：示例题和答案预先准备；示例理由实时生成；新题答案最后生成", []),
            ],
        ),
    ]

    for branch_title, branch_children in branches:
        topic(attached, branch_title, branch_children)
    return tostring(root, encoding="utf-8", xml_declaration=True)


def build_manifest():
    root = Element(f"{{{MANIFEST_NS}}}manifest")
    for full_path, media_type in [
        ("content.xml", "text/xml"),
        ("styles.xml", "text/xml"),
        ("meta.xml", "text/xml"),
        ("META-INF/manifest.xml", "text/xml"),
    ]:
        SubElement(root, f"{{{MANIFEST_NS}}}file-entry", {"full-path": full_path, "media-type": media_type})
    return tostring(root, encoding="utf-8", xml_declaration=True)


def main():
    styles = b'''<?xml version="1.0" encoding="UTF-8"?><xmap-styles xmlns="urn:xmind:xmap:xmlns:style:2.0"/>'''
    meta = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<meta xmlns="urn:xmind:xmap:xmlns:meta:2.0" version="2.0">'
        f'<Author>Codex</Author><Created>{datetime.now(timezone.utc).isoformat()}</Created>'
        '</meta>'
    ).encode("utf-8")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as archive:
        # XMind 8 recognizes this MIME marker at the beginning of the package.
        archive.writestr("mimetype", b"application/xmind", compress_type=ZIP_STORED)
        archive.writestr("content.xml", build_content())
        archive.writestr("styles.xml", styles)
        archive.writestr("meta.xml", meta)
        archive.writestr("META-INF/manifest.xml", build_manifest())
    print(OUTPUT)


if __name__ == "__main__":
    main()
