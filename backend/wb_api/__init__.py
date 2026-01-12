from .base import WBBaseClient
from .promotion import WBPromotionMixin
from .statistics import WBStatisticsMixin
from .content import WBContentMixin

class WBApiService(WBPromotionMixin, WBStatisticsMixin, WBContentMixin):
    """
    Единый фасад для работы с API Wildberries.
    Наследует методы всех миксинов.
    """
    pass

# Создаем синглтон для использования во всем приложении
wb_api_service = WBApiService()

__all__ = ["wb_api_service", "WBApiService"]