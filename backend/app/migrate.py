"""给 SQLite 自动补上新增的列。

SQLAlchemy 的 create_all 只建缺失的**表**，不会给已有的表补**列**。试运营阶段
字段会一直加，每加一个就让人删库重来不现实（订单和用户数据就没了），所以启动时
自己比对一遍，缺什么补什么。

只做加列这一件事——加列是安全的（老数据拿默认值），改类型和删列不是，那种情况
得人工处理。
"""
import logging

from sqlalchemy import inspect, text

from .database import Base, engine

logger = logging.getLogger("suda")


def _sql_type(column):
    try:
        return column.type.compile(dialect=engine.dialect)
    except Exception:
        return "TEXT"


def _default_clause(column):
    """新列要给个默认值，否则已有的行会是 NULL，而代码可能不期望 NULL。"""
    default = getattr(column, "default", None)
    if default is None or getattr(default, "is_callable", False):
        return ""
    value = default.arg
    if isinstance(value, bool):
        return f" DEFAULT {1 if value else 0}"
    if isinstance(value, (int, float)):
        return f" DEFAULT {value}"
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f" DEFAULT '{escaped}'"
    return ""


def run():
    if not engine.url.get_backend_name().startswith("sqlite"):
        return                      # 换了 MySQL/Postgres 就该用正经的迁移工具

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    added = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue            # 整张表缺失的交给 create_all
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in have:
                    continue
                ddl = (f'ALTER TABLE "{table.name}" '
                       f'ADD COLUMN "{column.name}" {_sql_type(column)}'
                       f'{_default_clause(column)}')
                conn.execute(text(ddl))
                added.append(f"{table.name}.{column.name}")

    if added:
        logger.info("数据库补齐了这些列: %s", ", ".join(added))
    return added
