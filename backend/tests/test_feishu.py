"""飞书推送。

最要紧的一条：飞书挂了不能让用户下不了单。推送是尽力而为的旁路。
"""
import json

import pytest

from app import feishu


@pytest.fixture
def captured(monkeypatch):
    """截下要发给飞书的 payload，不真的发网络请求。"""
    sent = []
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setattr(feishu, "_post", lambda payload: sent.append(payload) or {"code": 0})
    return sent


def test_disabled_when_no_webhook_configured(monkeypatch):
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK_URL", "")
    assert not feishu.enabled()


def test_notify_sends_a_card(captured):
    feishu._send("新订单", "blue", [("订单号", "SD001"), ("金额", "¥135.50")])
    assert len(captured) == 1
    card = captured[0]
    assert card["msg_type"] == "interactive"
    assert card["card"]["header"]["title"]["content"] == "新订单"
    body = json.dumps(card, ensure_ascii=False)
    assert "SD001" in body and "135.50" in body


def test_falls_back_to_plain_text_if_the_card_is_rejected(monkeypatch):
    """卡片格式被拒就退回纯文本，别因为排版问题把整条通知丢掉。"""
    sent = []

    def fake_post(payload):
        sent.append(payload)
        return {"code": 0} if payload["msg_type"] == "text" else {"code": 19001, "msg": "bad card"}

    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setattr(feishu, "_post", fake_post)

    feishu._send("新订单", "blue", [("订单号", "SD001")])
    assert [p["msg_type"] for p in sent] == ["interactive", "text"]
    assert "SD001" in sent[1]["content"]["text"]


def test_network_failure_never_raises(monkeypatch):
    """飞书挂了、网址填错了、网断了，都不能把异常抛回业务代码。"""
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK_URL", "https://example.invalid/hook")

    def boom(payload):
        raise OSError("connection refused")

    monkeypatch.setattr(feishu, "_post", boom)
    feishu._send("新订单", "blue", [("订单号", "SD001")])   # 不抛异常就算过


def test_signature_is_attached_when_a_secret_is_set(monkeypatch):
    sent = []
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setattr(feishu, "FEISHU_SIGN_SECRET", "my-secret")
    monkeypatch.setattr(feishu, "urllib", feishu.urllib)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())

        class R:
            def read(self_inner): return b'{"code":0}'
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): return False
        return R()

    monkeypatch.setattr(feishu.urllib.request, "urlopen", fake_urlopen)
    feishu._send("新订单", "blue", [("订单号", "SD001")])
    assert captured["body"]["sign"] and captured["body"]["timestamp"]


def test_ordering_still_works_when_feishu_is_broken(api, token, address_id, line_id,
                                                    make_package, monkeypatch):
    """这是这一整个模块最要紧的一条：推送失败绝不能挡住下单。"""
    monkeypatch.setattr(feishu, "FEISHU_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setattr(feishu, "_post", lambda payload: (_ for _ in ()).throw(OSError("down")))

    pkg = make_package(inbound=True)
    order = api.ok("System.Order.savePage", {
        "address_id": address_id, "line_id": line_id, "package_ids": [pkg["id"]],
    }, token)
    assert order["order_no"]
