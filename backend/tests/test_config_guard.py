"""生产配置自检。

带着默认 JWT_SECRET 上线 = 任何人都能签出任意用户的 token；
WX 凭证没配齐 = devLogin 还开着 = 填个用户名就能登录。
这两件事在 dev 无所谓，在生产必须让进程直接起不来。
"""
import pytest

from app import config


@pytest.fixture
def prod(monkeypatch):
    """把 config 模块临时切到"生产 + 全部配置合格"，各用例再单独打坏一项。"""
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "JWT_SECRET", "a-real-long-random-secret-value")
    monkeypatch.setattr(config, "STAFF_KEY", "a-real-long-random-staff-key")
    monkeypatch.setattr(config, "WX_APPID", "wx1234567890abcdef")
    monkeypatch.setattr(config, "WX_SECRET", "0123456789abcdef0123456789abcdef")
    return monkeypatch


def test_fully_configured_production_passes(prod):
    assert config.production_problems() == []
    config.check_production_config()   # 不抛异常


def test_dev_never_blocks_startup(monkeypatch):
    """本地联调用的就是默认值，不该被拦。"""
    monkeypatch.setattr(config, "IS_PRODUCTION", False)
    monkeypatch.setattr(config, "JWT_SECRET", config.DEFAULT_JWT_SECRET)
    monkeypatch.setattr(config, "STAFF_KEY", "")
    monkeypatch.setattr(config, "WX_APPID", "")
    monkeypatch.setattr(config, "WX_SECRET", "")
    assert config.production_problems() == []
    config.check_production_config()


def test_default_jwt_secret_is_rejected(prod):
    prod.setattr(config, "JWT_SECRET", config.DEFAULT_JWT_SECRET)
    problems = config.production_problems()
    assert len(problems) == 1 and "JWT_SECRET" in problems[0]
    with pytest.raises(config.ConfigError):
        config.check_production_config()


def test_short_jwt_secret_is_rejected(prod):
    prod.setattr(config, "JWT_SECRET", "short")
    assert any("JWT_SECRET" in p for p in config.production_problems())


def test_missing_staff_key_is_rejected(prod):
    prod.setattr(config, "STAFF_KEY", "")
    assert any("STAFF_KEY" in p for p in config.production_problems())


def test_short_staff_key_is_rejected(prod):
    prod.setattr(config, "STAFF_KEY", "abc123")
    assert any("STAFF_KEY" in p for p in config.production_problems())


@pytest.mark.parametrize("appid,secret", [("", ""), ("wxabc", ""), ("", "secret")])
def test_incomplete_wechat_credentials_are_rejected(prod, appid, secret):
    prod.setattr(config, "WX_APPID", appid)
    prod.setattr(config, "WX_SECRET", secret)
    assert any("devLogin" in p for p in config.production_problems())


def test_error_message_lists_every_problem_and_how_to_fix(prod):
    """报错要一次说全，别让人改一条重启一次。"""
    prod.setattr(config, "JWT_SECRET", config.DEFAULT_JWT_SECRET)
    prod.setattr(config, "STAFF_KEY", "")
    prod.setattr(config, "WX_APPID", "")
    prod.setattr(config, "WX_SECRET", "")
    assert len(config.production_problems()) == 3
    with pytest.raises(config.ConfigError) as exc:
        config.check_production_config()
    msg = str(exc.value)
    for name in ("JWT_SECRET", "STAFF_KEY", "WX_APPID"):
        assert name in msg
    assert "secrets.token_urlsafe" in msg, "报错里得直接给出生成密钥的命令"
    assert "APP_ENV" in msg, "报错里得说明本地怎么跳过"
