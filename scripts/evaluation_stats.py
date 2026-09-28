"""Shared offline evaluation statistics."""
import math

def wilson(correct, count):
    if not count:
        return None
    z = 1.959963984540054
    p = correct / count
    denominator = 1 + z*z/count
    center = (p + z*z/(2*count)) / denominator
    half = z*math.sqrt(p*(1-p)/count + z*z/(4*count*count))/denominator
    return [center-half, center+half]
