"""
테스트 시나리오 1: calculate_total 함수 버그 수정

버그: 할인율 계산 시 100을 곱하지 않아서 할인이 제대로 안 됨
"""


def calculate_total(price: float, discount_rate: float) -> float:
    """
    총 가격 계산.

    Args:
        price: 원래 가격
        discount_rate: 할인율 (0.1 = 10% 할인)

    Returns:
        할인 적용된 가격

    버그: discount_rate를 그대로 빼서 할인이 과도하게 적용됨
    예: calculate_total(100, 0.1) = 99.9 (기대: 90.0)
    """
    # 🐛 버그: discount_rate를 그대로 빼면 안 됨
    # ✅ 수정: 할인율을 올바르게 적용
    discount = price * discount_rate
    return price - discount
