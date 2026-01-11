import time
import logging
from typing import Optional, Dict, Any, Union
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("RTB-Engine")

class PIDController:
    """
    Профессиональный PID-регулятор для RTB систем.
    Особенности:
    - Derivative on Measurement (защита от скачков при смене цели)
    - Anti-Windup (Clamping интегратора)
    - Deadband (Зона нечувствительности для экономии API квот)
    """
    def __init__(self, kp: float, ki: float, kd: float, 
                 min_bid: int, max_bid: int, 
                 target_pos: int,
                 integral_min: float = -500.0, 
                 integral_max: float = 500.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        
        self.min_bid = min_bid
        self.max_bid = max_bid
        self.target_pos = target_pos
        
        # Ограничения интегратора (Anti-Windup)
        self.integral_min = integral_min
        self.integral_max = integral_max
        
        self.last_time = None

    def update(self, current_pos: int, current_bid: int, 
               prev_error: float, accumulated_integral: float, 
               last_measurement: float = None) -> dict:
        """
        Рассчитывает новую ставку.
        Возвращает словарь с новой ставкой и состоянием для сохранения в Redis.
        """
        now = time.time()
        
        # Если это первый запуск, инициализируем dt
        if self.last_time is None:
            dt = 1.0  # Дефолт для первого шага
        else:
            dt = now - self.last_time
            if dt <= 0: dt = 1e-3 # Защита от деления на ноль

        # --- 1. Расчет ошибки ---
        # В WB позиция 1 лучше, чем 10.
        # Если мы на 10, а хотим 1 -> 10 - 1 = 9 (Ошибка положительная, нужно повышать ставку)
        # Если мы на 1, а хотим 5 -> 1 - 5 = -4 (Ошибка отрицательная, нужно понижать ставку)
        error = current_pos - self.target_pos
        
        # --- 2. Deadband (Мертвая зона) ---
        # Если мы отклонились менее чем на 1 позицию, не дергаем API
        if abs(error) <= 1 and current_pos != 0:
            return {
                "new_bid": current_bid,
                "integral": accumulated_integral,
                "prev_error": error,
                "last_measurement": current_pos,
                "action": "hold",
                "components": {"P": 0, "I": 0, "D": 0}
            }

        # --- 3. Proportional Term ---
        P = self.kp * error

        # --- 4. Integral Term (с Anti-Windup Clamping) ---
        # Накапливаем ошибку
        # Conditional Integration: не накапливаем, если выход уже в насыщении (saturated) и ошибка пытается усугубить это
        # Здесь используем простой Clamping, который эффективен для аукционов
        new_integral = accumulated_integral + (error * dt)
        
        # Clamping: жестко ограничиваем вклад интегратора
        new_integral = max(min(new_integral, self.integral_max), self.integral_min)
        
        I = self.ki * new_integral

        # --- 5. Derivative Term (Derivative on Measurement) ---
        # Используем изменение позиции, а не ошибки, чтобы избежать "удара" (Kick)
        # при резком изменении target_pos.
        # D = -Kd * (d(Measurement) / dt)
        if last_measurement is not None:
            d_measurement = (current_pos - last_measurement) / dt
            D = -self.kd * d_measurement
        else:
            D = 0

        # --- 6. Расчет выхода (Delta Bid) ---
        output = P + I + D
        
        # Новая ставка = Текущая + Изменение
        calculated_bid = current_bid + output
        
        # Округление до целого (WB принимает int)
        final_bid = int(round(calculated_bid))

        # --- 7. Saturation (Ограничение выхода) ---
        # Применяем лимиты стратегии
        final_bid = max(min(final_bid, self.max_bid), self.min_bid)
        
        action = "update"
        if final_bid == current_bid:
            action = "hold"

        self.last_time = now

        return {
            "new_bid": final_bid,
            "integral": new_integral,
            "prev_error": error,
            "last_measurement": current_pos,
            "action": action,
            "components": {"P": P, "I": I, "D": D}
        }

class StrategyInput(BaseModel):
    target_cpa: float
    current_conversion_rate: Optional[float] = Field(default=None)
    max_cpm: int
    click_to_order_ratio: Optional[float] = Field(default=None, description="Количество кликов на 1 заказ (1/CR)")
    competitor_bid: Optional[int] = Field(default=None)

class StrategyManager:
    """
    Управляет финансовой безопасностью и стратегиями биддинга.
    Реализует паттерн 'Guard Rails' для защиты от слива бюджета.
    """
    DEFAULT_CR = 0.05  # 5% конверсия как fallback для категории
    
    def __init__(self, input_data: StrategyInput):
        self.data = input_data
        
        # Нормализация Conversion Rate
        if not self.data.current_conversion_rate or self.data.current_conversion_rate <= 0:
            logger.warning(f"Conversion rate missing/zero. Using category default: {self.DEFAULT_CR}")
            self.cr = self.DEFAULT_CR
        else:
            self.cr = self.data.current_conversion_rate

        # Нормализация Click To Order Ratio
        # Если не передан, вычисляем как обратный CR (при условии CR > 0)
        if not self.data.click_to_order_ratio or self.data.click_to_order_ratio <= 0:
            if self.cr > 0:
                self.click_to_order_ratio = 1 / self.cr
            else:
                self.click_to_order_ratio = 20.0 # Fallback (1/0.05)
        else:
            self.click_to_order_ratio = self.data.click_to_order_ratio

    def calculate_safety_cap(self) -> int:
        """
        Рассчитывает максимально допустимую ставку CPM исходя из Unit-экономики.
        Formula: safe_bid = (target_cpa * current_conversion_rate * 1000) / click_to_order_ratio
        """
        try:
            # Примечание: В классической формуле:
            # CPM = CPC * CTR * 1000
            # CPC = CPA * CR
            # Значит CPM = CPA * CR * CTR * 1000
            # Если click_to_order_ratio интерпретируется как 1/CR (кликов на заказ),
            # то деление на него равнозначно умножению на CR.
            # Строго следуем формуле из ТЗ:
            
            numerator = self.data.target_cpa * self.cr * 1000
            denominator = self.click_to_order_ratio
            
            if denominator == 0:
                logger.error("Click-to-order ratio is 0, avoiding division by zero.")
                return self.data.max_cpm

            safe_bid = numerator / denominator
            
            return int(safe_bid)
        except Exception as e:
            logger.error(f"Safety cap calculation error: {e}")
            return self.data.max_cpm

    def apply_shadowing(self, competitor_bid: int) -> int:
        """
        Стратегия 'Shadowing': ставка всегда чуть выше конкурента.
        Позволяет экономить бюджет, не перебивая ставку слишком сильно.
        Logic: return competitor_bid + 1
        """
        return competitor_bid + 1

    def decide_bid(self, pid_suggested_bid: int, user_max_bid: int) -> Dict[str, Any]:
        """
        Принимает финальное решение о ставке, объединяя PID, Safety Cap и Shadowing.
        Logic: final_bid = min(pid_output, safety_cap_output, user_max_bid)
        """
        # 1. Расчет финансового потолка
        safety_cap = self.calculate_safety_cap()
        
        # 2. Логика Shadowing (если известна ставка конкурента, она может быть lower bound или target)
        # В данном контексте PID уже учитывает позицию (конкуренцию), 
        # но если мы хотим жестко привязаться к конкуренту (Shadowing):
        shadow_bid = None
        if self.data.competitor_bid:
            shadow_bid = self.apply_shadowing(self.data.competitor_bid)
            # Если стратегия чистого Shadowing, можно игнорировать PID, 
            # но по ТЗ мы используем min() от всех ограничений.
            # Однако shadowing обычно диктует 'минимум необходимый для победы'.
            # Если PID говорит 500, а конкурент 200 (shadow 201), то PID может быть "перегрет".
            # Но здесь мы используем PID как основной драйвер позиции.
            pass 

        # 3. Финальный выбор (Safety Layer)
        # Берем минимум из предложенного PID, защиты бюджета и жесткого лимита пользователя
        
        possible_bids = [pid_suggested_bid, safety_cap, user_max_bid]
        final_bid = min(possible_bids)
        
        # Логирование срабатывания защиты
        status_msg = "OK"
        capped_by = None
        
        if final_bid == safety_cap and safety_cap < pid_suggested_bid:
            logger.warning(f"Bid capped by CPA Guard. PID: {pid_suggested_bid}, Cap: {safety_cap}")
            status_msg = "Bid capped by CPA Guard"
            capped_by = "cpa_guard"
        elif final_bid == user_max_bid and user_max_bid < pid_suggested_bid:
            status_msg = "Bid capped by User Max Limit"
            capped_by = "user_max"

        return {
            "final_bid": final_bid,
            "original_pid_bid": pid_suggested_bid,
            "safety_cap": safety_cap,
            "status": status_msg,
            "capped_by": capped_by
        }