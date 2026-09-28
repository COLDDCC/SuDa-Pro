"""启动时给已有的数据库补上新加的列。

项目没用 Alembic，create_all() 只会建新表、不会给老表加列；直接用老的 suda.db
启动新代码，查询一带上新列就会报 no such column。这里对比模型和数据库里实际的列，
缺哪列就 ALTER TABLE ADD COLUMN 补哪列，只加不删，重复执行没有副作用。
"""
from sqlalchemy import inspect, text

from .database import Base, engine


def _default_sql(column):
    default = column.default
    if default is None or not default.is_scalar:
        return ""
    value = default.arg
    if isinstance(value, bool):
        return f" DEFAULT {int(value)}"
    if isinstance(value, (int, float)):
        return f" DEFAULT {value}"
    if isinstance(value, str):
        return " DEFAULT '" + value.replace("'", "''") + "'"
    return ""


def run():
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # 新表交给 create_all
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in have:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{_default_sql(column)}'
                ))
        # 老订单只有 total_fee，拆出来的运费/囤货费补上，免得页面显示空
        conn.execute(text("UPDATE orders SET shipping_fee = total_fee WHERE shipping_fee IS NULL"))
        conn.execute(text("UPDATE orders SET storage_fee = 0 WHERE storage_fee IS NULL"))
        conn.execute(text("UPDATE orders SET paid = 0 WHERE paid IS NULL"))
