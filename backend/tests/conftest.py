"""测试环境准备。

关键点：app.config 是在 import 时一次性读环境变量的（order.py 还把 STAFF_KEY
直接 import 成了模块级常量），所以这些环境变量必须在任何 app.* 被导入之前设好，
放在 conftest 顶层就是为了这个 —— pytest 会先加载 conftest 再加载测试模块。
"""
import io
import itertools
import os
import tempfile
import uuid

_TMPDIR = tempfile.mkdtemp(prefix="suda-test-")

os.environ["APP_ENV"] = "dev"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMPDIR}/test.db"
os.environ["STAFF_KEY"] = "test-staff-key-0123456789"
os.environ["JWT_SECRET"] = "test-jwt-secret-0123456789"
# 配了微信凭证 devLogin 会自动禁用，测试要用 devLogin，所以确保它们是空的。
os.environ.pop("WX_APPID", None)
os.environ.pop("WX_SECRET", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

STAFF_KEY = os.environ["STAFF_KEY"]


class Api:
    """把 POST /api {method, params, token} 包一层，测试里读起来像在调函数。"""

    def __init__(self, client):
        self.client = client

    def raw(self, method, params=None, token=None):
        body = {"method": method, "params": params or {}}
        if token:
            body["token"] = token
        return self.client.post("/api", json=body).json()

    def ok(self, method, params=None, token=None):
        """断言调用成功并返回 data，失败时把后端的 msg 原样抛出来，好定位。"""
        resp = self.raw(method, params, token)
        assert resp["code"] == 0, f"{method} 失败: {resp['msg']}"
        return resp["data"]

    def fail(self, method, params=None, token=None):
        """断言调用失败并返回整个响应，方便继续断言 code/msg。"""
        resp = self.raw(method, params, token)
        assert resp["code"] != 0, f"{method} 本该失败，却成功了: {resp['data']}"
        return resp


@pytest.fixture(scope="session")
def api():
    with TestClient(app) as client:
        yield Api(client)


@pytest.fixture
def token(api):
    """每个测试一个全新会员，互不干扰（库是整个 session 共用的）。"""
    return api.ok("System.Login.devLogin", {"identifier": uuid.uuid4().hex})["token"]


@pytest.fixture
def other_token(api):
    """第二个会员，用来验证"看不到别人的数据"。"""
    return api.ok("System.Login.devLogin", {"identifier": uuid.uuid4().hex})["token"]


@pytest.fixture(scope="session")
def region(api):
    """省/市/区 id 是内置数据集自己的序号，不是国标行政区划码，所以顺着三级联动
    接口真查一遍取第一条——顺便也验证了这条链本身是通的。"""
    province = api.ok("System.Address.province")[0]
    city = api.ok("System.Address.city", {"province_id": province["id"]})[0]
    district = api.ok("System.Address.district", {"city_id": city["id"]})[0]
    return {
        "province_id": province["id"],
        "city_id": city["id"],
        "district_id": district["id"],
    }


# 大连港清关要求同一航次里身份证、地址、电话都不能重复，所以每个测试地址的
# 实名信息都得是独一份的，否则测试之间会互相撞单。
_seq = itertools.count(1)


@pytest.fixture
def make_address(api, region):
    def _make(token, **kw):
        n = next(_seq)
        payload = {
            "consigner": f"收件人{n}",
            "mobile": f"139{n:08d}"[:11],
            "address": f"测试路 {n} 号",
            "idnumber": f"1101011990{n:08d}",
            **region,
            **kw,
        }
        return api.ok("System.Member.addAddress", payload, token)
    return _make


@pytest.fixture
def address_id(make_address, token):
    return make_address(token)["id"]


@pytest.fixture(scope="session")
def line(api):
    """用公开的 lineList 取线路，省得每个 fixture 都得先拿 token。"""
    return api.ok("System.Address.lineList")[0]


@pytest.fixture
def line_id(line):
    return line["id"]


@pytest.fixture
def make_package(api, token):
    """建一个包裹，可选直接推进到已入库（入库必须称重）。返回包裹 dict。

    netwt 是用户预报时自己填的重量，actual_weight 是仓库称的。计费只认后者，
    所以默认让两者不一样，免得测试在"用错了字段"的情况下照样通过。
    """
    def _make(netwt="2.0", inbound=False, actual_weight=None, **kw):
        # 申报价值默认压低：两条线路按申报价值卡准入，默认值太高会撞上
        # 「精致小」的 ¥400 上限，让每个测试都得额外操心这件事。
        pkg = api.ok("System.Order.addforecast", {
            "express_num": f"TEST{uuid.uuid4().hex[:10].upper()}",
            "good_name": "测试商品",
            "netwt": netwt,
            "price": "100",
            **kw,
        }, token)
        if inbound:
            pkg = api.ok("System.Order.markInbound", {
                "goods_id": pkg["id"],
                "actual_weight": actual_weight if actual_weight is not None else netwt,
                "staff_key": STAFF_KEY,
            })
        return pkg
    return _make


def png_bytes():
    """一张最小的合法 PNG，上传测试用。"""
    return (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')


_UNSET = object()


@pytest.fixture
def upload(api):
    """POST /upload。content 显式传 b"" 时就真的传空文件，不要被默认值顶掉。"""
    def _upload(content=_UNSET, filename="photo.png", content_type="image/png", staff_key=STAFF_KEY):
        body = png_bytes() if content is _UNSET else content
        return api.client.post(
            "/upload",
            files={"file": (filename, io.BytesIO(body), content_type)},
            data={"staff_key": staff_key},
        ).json()
    return _upload


@pytest.fixture
def photographed_package(api, make_package, upload):
    """一个申请了拍照、并且仓库确实拍了的已入库包裹。"""
    def _make(**kw):
        pkg = make_package(inbound=True, photo_requested=True, **kw)
        url = upload()["data"]["url"]
        return api.ok("System.Order.addPackagePhoto", {
            "goods_id": pkg["id"], "url": url, "kind": "inbound", "staff_key": STAFF_KEY,
        })
    return _make
