"""
Единый маппинг категорий заказов в коды навыков мастеров.

Используется в:
- distribution_worker.py
- distribution_scheduler.py
- eligibility.py
"""

CATEGORY_TO_SKILL_CODE = {
    "ELECTRICS": "ELECTRICS",
    "PLUMBING": "PLUMBING",
    "APPLIANCES": "APPLIANCES",
    "WINDOWS": "WINDOWS",
    "HANDYMAN": "HANDYMAN",
    "ROADSIDE": "ROADSIDE",
}


def get_skill_code(category: str | None) -> str | None:
    """Получить код навыка для категории заказа.
    
    Args:
        category: Категория заказа (ELECTRICS, PLUMBING, и т.д.)
        
    Returns:
        Код навыка (ELEC, PLUMB, и т.д.) или None
    """
    if not category:
        return None
    return CATEGORY_TO_SKILL_CODE.get(str(category).upper())
