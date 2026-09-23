"""上传图片的压缩与校验。

手机直出照片一张 3-8MB，原样存下来磁盘很快见底——而照片和 SQLite 数据库在同一个
卷上，磁盘满了会连带订单写不进去，整个系统跟着挂。压到 1/10 之后这个风险基本消失。

顺带还解决两个实际问题：
  1. 手机拍的照片带 EXIF 方向标记，不处理的话在小程序里会歪着显示
  2. 真正用 PIL 解码一遍，等于验证了"这确实是张图"——光看 Content-Type 是不够的，
     那个字段是客户端说了算的
"""
import io

from PIL import Image, ImageOps, UnidentifiedImageError

# 长边上限。留底照片要看清商品外观和破损情况，2000px 绰绰有余；
# 再往上收益很小，体积却涨得快。
MAX_EDGE = 2000
JPEG_QUALITY = 85


class BadImage(Exception):
    """这坨字节不是一张能解码的图。"""


def compress(body: bytes):
    """把上传的原图压成 JPEG，返回 (字节, 扩展名)。

    统一转 JPEG：留底照片不需要透明通道，而 PNG 存照片体积是 JPEG 的好几倍。
    """
    try:
        img = Image.open(io.BytesIO(body))
        img.load()
    except (UnidentifiedImageError, OSError, ValueError):
        raise BadImage("这个文件不是一张能打开的图片")

    # 必须在缩放之前做：EXIF 里的方向标记一旦丢了，照片就永远歪着了。
    img = ImageOps.exif_transpose(img)

    # 带透明通道的图直接转 RGB 会变成黑底，先铺一层白底。
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        canvas = Image.new("RGB", img.size, (255, 255, 255))
        canvas.paste(img, mask=img.split()[-1])
        img = canvas
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # thumbnail 只缩不放，小图原样保留，不会被硬拉大糊掉。
    img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)

    out = io.BytesIO()
    # 重新编码时 EXIF 不带过去：方向已经应用到像素上了，而 EXIF 里还有拍摄地点
    # 这类信息，没必要留在给客户看的图上。
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return out.getvalue(), ".jpg"
