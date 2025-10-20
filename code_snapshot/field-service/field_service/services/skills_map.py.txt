"""
Единый маппинг категорий заказов в коды навыков мастеров.

Используется в:
- distribution_worker.py
- distribution_scheduler.py
- eligibility.py
"""

CATEGORY_TO_SKILL_CODE = {
    "ELECTRICS": "ELEC",
    "PLUMBING": "PLUMB",
    "APPLIANCES": "APPLI",
    "WINDOWS": "WINDOWS",
    "HANDYMAN": "HANDY",
    "ROADSIDE": "AUTOHELP",
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
