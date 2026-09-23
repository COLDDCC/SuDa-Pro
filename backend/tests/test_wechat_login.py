"""微信登录：连不上微信、微信报错时，用户得看到看得懂的话。

这条路没法在测试里真连微信（需要真实的 wx.login code），所以把 httpx 那一层
换掉，重点验证各种失败情形不会变成一句"服务器内部错误"——那句话对用户和运维
都等于没说。
"""
import httpx
import pytest

from app.modules import login as login_mod


@pytest.fixture
def wx(monkeypatch):
    """假装配好了微信凭证，并接管对微信服务器的请求。"""
    monkeypatch.setattr(login_mod, "WX_APPID", "wx48aef7da6d3d6b6a")
    monkeypatch.setattr(login_mod, "WX_SECRET", "x" * 32)

    def _set(payload=None, exc=None, body=None, status=200):
        def fake_get(url, params=None, timeout=None):
            if exc:
                raise exc
            return httpx.Response(status, json=payload) if payload is not None \
                else httpx.Response(status, text=body or "")
        monkeypatch.setattr(login_mod.httpx, "get", fake_get)
    return _set


def test_successful_login_creates_a_member_with_a_code(api, wx):
    wx({"openid": "o_test_openid_001", "session_key": "k"})
    data = api.ok("System.Login.wechatLogin", {"code": "any-code"})
    assert data["token"]
    assert api.ok("System.Member.memberInfo", {}, data["token"])["cn_code"].startswith("SD")


def test_logging_in_twice_reuses_the_same_member(api, wx):
    """同一个微信号第二次登录不能变成一个新账号——包裹和订单就找不到了。"""
    wx({"openid": "o_test_openid_002"})
    first = api.ok("System.Login.wechatLogin", {"code": "c1"})
    second = api.ok("System.Login.wechatLogin", {"code": "c2"})
    assert first["member_id"] == second["member_id"]


def test_missing_code_is_rejected(api, wx):
    wx({"openid": "o_x"})
    api.fail("System.Login.wechatLogin", {})


def test_cannot_reach_wechat_is_not_a_500(api, wx):
    """服务器没外网 / DNS 挂了 / 微信抽风。用户得知道是网络问题，不是"内部错误"。"""
    wx(exc=httpx.ConnectError("connection refused"))
    resp = api.fail("System.Login.wechatLogin", {"code": "c"})
    assert resp["code"] != 500
    assert "微信服务器" in resp["msg"]


def test_proxy_error_is_not_a_500(api, wx):
    wx(exc=httpx.ProxyError("403 Forbidden"))
    assert api.fail("System.Login.wechatLogin", {"code": "c"})["code"] != 500


def test_timeout_is_not_a_500(api, wx):
    wx(exc=httpx.ReadTimeout("timed out"))
    assert api.fail("System.Login.wechatLogin", {"code": "c"})["code"] != 500


def test_non_json_response_is_not_a_500(api, wx):
    """微信前面挡了个网关返回 HTML 错误页的情况。"""
    wx(body="<html>502 Bad Gateway</html>")
    assert api.fail("System.Login.wechatLogin", {"code": "c"})["code"] != 500


@pytest.mark.parametrize("errcode,expect", [
    (40029, "重进"),        # code 失效 —— 用户自己能解决
    (45011, "频繁"),        # 调用太频繁 —— 等一下
    (40013, "AppID"),       # 配置错了 —— 运维要看的
    (40125, "AppSecret"),
])
def test_wechat_errors_are_translated_into_actionable_chinese(api, wx, errcode, expect):
    """把官方的 "invalid code" 原样抛给用户等于没说。"""
    wx({"errcode": errcode, "errmsg": "some english message"})
    resp = api.fail("System.Login.wechatLogin", {"code": "c"})
    assert resp["code"] != 500
    assert expect in resp["msg"], f"errcode {errcode} 的提示是：{resp['msg']}"


def test_unknown_error_code_still_says_something_useful(api, wx):
    wx({"errcode": 99999, "errmsg": "brand new error"})
    resp = api.fail("System.Login.wechatLogin", {"code": "c"})
    assert resp["code"] != 500
    assert "99999" in resp["msg"], "没见过的错误码要把码带出来，不然没法排查"


def test_nickname_and_avatar_are_saved_when_provided(api, wx):
    wx({"openid": "o_test_openid_003"})
    token = api.ok("System.Login.wechatLogin",
                   {"code": "c", "nickname": "阿花", "avatar": "https://x/a.png"})["token"]
    me = api.ok("System.Member.memberInfo", {}, token)
    assert me["nickname"] == "阿花"
