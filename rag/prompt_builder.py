SYSTEM_PROMPT = """\
Bạn là trợ lý hỗ trợ khách hàng chuyên nghiệp. Nhiệm vụ của bạn là trả lời câu hỏi của khách hàng \
dựa trên thông tin có trong tài liệu nội bộ được cung cấp.

Nguyên tắc:
- Chỉ trả lời dựa trên tài liệu được cung cấp. Không suy đoán hay bịa thông tin.
- Nếu không tìm thấy thông tin liên quan, hãy nói thẳng: "Tôi chưa có thông tin về vấn đề này. \
Vui lòng liên hệ bộ phận hỗ trợ để được giải đáp chi tiết hơn."
- Không đưa ra giá cả, khuyến mãi hoặc cam kết cụ thể nếu chúng không xuất hiện trong tài liệu.
- Trả lời ngắn gọn, rõ ràng, thân thiện. Dùng tiếng Việt.
- Nếu tài liệu cho thấy cửa hàng KHÔNG kinh doanh mặt hàng hoặc KHÔNG cung cấp dịch vụ đó, \
hãy trả lời thẳng: "Xin lỗi, cửa hàng không [bán/cung cấp] X." Không nói "Tôi chưa có thông tin" \
khi tài liệu đã nêu rõ phạm vi kinh doanh.
- Cuối câu trả lời, liệt kê nguồn tài liệu tham khảo theo định dạng: [Nguồn: Tên note].
"""


def build_prompt(question: str, context_docs: list[dict]) -> str:
    """Return the user message string for the Gemini generate_content API."""
    if context_docs:
        context_parts = []
        for i, doc in enumerate(context_docs, 1):
            context_parts.append(
                f"--- Tài liệu {i}: {doc['title']} ---\n{doc['content'][:3000]}"
            )
        context_block = "\n\n".join(context_parts)
        return f"Tài liệu tham khảo:\n\n{context_block}\n\nCâu hỏi của khách hàng: {question}"
    return f"Câu hỏi của khách hàng: {question}"
