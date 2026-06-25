"""Định dạng link trả về cho FE.

Bất biến: MỌI link hiển thị text "Tại đây" — KHÔNG bao giờ lộ URL dài. Dòng
"Xem chi tiết: <url>" giữ nhãn rồi link "Tại đây"; URL trần đứng riêng (model
xuống dòng tách URL khỏi nhãn) cũng thành "Tại đây". Không bọc trùng URL đã nằm
trong href.
"""
from api.formatting import format_answer_lines

_ATTRS = 'target="_blank" rel="noopener noreferrer"'


def test_detail_link_rendered_as_anchor_with_tai_day():
    out = format_answer_lines("- Xem chi tiết: https://dienmaythienphu.vn/tivi/x")
    assert out == [
        f'- Xem chi tiết: <a href="https://dienmaythienphu.vn/tivi/x" {_ATTRS}>Tại đây</a>'
    ]


def test_detail_link_not_double_wrapped():
    line = format_answer_lines("- Xem chi tiết: https://x.vn/a")[0]
    assert line.count("<a ") == 1
    assert 'href="https://x.vn/a"' in line
    # URL KHÔNG được dùng làm text hiển thị
    assert "https://x.vn/a</a>" not in line


def test_bare_url_on_own_line_becomes_tai_day():
    # Model xuống dòng: "Xem chi tiết:" và URL ở 2 dòng riêng (bug item 4 trong ảnh).
    out = format_answer_lines("- Xem chi tiết:\nhttps://dienmaythienphu.vn/tivi/ua43u8500")
    assert out == [
        "- Xem chi tiết:",
        f'<a href="https://dienmaythienphu.vn/tivi/ua43u8500" {_ATTRS}>Tại đây</a>',
    ]
    # URL dài KHÔNG còn xuất hiện dưới dạng text hiển thị.
    assert not any("ua43u8500</a>" in line for line in out)


def test_bare_url_linkified_with_tai_day_text():
    line = format_answer_lines("Tham khảo https://x.vn/p")[0]
    assert line == f'Tham khảo <a href="https://x.vn/p" {_ATTRS}>Tại đây</a>'


def test_line_without_url_unchanged():
    assert format_answer_lines("Giá: 5.000.000 đ") == ["Giá: 5.000.000 đ"]
