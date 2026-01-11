import time
import logging

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
                "action": "hold"
            }

        # --- 3. Proportional Term ---
        P = self.kp * error

        # --- 4. Integral Term (с Anti-Windup Clamping) ---
        # Накапливаем ошибку
        new_integral = accumulated_integral + (error * dt)
        
        # Clamping: жестко ограничиваем вклад интегратора, чтобы он не улетел в бесконечность
        # если ставка конкурента физически выше нашего max_bid
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
        
        # Защита от слишком резких скачков (опционально, например не более 30% за шаг)
        # if abs(final_bid - current_bid) > current_bid * 0.5: ... 

        action = "update"
        if final_bid == current_bid:
            action = "hold"

        return {
            "new_bid": final_bid,
            "integral": new_integral,
            "prev_error": error,
            "last_measurement": current_pos,
            "action": action,
            "components": {"P": P, "I": I, "D": D}
        }