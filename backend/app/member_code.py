"""会员代码 —— 用户要手写在日本快递单上，仓库靠它认出包裹是谁的。

格式 SD + 4 位数字（SD0001）。之前用的是 8 位十六进制（CB920F23），手写时
0/O、8/B 极易混淆，仓库认错货的代价比这点代码高得多。

直接拿会员 id 补零：天然唯一、不用额外的计数器表、也不会并发撞号。
超过 9999 个会员后自然变成 5 位（SD10000），不会出错。
"""
PREFIX = "SD"
MIN_DIGITS = 4


def format_member_code(member_id: int) -> str:
    return f"{PREFIX}{member_id:0{MIN_DIGITS}d}"


def assign_member_code(db, member):
    """会员建好拿到 id 之后调用。"""
    member.cn_code = format_member_code(member.id)
    db.commit()
    db.refresh(member)
    return member.cn_code
