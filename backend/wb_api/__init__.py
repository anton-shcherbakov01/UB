from .base import WBApiBase
from .statistics import WBStatisticsMixin
from .promotion import WBPromotionMixin
# Добавляем импорт Content Mixin, которого не хватало
from .content import WBContentMixin

class WBApiService(
    WBStatisticsMixin, 
    WBPromotionMixin, 
    WBContentMixin,  # <--- Обязательно добавляем сюда
    WBApiBase
):
    """
    Единый фасад для работы с API Wildberries.
    Наследует методы из миксинов Statistics, Promotion и Content, а также Base.
    """
    pass

# Создаем синглтон
wb_api_service = WBApiService()

__all__ = ["wb_api_service", "WBApiService"]