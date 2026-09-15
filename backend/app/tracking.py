"""从一段文字里猜快递单号——不接任何第三方 OCR 服务，纯正则。

用户把快递单上的文字拍照后用手机自带的"提取文字"功能复制粘贴进来，或者直接
照着抄，这个模块负责从这坨文字里挑出看起来像单号的那一串，减少手动输入。
不保证 100% 准，所以调用方永远要让用户能看到识别结果再确认/编辑。
"""
import re

# 按优先级排序：越靠前的格式越"像"快递单号，命中就优先用它。
_PATTERNS = [
    # EMS/万国邮联格式，例如 EE123456789JP、RR987654321CN
    re.compile(r'\b[A-Za-z]{2}\d{9}[A-Za-z]{2}\b'),
    # 日本国内快递常见的三段分组数字，例如 1234-5678-9012 / 1234 5678 9012
    re.compile(r'\b\d{4}[-\s]\d{4}[-\s]\d{4}\b'),
    # 兜底：一长串 10~14 位数字（不少快递公司单号就是纯数字）
    re.compile(r'\b\d{10,14}\b'),
]


def guess_tracking_numbers(text: str):
    """返回文本里所有候选单号，按上面模式的优先级排序，去重但保留顺序。"""
    if not text:
        return []
    seen = set()
    candidates = []
    for pattern in _PATTERNS:
        for m in pattern.finditer(text):
            raw = m.group(0)
            normalized = re.sub(r'[-\s]', '', raw).upper()
            if normalized not in seen:
                seen.add(normalized)
                candidates.append(normalized)
    return candidates
