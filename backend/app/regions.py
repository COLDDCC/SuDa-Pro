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


def list_provinces():
    return _load()["provinces"]


def list_cities(province_id):
    return [c for c in _load()["cities"] if c["province_id"] == int(province_id)]


def list_districts(city_id):
    return [d for d in _load()["districts"] if d["city_id"] == int(city_id)]


def get_province_name(province_id):
    for p in _load()["provinces"]:
        if p["id"] == int(province_id):
            return p["name"]
    return ""


def get_city_name(city_id):
    for c in _load()["cities"]:
        if c["id"] == int(city_id):
            return c["name"]
    return ""


def get_district_name(district_id):
    for d in _load()["districts"]:
        if d["id"] == int(district_id):
            return d["name"]
    return ""
