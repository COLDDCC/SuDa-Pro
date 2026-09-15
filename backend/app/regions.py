"""Loads the bundled China province/city/district dataset used by
System.Address.province / city / district.

Source: public domain administrative-division listing (province -> city ->
district), re-indexed with numeric ids so it matches the competitor's
province()/city(province_id)/district(city_id) interface shape.
"""
import json
import os
import threading

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "regions.json")
_lock = threading.Lock()
_cache = None


def _load():
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                with open(_DATA_PATH, encoding="utf-8") as f:
                    _cache = json.load(f)
    return _cache


def _safe_int(value):
    """id 参数理论上都应该是数字，但请求体是外部传进来的 JSON，什么都可能塞进来
    （字符串、None、别的类型）。转不了就当"没有这个 id"处理，而不是让 int()
    直接抛 ValueError 炸到 500。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def list_provinces():
    return _load()["provinces"]


def list_cities(province_id):
    province_id = _safe_int(province_id)
    if province_id is None:
        return []
    return [c for c in _load()["cities"] if c["province_id"] == province_id]


def list_districts(city_id):
    city_id = _safe_int(city_id)
    if city_id is None:
        return []
    return [d for d in _load()["districts"] if d["city_id"] == city_id]


def get_province_name(province_id):
    province_id = _safe_int(province_id)
    if province_id is None:
        return ""
    for p in _load()["provinces"]:
        if p["id"] == province_id:
            return p["name"]
    return ""


def get_city_name(city_id):
    city_id = _safe_int(city_id)
    if city_id is None:
        return ""
    for c in _load()["cities"]:
        if c["id"] == city_id:
            return c["name"]
    return ""


def get_district_name(district_id):
    district_id = _safe_int(district_id)
    if district_id is None:
        return ""
    for d in _load()["districts"]:
        if d["id"] == district_id:
            return d["name"]
    return ""
