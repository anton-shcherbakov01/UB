from .base import WBApiBase
from .statistics import WBStatisticsMixin
from .promotion import WBPromotionMixin

class WBApiService(WBStatisticsMixin, WBPromotionMixin, WBApiBase):
    """
    Единый фасад для работы с API Wildberries.
    Наследует методы из миксинов Statistics и Promotion, а также Base.
    """
    pass

# Создаем синглтон, как было в оригинальном файле
wb_api_service = WBApiService()

__all__ = ["wb_api_service", "WBApiService"]