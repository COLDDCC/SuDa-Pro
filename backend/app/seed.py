"""Seed the database with baseline data: JP warehouse, logistics lines, a notice.

Run with: python -m app.seed
"""
from .database import Base, engine, SessionLocal
from . import models


def run():
    Base.metadata.create_all(bind=engine)
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
        if db.query(models.Line).count() == 0:
            db.add_all([
                models.Line(shop_id=1, name="标准海运专线", description="经济实惠，适合大件不急用",
                            price_per_kg=38, min_weight=0.5, days_min=15, days_max=25),
                models.Line(shop_id=1, name="标准空运专线", description="性价比均衡，适合日常转运",
                            price_per_kg=68, min_weight=0.1, days_min=7, days_max=12),
                models.Line(shop_id=1, name="极速空运专线", description="最快到手，适合急件",
                            price_per_kg=98, min_weight=0.1, days_min=3, days_max=6),
            ])
        if db.query(models.Notice).count() == 0:
            db.add(models.Notice(
                shop_id=1,
                title="欢迎使用 XX转运Pro",
                content="把包裹寄到我们的日本仓地址，预报后我们帮你集运、清关、寄回国内。有问题请联系客服。",
            ))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run()
