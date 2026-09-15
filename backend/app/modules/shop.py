"""System.Shop.* — 多店铺（MVP 阶段先固定单店铺，留出接口位）"""

_DEFAULT_SHOP = {"id": 1, "name": "XX转运Pro 总仓"}


def ShopListByConditions(db, member, params):
    return {"total": 1, "list": [_DEFAULT_SHOP]}


def updateShopId(db, member, params):
    return {"shop_id": params.get("id", 1)}


def getShopMessage(db, member, params):
    return _DEFAULT_SHOP
