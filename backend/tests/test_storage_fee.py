"""囤货费：入库后 30 天免费，超出按 1 元/天/包裹。

测试要能让包裹"躺很久"，所以直接改库里的 inbound_at，而不是等 30 天。
"""
import datetime
from decimal import Decimal

import pytest

from app import business, models
from app.database import SessionLocal


@pytest.fixture
def age_package():
    """把包裹的入库时间往前拨 N 天，模拟它在仓库躺了很久。"""
    def _age(package_id, days):
        db = SessionLocal()
        try:
            p = db.query(models.Package).filter_by(id=package_id).first()
            p.inbound_at = models.now() - datetime.timedelta(days=days)
            db.commit()
        finally:
            db.close()
    return _age


def _fee_of(order, fee_type):
    rows = [f for f in order["fees"] if f["fee_type"] == fee_type]
    return Decimal(rows[0]["amount"]) if rows else None


def test_within_the_free_window_costs_nothing(api, token, address_id, line_id,
                                              make_package, age_package):
    pkg = make_package(inbound=True)
    age_package(pkg["id"], business.FREE_STORAGE_DAYS - 1)

    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    assert _fee_of(order, "storage") is None, "还在免费期内就收了囤货费"


def test_exactly_at_the_boundary_is_still_free(api, token, address_id, line_id,
                                               make_package, age_package):
    """第 30 天是免费的最后一天，不能提前一天开始收。"""
    pkg = make_package(inbound=True)
    age_package(pkg["id"], business.FREE_STORAGE_DAYS)

    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    assert _fee_of(order, "storage") is None


def test_overdue_package_is_charged_per_day(api, token, address_id, line_id,
                                            make_package, age_package):
    pkg = make_package(inbound=True)
    age_package(pkg["id"], business.FREE_STORAGE_DAYS + 7)

    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    assert _fee_of(order, "storage") == Decimal(business.STORAGE_FEE_PER_DAY) * 7


def test_each_package_is_counted_on_its_own_clock(api, token, address_id, line_id,
                                                  make_package, age_package):
    """合箱时有的躺得久有的刚到，不能一刀切按最久的那个算。"""
    old = make_package(inbound=True)
    fresh = make_package(inbound=True)
    age_package(old["id"], business.FREE_STORAGE_DAYS + 10)
    age_package(fresh["id"], 1)

    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id,
        "package_ids": [old["id"], fresh["id"]],
    }, token)
    assert _fee_of(order, "storage") == Decimal(business.STORAGE_FEE_PER_DAY) * 10


def test_storage_fee_is_a_separate_visible_line(api, token, address_id, line_id,
                                                make_package, age_package):
    """用户得看懂这笔钱是怎么来的，不然就是客服工单。"""
    pkg = make_package(inbound=True)
    age_package(pkg["id"], business.FREE_STORAGE_DAYS + 3)

    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    row = [f for f in order["fees"] if f["fee_type"] == "storage"][0]
    assert str(business.FREE_STORAGE_DAYS) in row["name"], "得写明免费期是多少天"
    assert "3 天" in row["detail"], "得写明超期几天"
    assert Decimal(order["total_fee"]) == sum(Decimal(f["amount"]) for f in order["fees"])


def test_preview_shows_the_storage_fee_before_ordering(api, token, line_id,
                                                       make_package, age_package):
    """下单前就得看到，不能提交完才发现多了一笔。"""
    pkg = make_package(inbound=True)
    age_package(pkg["id"], business.FREE_STORAGE_DAYS + 5)

    preview = api.ok("System.Order.previewFee", {
        "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    assert _fee_of(preview, "storage") == Decimal(business.STORAGE_FEE_PER_DAY) * 5
