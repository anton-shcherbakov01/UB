import time
import logging
import asyncio
import json
from datetime import datetime
from typing import Optional, Tuple, Dict, List

from database import AsyncSessionLocal, BidderSettings, BidderLog
from wb_api_service import wb_api_service  # Ваш сервис API (должен иметь get_auction_cpm)
from parser_service import parser_service  # Для проверки органики

logger = logging.getLogger("Bidder-Engine")

# --- ВАШ КОД PID CONTROLLER (Оставляем как есть) ---
class PIDController:
    """
    Advanced PID Controller for Real-Time Bidding.
    Features: Anti-Windup, Deadband, Derivative Kick Prevention, Output limiting
    """
    def __init__(
        self, 
        kp: float, ki: float, kd: float, 
        target_pos: int, 
        min_bid: int, max_bid: int,
        deadband: int = 1
    ):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.target_pos = target_pos
        self.min_bid = min_bid
        self.max_bid = max_bid
        self.deadband = deadband
        self._prev_error = 0.0
        self._integral = 0.0
        self._prev_measurement: Optional[float] = None

    def load_state(self, integral: float, prev_measurement: Optional[float]):
        """Load state from Redis/DB"""
        self._integral = integral
        self._prev_measurement = prev_measurement

    def get_state(self) -> Tuple[float, Optional[float]]:
        """Export state to save in Redis/DB"""
        return self._integral, self._prev_measurement

    def update(self, current_pos: int, current_bid: int, dt: float) -> int:
        if dt <= 0: return current_bid
        
        # 1. Error Logic (Target 1 is better than 5)
        # Если цель 1, а мы на 5 -> ошибка 4 -> надо повышать ставку
        error = current_pos - self.target_pos

        if abs(error) <= self.deadband:
            return current_bid

        p_term = self.kp * error

        # 4. Integral with Clamping
        self._integral += self.ki * error * dt
        integral_limit = (self.max_bid - self.min_bid) * 0.5
        self._integral = max(-integral_limit, min(self._integral, integral_limit))
        i_term = self._integral

        # 5. Derivative
        if self._prev_measurement is None:
            self._prev_measurement = current_pos
        
        derivative = (current_pos - self._prev_measurement) / dt
        d_term = -self.kd * derivative
        self._prev_measurement = current_pos

        adjustment = p_term + i_term + d_term
        new_bid = int(current_bid + adjustment)

        if new_bid < self.min_bid: new_bid = self.min_bid
        elif new_bid > self.max_bid: new_bid = self.max_bid

        return new_bid

# --- НОВЫЙ КЛАСС: StrategyManager ---
class StrategyManager:
    def __init__(self, settings: Dict[str, Any]):
        self.target_pos = settings.get('target_pos', 1)
        self.min_bid = settings.get('min_bid', 125)
        self.max_bid = settings.get('max_bid', 1000)
        self.target_cpa = settings.get('target_cpa', 0)
        self.max_cpm = settings.get('max_cpm', 5000)
        self.strategy = settings.get('strategy', 'target_pos')

    def decide_bid(self, pid_bid: int, current_metrics: Dict[str, float], competitor_bid: Optional[int]) -> Tuple[int, str]:
        """
        Принимает решение о ставке на основе стратегии и лимитов.
        """
        final_bid = self.min_bid
        reason = "init"

        # 1. Выбор базовой ставки
        if self.strategy == 'pid':
            final_bid = pid_bid
            reason = f"PID (Target Pos {self.target_pos})"
        
        elif self.strategy == 'target_pos':
            # Стратегия удержания позиции: перебить конкурента
            if competitor_bid is not None:
                final_bid = competitor_bid + 1
                reason = f"Follow Comp ({competitor_bid} + 1)"
            else:
                # Если конкурента нет (мы одни или аукцион пуст), ставим минимум
                final_bid = self.min_bid
                reason = "No comp, min bid"
                
        else:
            reason = "Unknown strategy, min bid"

        # 2. Safety Layer: CPA Guard (если задан)
        # Если CPA (Cost Per Action) слишком высокий, снижаем ставку
        # CPA ~ (CPM / 1000) / CTR / CR
        ctr = current_metrics.get('ctr', 0) or 0.01 # защита от деления на 0
        cr = current_metrics.get('cr', 0) or 0.01
        
        if self.target_cpa > 0:
            # Расчетный CPA при текущей ставке
            predicted_cpa = (final_bid / 1000) / (ctr * cr)
            if predicted_cpa > self.target_cpa:
                # Снижаем ставку, чтобы попасть в CPA
                # Bid = CPA * 1000 * CTR * CR
                capped_bid = int(self.target_cpa * 1000 * ctr * cr)
                if capped_bid < final_bid:
                    final_bid = capped_bid
                    reason += f" | CPA Cap {self.target_cpa}"

        # 3. Hard Limits
        if final_bid > self.max_bid:
            final_bid = self.max_bid
            reason += " | Max Bid"
            
        if self.max_cpm and final_bid > self.max_cpm:
            final_bid = self.max_cpm
            reason += " | Max CPM"

        if final_bid < self.min_bid:
            final_bid = self.min_bid
            
        return int(final_bid), reason

# --- НОВЫЙ КОД: ДВИЖОК БИДДЕРА ---

