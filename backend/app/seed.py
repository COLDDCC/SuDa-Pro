"""Seed the database with baseline data: JP warehouse, logistics lines, a notice.

Run with: python -m app.seed
"""
from .database import Base, engine, SessionLocal
from . import models, migrate


def run():
    Base.metadata.create_all(bind=engine)
    migrate.run()
    db = SessionLocal()
    try:
        if db.query(models.Warehouse).count() == 0:
            db.add(models.Warehouse(
                shop_id=1,
                name="东京集运仓",
                country="日本",
                postal_code="140-0002",
                address="東京都品川区東品川2-2-20 天王洲パークサイドビル 3F XX转运（收件人后请务必备注您的会员代码）",
                contact="+81-3-0000-0000",
                note="收货后 1-2 个工作日内入库，入库后请在小程序内核对包裹信息。",
            ))
        _sync_lines(db)
        if db.query(models.Notice).count() == 0:
            db.add(models.Notice(
                shop_id=1,
                title="欢迎使用 XX转运Pro",
                content="把包裹寄到我们的日本仓地址，预报后我们帮你集运、清关、寄回国内。有问题请联系客服。",
            ))
        db.commit()
    finally:
        db.close()


# 国际物流包清服务的两条线路（价格来自运营给的《国际物流费用说明》）。
# 大连港清关，一周五个航班（周二至周六）。
LINES = [
    dict(name="精致小", description="适合个人日本直邮：单个包裹价值 400 元以内、重量 0.6kg 以内。"
                                    "首重 0.6kg 45 元，续重 35 元/0.5kg",
         first_weight=0.6, first_price=45, step_weight=0.5, step_price=35, max_value=400,
         days_min=5, days_max=10),
    dict(name="无忧草", description="适合价值 400-1000 元、重量超过 0.6kg 的包裹，直邮。"
                                    "80 元/kg，续重 8 元/0.1kg",
         first_weight=1, first_price=80, step_weight=0.1, step_price=8, max_value=1000,
         days_min=5, days_max=10),
]
# 早期版本种进去的三条示例线路，换成上面两条后停用（老订单还引用着，所以不删）
_OLD_SAMPLE_LINES = ("标准海运专线", "标准空运专线", "极速空运专线")


def _sync_lines(db):
    """按名字补齐 LINES 里的线路。已存在的不覆盖——上线后在数据库里改过的价格不会被重启冲掉。"""
    for spec in LINES:
        if db.query(models.Line).filter_by(name=spec["name"]).first() is None:
            db.add(models.Line(shop_id=1, price_per_kg=0, **spec))
    db.query(models.Line).filter(models.Line.name.in_(_OLD_SAMPLE_LINES)).update(
        {"is_active": False}, synchronize_session=False)


if __name__ == "__main__":
    run()
