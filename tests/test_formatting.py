"""Định dạng link trả về cho FE.

Bất biến: link sản phẩm hiển thị dạng <a href="url">Xem chi tiết</a> — text là
nhãn, KHÔNG lộ URL trần. URL trần khác (không phải dòng "Xem chi tiết") vẫn được
bọc <a> với chính URL làm text. Không bọc trùng URL đã nằm trong href.
"""
from api.formatting import format_answer_lines

_ATTRS = 'target="_blank" rel="noopener noreferrer"'


def test_detail_link_rendered_as_anchor_with_label():
    out = format_answer_lines("- Xem chi tiết: https://dienmaythienphu.vn/tivi/x")
    assert out == [
        f'- <a href="https://dienmaythienphu.vn/tivi/x" {_ATTRS}>Xem chi tiết</a>'
    ]


def test_detail_link_not_double_wrapped():
    line = format_answer_lines("- Xem chi tiết: https://x.vn/a")[0]
    assert line.count("<a ") == 1
    assert 'href="https://x.vn/a"' in line
    # URL KHÔNG được dùng làm text hiển thị
    assert "https://x.vn/a</a>" not in line


def test_bare_url_still_linkified_with_url_text():
    line = format_answer_lines("Tham khảo https://x.vn/p")[0]
    assert line == f'Tham khảo <a href="https://x.vn/p" {_ATTRS}>https://x.vn/p</a>'


def test_line_without_url_unchanged():
    assert format_answer_lines("Giá: 5.000.000 đ") == ["Giá: 5.000.000 đ"]