class BidderEngine:
    """
    Оркестратор управления ставками.
    Работает с БД, API WB и выбирает стратегию.
    """
    
    async def run_cycle(self, campaign_id: int, user_id: int):
        async with AsyncSessionLocal() as db:
            # 1. Загружаем настройки кампании
            settings = await db.get(BidderSettings, campaign_id)
            if not settings or not settings.is_active:
                return

            # Нам нужен токен пользователя
            # Предполагаем, что есть связь или получение юзера
            user = await db.get("User", user_id) # Псевдокод, замените на реальный запрос
            if not user or not user.wb_api_token:
                logger.error(f"No token for user {user_id}")
                return

            # 2. Получаем РЕАЛЬНЫЙ аукцион (ставок конкурентов)
            # Важно: keyword должен быть в настройках
            target_keyword = getattr(settings, 'keyword', None) 
            if not target_keyword:
                logger.warning(f"No keyword for campaign {campaign_id}")
                return

            # Вызываем метод получения аукциона (из моего предыдущего ответа)
            # Он возвращает список [{'pos': 1, 'cpm': 1000, 'id': 123}, ...]
            auction = await wb_api_service.get_auction_cpm(target_keyword)
            if not auction:
                logger.warning(f"Empty auction data for {target_keyword}")
                return

            # 3. Определяем где мы сейчас
            my_ad = next((x for x in auction if x['id'] == campaign_id), None)
            
            # Если нас нет в аукционе, считаем что мы далеко (pos=100, cpm=текущая из настроек или min)
            current_pos = my_ad['pos'] if my_ad else 100
            current_cpm = my_ad['cpm'] if my_ad else settings.min_bid
            
            # 4. Проверка органики (Экономия бюджета)
            # Если мы органически уже в ТОПе по этому ключу, отключаем рекламу (или ставим минимум)
            should_bid = True
            if settings.check_organic: # Предположим, есть такой флаг
                organic_data = await parser_service.get_search_position_v2(target_keyword, settings.sku)
                organic_pos = organic_data.get('organic_pos', 999)
                if organic_pos <= settings.target_pos:
                    logger.info(f"Campaign {campaign_id}: Organic pos {organic_pos} is good. Pausing bid.")
                    should_bid = False
                    new_bid = settings.min_bid # Или можно ставить на паузу через API

            if not should_bid:
                # Если органика хорошая, просто обновляем ставку на минимум и выходим
                await self._apply_bid(db, user.wb_api_token, campaign_id, settings.min_bid, current_cpm, current_pos, settings.target_pos, "Organic protection")
                return

            # 5. Расчет новой ставки
            new_bid = current_cpm

            if settings.strategy == 'pid':
                # --- PID СТРАТЕГИЯ ---
                # Нам нужно время с последнего обновления для dt
                last_update = settings.last_updated_at or datetime.utcnow()
                dt = (datetime.utcnow() - last_update).total_seconds()
                if dt < 1: dt = 1 # Защита от деления на ноль

                # Инициализируем контроллер
                pid = PIDController(
                    kp=1.0, ki=0.1, kd=0.05, # Эти коэф. лучше вынести в настройки
                    target_pos=settings.target_pos,
                    min_bid=settings.min_bid,
                    max_bid=settings.max_bid
                )
                
                # Загружаем сохраненное состояние PID из БД (предполагаем поле pid_state типа JSON)
                state = settings.pid_state or {}
                pid.load_state(state.get('integral', 0.0), state.get('prev_measurement'))

                # Считаем
                new_bid = pid.update(current_pos, current_cpm, dt)
                
                # Сохраняем состояние обратно
                new_integral, new_prev = pid.get_state()
                settings.pid_state = {'integral': new_integral, 'prev_measurement': new_prev}

            else:
                # --- СТРАТЕГИЯ: ЛИНЕЙНАЯ / "В ЛОБ" (Надежная) ---
                # Хочу 5-е место. Смотрю кто на 5-м месте. Ставлю его ставку + 1 руб.
                target_idx = settings.target_pos - 1 # Индекс в массиве (0 = 1 место)
                
                if target_idx < len(auction):
                    competitor_bid = auction[target_idx]['cpm']
                    new_bid = competitor_bid + 1
                else:
                    # Если конкурентов мало, берем ставку последнего
                    new_bid = auction[-1]['cpm'] + 1 if auction else settings.min_bid

                # Хард лимиты
                if new_bid > settings.max_bid: new_bid = settings.max_bid
                if new_bid < settings.min_bid: new_bid = settings.min_bid

            # Дополнительная защита по max_cpm
            if settings.max_cpm and new_bid > settings.max_cpm:
                new_bid = settings.max_cpm

            # 6. Применяем изменения
            await self._apply_bid(
                db, 
                user.wb_api_token, 
                campaign_id, 
                new_bid, 
                current_cpm, 
                current_pos, 
                settings.target_pos,
                f"Strategy: {settings.strategy}"
            )
            
            # Обновляем время последней проверки
            settings.last_updated_at = datetime.utcnow()
            await db.commit()

    async def _apply_bid(self, db, token, campaign_id, new_bid, current_bid, current_pos, target_pos, reason):
        """
        Отправляет запрос в WB только если ставка изменилась.
        Пишет логи.
        """
        new_bid = int(new_bid)
        current_bid = int(current_bid)

        # Не спамим API, если ставка та же
        if new_bid == current_bid:
            return

        try:
            # Обновляем ставку через сервис API
            # В wb_api_service должен быть метод update_bid(token, campaign_id, amount)
            await wb_api_service.update_bid(token, campaign_id, new_bid)
            
            logger.info(f"Updated Bid {campaign_id}: {current_bid} -> {new_bid} (Pos: {current_pos}->Target:{target_pos})")

            # Пишем лог в БД
            log_entry = BidderLog(
                campaign_id=campaign_id,
                current_pos=current_pos,
                target_pos=target_pos,
                previous_bid=current_bid,
                calculated_bid=new_bid,
                action="update",
                reason=reason,
                timestamp=datetime.utcnow()
            )
            db.add(log_entry)
            
        except Exception as e:
            logger.error(f"Failed to update bid for {campaign_id}: {e}")

# Создаем глобальный экземпляр
bidder_engine = BidderEngine()