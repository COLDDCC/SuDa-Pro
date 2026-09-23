"""把 business.py 里的业务数据同步进数据库。

每次启动都跑一遍，而且是"改了就更新"而不是"只在空库时写一次"——开测阶段价格
和地址会反复调，改完重启就生效比让人去改数据库现实得多。

已经下过的订单不受影响：订单金额在下单那一刻就冻结进 OrderFee 了，
改线路价格只影响之后的新订单。

Run with: python -m app.seed
"""
from decimal import Decimal

from .database import Base, engine, SessionLocal
from . import business, models


def _sync_warehouse(db):
    cfg = business.WAREHOUSE
    w = db.query(models.Warehouse).filter_by(shop_id=1).first()
    if w is None:
        w = models.Warehouse(shop_id=1)
        db.add(w)
    for field in ("name", "country", "postal_code", "address", "contact", "note"):
        setattr(w, field, cfg[field])
    w.is_active = True


def _sync_lines(db):
    """按名字匹配。business.py 里删掉的线路会被停用而不是删除——
    删了的话，引用它的历史订单会查不到线路名。"""
    wanted = {l["name"]: l for l in business.LINES}
    existing = {l.name: l for l in db.query(models.Line).filter_by(shop_id=1).all()}

    for name, cfg in wanted.items():
        line = existing.get(name)
        if line is None:
            line = models.Line(shop_id=1, name=name)
            db.add(line)
        line.description = cfg["description"]
        line.first_weight = Decimal(str(cfg["first_weight"]))
        line.first_fee = Decimal(str(cfg["first_fee"]))
        line.step_weight = Decimal(str(cfg["step_weight"]))
        line.step_fee = Decimal(str(cfg["step_fee"]))
        line.min_declared_value = Decimal(str(cfg["min_declared_value"]))
        line.max_declared_value = (
            None if cfg["max_declared_value"] is None
            else Decimal(str(cfg["max_declared_value"]))
        )
        line.days_min = cfg["days_min"]
        line.days_max = cfg["days_max"]
        line.is_active = True

    for name, line in existing.items():
        if name not in wanted:
            line.is_active = False


def _sync_notices(db):
    for cfg in business.NOTICES:
        n = db.query(models.Notice).filter_by(shop_id=1, title=cfg["title"]).first()
        if n is None:
            n = models.Notice(shop_id=1, title=cfg["title"])
            db.add(n)
        n.content = cfg["content"]


def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _sync_warehouse(db)
        _sync_lines(db)
        _sync_notices(db)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run()
    print("业务数据已同步（app/business.py -> 数据库）")
