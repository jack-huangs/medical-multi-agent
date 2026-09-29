# 文件用途：共享 Wilson 比例置信区间计算，避免新研究依赖旧运行器。
"""Shared offline evaluation statistics."""
import math

# 估计正确率的 Wilson 置信区间；样本少时，即使全对，区间也不会只剩 100%。
def wilson(correct, count):
    if not count:
        return None
    z = 1.959963984540054
    p = correct / count
    denominator = 1 + z*z/count
    center = (p + z*z/(2*count)) / denominator
    half = z*math.sqrt(p*(1-p)/count + z*z/(4*count*count))/denominator
    return [center-half, center+half]
