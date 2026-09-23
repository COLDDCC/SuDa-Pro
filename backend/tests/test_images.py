"""上传图片的压缩与校验。

压缩不是锦上添花：照片和 SQLite 在同一个卷上，磁盘被原图撑满会连带数据库写不进去，
下单入库发货全挂。这组测试守的是那条线。
"""
import io

import pytest
from PIL import Image

from app import images


def make_photo(size=(4000, 3000), fmt="JPEG"):
    """造一张"手机直出"尺寸的图。

    用平滑渐变而不是随机噪点：噪点是 JPEG 最难压的极端情况，压缩比会假性偏低，
    真实照片以渐变和平滑区域为主，这样测出来的比例才有参考意义。
    """
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        for x in range(0, w, 4):
            c = ((x * 255) // w, (y * 255) // h, ((x + y) * 255) // (w + h))
            for dx in range(min(4, w - x)):
                px[x + dx, y] = c
    buf = io.BytesIO()
    img.save(buf, format=fmt, quality=95) if fmt == "JPEG" else img.save(buf, format=fmt)
    return buf.getvalue()


def test_large_photo_is_shrunk_to_the_long_edge_cap():
    body, ext = images.compress(make_photo((4000, 3000)))
    out = Image.open(io.BytesIO(body))
    assert max(out.size) == images.MAX_EDGE
    assert out.size == (images.MAX_EDGE, images.MAX_EDGE * 3 // 4), "长宽比被改了"
    assert ext == ".jpg"


def test_compression_actually_saves_a_lot_of_space():
    """这是整件事的重点：压不下来就没意义。"""
    original = make_photo((4000, 3000))
    body, _ = images.compress(original)
    assert len(body) < len(original) / 3, (
        f"只从 {len(original)} 压到 {len(body)}，没达到预期")


def test_small_image_is_not_blown_up():
    """小图原样保留，不能被硬拉大糊掉。"""
    body, _ = images.compress(make_photo((400, 300)))
    assert Image.open(io.BytesIO(body)).size == (400, 300)


def test_transparent_png_gets_a_white_background_not_black():
    """带透明通道的图直接转 RGB 会变成黑底。"""
    img = Image.new("RGBA", (50, 50), (255, 255, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    body, ext = images.compress(buf.getvalue())
    assert ext == ".jpg"
    assert Image.open(io.BytesIO(body)).getpixel((25, 25)) == (255, 255, 255)


def test_exif_rotation_is_baked_into_the_pixels():
    """手机拍的照片带方向标记，不处理的话在小程序里会歪着显示。"""
    img = Image.new("RGB", (100, 50), (200, 100, 50))
    exif = img.getexif()
    exif[274] = 6          # Orientation = 旋转 90 度
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)

    body, _ = images.compress(buf.getvalue())
    assert Image.open(io.BytesIO(body)).size == (50, 100), "EXIF 方向没被应用"


def test_exif_metadata_is_stripped():
    """EXIF 里有拍摄地点这类信息，没必要留在给客户看的图上。"""
    img = Image.new("RGB", (100, 100))
    exif = img.getexif()
    exif[271] = "SecretCameraMaker"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)

    body, _ = images.compress(buf.getvalue())
    assert not Image.open(io.BytesIO(body)).getexif()


@pytest.mark.parametrize("junk", [
    b"not an image at all",
    b"\x89PNG\r\n\x1a\n" + b"garbage" * 50,     # PNG 头，后面是垃圾
    b"\xff\xd8\xff" + b"\x00" * 100,            # JPEG 头，后面是垃圾
])
def test_undecodable_bytes_are_rejected(junk):
    """Content-Type 是客户端说了算的，不能拿它当数据校验——必须真解码一遍。"""
    with pytest.raises(images.BadImage):
        images.compress(junk)


# ---- 走完整的上传接口 ----

def test_upload_endpoint_stores_the_compressed_version(api, upload):
    original = make_photo((3000, 2000))
    url = upload(content=original, content_type="image/jpeg")["data"]["url"]

    stored = api.client.get(url)
    assert stored.status_code == 200
    assert len(stored.content) < len(original) / 3, "存下来的还是原图大小"
    assert max(Image.open(io.BytesIO(stored.content)).size) == images.MAX_EDGE


def test_upload_normalises_everything_to_jpg(upload):
    """PNG 存照片体积是 JPEG 的好几倍，统一转。"""
    assert upload(content=make_photo((800, 600), fmt="PNG"),
                  content_type="image/png")["data"]["url"].endswith(".jpg")


def test_upload_rejects_a_file_lying_about_its_type(upload):
    """声称是 PNG 实际是可执行脚本——压缩这一步会把它拦下来。"""
    assert upload(content=b"#!/bin/sh\nrm -rf /", content_type="image/png")["code"] == 400
