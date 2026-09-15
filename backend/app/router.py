"""Method-name dispatch table, mirroring the competitor's `api.php?method=Module.action`
design mentioned in the project plan: one HTTP entrypoint, method routed by name.
"""
from .modules import login, member, address, order, config, shop

_MODULES = {
    "System.Login": login,
    "System.Member": member,
    "System.Address": address,
    "System.Order": order,
    "System.Config": config,
    "System.Shop": shop,
}

# Methods that don't require a logged-in member.
PUBLIC_METHODS = {
    "System.Login.wechatLogin",
    "System.Login.devLogin",
    "System.Config.webSite",
    "System.Config.copyRight",
    "System.Config.defaultImages",
    "System.Config.getCurrentTime",
    "System.Config.noticeConfig",
    "System.Config.getVertification",
    "System.Address.province",
    "System.Address.city",
    "System.Address.district",
    "System.Address.lineList",
    "System.Address.lineInfo",
    "System.Address.estimateFee",
    "System.Address.noticeList",
    "System.Address.noticeInfo",
    "System.Shop.ShopListByConditions",
    "System.Shop.getShopMessage",
    # 仓库/客服操作：不挂在会员 token 上，改由 staff_key 校验（见 order.py 的 _require_staff）
    "System.Order.markInbound",
    "System.Order.markShipped",
    "System.Order.addTrack",
    "System.Order.staffPendingPackages",
    "System.Order.staffOrders",
}


class MethodNotFound(Exception):
    pass


def resolve(method: str):
    """method like 'System.Order.addforecast' -> (module, func, requires_auth)"""
    parts = method.rsplit(".", 1)
    if len(parts) != 2:
        raise MethodNotFound(method)
    module_path, func_name = parts
    module = _MODULES.get(module_path)
    if module is None:
        raise MethodNotFound(method)
    func = getattr(module, func_name, None)
    if func is None or func_name.startswith("_"):
        raise MethodNotFound(method)
    # 只允许调用这个模块自己定义的函数，防止 getattr 意外命中模块里 import
    # 进来的类/子模块（比如 order.py 里的 Decimal、models）。
    if getattr(func, "__module__", None) != module.__name__:
        raise MethodNotFound(method)
    requires_auth = method not in PUBLIC_METHODS
    return func, requires_auth
