"""粘贴文字识别快递单号（差异化功能"预报体验"的过渡版）。"""
import pytest

from app import tracking


@pytest.mark.parametrize("text,expected", [
    ("お問い合わせ番号 EE123456789JP 追跡", "EE123456789JP"),
    ("伝票番号：1234-5678-9012", "123456789012"),
    ("追跡番号 1234 5678 9012 です", "123456789012"),
    ("SF1234567890123 顺丰速运", "1234567890123"),
    ("お問い合わせ番号　１２３４－５６７８－９０１２", "123456789012"),   # 全角
])
def test_best_guess(text, expected):
    assert tracking.guess_tracking_numbers(text)[0] == expected


@pytest.mark.parametrize("text", ["", "没有任何单号的一段话", "2026年9月22日 発送", None])
def test_no_false_positives(text):
    assert tracking.guess_tracking_numbers(text) == []


def test_ems_format_wins_over_plain_digits():
    """一段文字里同时有电话号码和 EMS 单号时，EMS 要排在前面。"""
    got = tracking.guess_tracking_numbers("电话 03012345678 単号 EE123456789JP")
    assert got[0] == "EE123456789JP"


def test_duplicates_are_collapsed():
    got = tracking.guess_tracking_numbers("EE123456789JP ... 再确认 EE123456789JP")
    assert got == ["EE123456789JP"]


def test_api_returns_best_guess_and_candidates(api, token):
    data = api.ok("System.Order.parseTrackingText", {
        "text": "お問い合わせ番号 EE123456789JP / 電話 03012345678",
    }, token)
    assert data["best_guess"] == "EE123456789JP"
    assert len(data["candidates"]) >= 1
