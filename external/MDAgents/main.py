import os
import json
import random
import argparse #因该是专门用来设置命令行参数的库
from datetime import datetime
from tqdm import tqdm #进度条库
from termcolor import cprint
from pptree import print_tree
from prettytable import PrettyTable
# utils.py 放置所有“专家、团队、难度路由”的核心逻辑；main.py 只负责串起流程。
from utils import (
    Agent, Group, parse_hierarchy, parse_group_info, setup_model,
    load_data, create_question, determine_difficulty,
    process_basic_query, process_intermediate_query, process_advanced_query,
    configure_trace_log, trace_event
)

# 命令行参数：例如 `python main.py --dataset medqa --difficulty adaptive`。
parser = argparse.ArgumentParser()
parser.add_argument('--dataset', type=str, default='medqa')
parser.add_argument('--model', type=str, default='gpt-4o-mini')
parser.add_argument('--difficulty', type=str, default='adaptive')
parser.add_argument('--num_samples', type=int, default=100)
parser.add_argument('--verbose', action='store_true', help='Print model-call progress while writing a detailed JSONL trace.')
args = parser.parse_args()

# 先创建输出目录和追踪日志，保证每次模型调用都有可审计记录。
path = os.path.join(os.getcwd(), 'output')
os.makedirs(path, exist_ok=True)
run_timestamp = datetime.now().strftime('%d-%H%M%S')
short_result_path = os.path.join(path, f'{args.model}_{args.dataset}_{args.difficulty}.json')
run_name = f'{args.model}_{args.dataset}_{args.difficulty}_{run_timestamp}'
full_result_path = os.path.join(path, f'{run_name}.json')
trace_path = os.path.join(path, f'{run_name}_trace.jsonl')
configure_trace_log(trace_path, verbose=args.verbose)
trace_event(
    'run_started',
    arguments=vars(args),
    short_result_file=os.path.abspath(short_result_path),
    full_result_file=os.path.abspath(full_result_path),
)

# 启动时先验证模型配置，再一次性读取测试题和训练示例题。
# client 在当前文件中未直接使用；实际请求由 utils.py 内的 Agent 发出。
model, client = setup_model(args.model)
test_qa, examplers = load_data(args.dataset)

agent_emoji = ['\U0001F468\u200D\u2695\uFE0F', '\U0001F468\U0001F3FB\u200D\u2695\uFE0F', '\U0001F469\U0001F3FC\u200D\u2695\uFE0F', '\U0001F469\U0001F3FB\u200D\u2695\uFE0F', '\U0001f9d1\u200D\u2695\uFE0F', '\U0001f9d1\U0001f3ff\u200D\u2695\uFE0F', '\U0001f468\U0001f3ff\u200D\u2695\uFE0F', '\U0001f468\U0001f3fd\u200D\u2695\uFE0F', '\U0001f9d1\U0001f3fd\u200D\u2695\uFE0F', '\U0001F468\U0001F3FD\u200D\u2695\uFE0F']
random.shuffle(agent_emoji)

# 每道题的完整输入、标准答案、模型回答和所选协作模式都会收集在这里。
results = []
for no, sample in enumerate(tqdm(test_qa)):
    if no == args.num_samples:
        break
    
    print(f"\n[INFO] no: {no}")
    total_api_calls = 0

    # 将 JSON 样本转为模型可读的题目文本；当前代码未实际使用 img_path。
    question, img_path = create_question(sample, args.dataset)
    # adaptive 时由 LLM 自行判定复杂度；也可以用参数强制指定 basic/intermediate/advanced。
    difficulty = determine_difficulty(question, args.difficulty, args.model)

    print(f"difficulty: {difficulty}")

    # 根据难度选择协作规模：单专家 → 多专家辩论 → 多学科团队。
    if difficulty == 'basic':
        final_decision = process_basic_query(question, examplers, args.model, args)
    elif difficulty == 'intermediate':
        final_decision = process_intermediate_query(question, examplers, args.model, args)
    elif difficulty == 'advanced':
        final_decision = process_advanced_query(question, args.model, args)

    # 当前输出格式只为 MedQA 明确定义了标准答案和选项字段。
    if args.dataset == 'medqa':
        results.append({
            'question': question,
            'label': sample['answer_idx'],
            'answer': sample['answer'],
            'options': sample['options'],
            'response': final_decision,
            'difficulty': difficulty
        })

# 运行目录为 external/MDAgents 时，结果与逐次调用日志均写到 output/ 下。
with open(short_result_path, 'w', encoding='utf-8') as file:
    json.dump(results, file, indent=4)
with open(full_result_path, 'w', encoding='utf-8') as file:
    json.dump(results, file, indent=4)
trace_event(
    'run_finished',
    samples_completed=len(results),
    short_result_file=os.path.abspath(short_result_path),
    full_result_file=os.path.abspath(full_result_path),
)
print(f'[INFO] result: {short_result_path}')
print(f'[INFO] full result: {full_result_path}')
print(f'[INFO] trace: {trace_path}')
