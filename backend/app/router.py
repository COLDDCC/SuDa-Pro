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
    requires_auth = method not in PUBLIC_METHODS
    return func, requires_auth
