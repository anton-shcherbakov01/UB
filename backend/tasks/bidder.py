import logging
import asyncio
import redis
from datetime import datetime
from typing import Dict, Any, Optional

from celery_app import celery_app, REDIS_URL
from wb_api_service import wb_api_service
from database import SyncSessionLocal, User, BidderSettings
from bidder_engine import PIDController, StrategyManager
from .utils import log_bidder_action_sync
from parser_parts import parser_service

logger = logging.getLogger("Tasks-Bidder")

try:
    r_client = redis.from_url(REDIS_URL, decode_responses=True)
except Exception as e:
    logger.error(f"Redis connect error: {e}")
    r_client = None

class BidderWorker:
    def __init__(self, user_id: int, token: str, settings: BidderSettings):
        self.user_id = user_id
        self.token = token
        self.settings = {
            "target_pos": settings.target_pos,
            "min_bid": settings.min_bid,
            "max_bid": settings.max_bid,
            "target_cpa": settings.target_cpa,
            "max_cpm": settings.max_cpm,
            "strategy": settings.strategy,
            "keyword": getattr(settings, 'keyword', None),  # <-- ВАЖНО: Ключевое слово
            "check_organic": getattr(settings, 'check_organic', False),
            "sku": getattr(settings, 'sku', None) # SKU нужен для проверки органики
        }
        self.campaign_id = settings.campaign_id
        self.is_active = settings.is_active

    async def process_campaign(self):
        if not self.is_active: return

        campaign_key = f"bidder:state:{self.campaign_id}"
        keyword = self.settings.get('keyword')
        
        # 1. Получаем РЕАЛЬНЫЙ Аукцион (Catalog Ads)
        # Это критически важно для работы с реальными значениями
        auction_data = []
        if keyword:
            auction_data = await wb_api_service.get_auction_cpm(keyword)
        else:
            logger.warning(f"Camp {self.campaign_id}: No keyword specified for bidder.")

        # 2. Определяем нашу позицию и позицию конкурента из аукциона
        current_pos = 100
        current_real_cpm = 0
        competitor_bid = None

        if auction_data:
            # Ищем себя
            my_ad = next((x for x in auction_data if x['id'] == self.campaign_id), None)
            if my_ad:
                current_pos = my_ad['pos']
                current_real_cpm = my_ad['cpm']
            
            # Ищем конкурента на целевой позиции
            # target_pos 1 -> index 0
            target_idx = self.settings['target_pos'] - 1
            if len(auction_data) > target_idx:
                competitor_bid = auction_data[target_idx]['cpm']
            elif auction_data:
                # Конкурентов меньше, чем цель -> берем последнего
                competitor_bid = auction_data[-1]['cpm']
        else:
            # Если аукцион пуст или не получен, фоллбэк на внутреннее инфо (менее точно)
            info = await wb_api_service.get_current_bid_info(self.token, self.campaign_id)
            current_pos = info.get('position', 100)

        # 3. Проверка органики (Safety Layer)
        if self.settings.get('check_organic') and keyword and self.settings.get('sku'):
            # Проверяем, где мы в органике
            org_res = await parser_service.get_search_position_v2(keyword, self.settings['sku'])
            if org_res.get('organic_pos', 999) <= self.settings['target_pos']:
                # Мы и так в топе, ставим минимум
                await self._execute_update(self.settings['min_bid'], current_real_cpm, current_pos, "Organic is good")
                return

        # 4. Fetch Stats for CPA Guard
        stats = await wb_api_service.get_advert_stats(self.token, self.campaign_id)
        if not stats:
            stats = {"ctr": 1.5, "views": 0, "cr": 0.03}

        # 5. Load & Update PID
        integral, prev_meas, last_update = 0.0, None, 0.0
        if r_client:
            state = r_client.hgetall(campaign_key)
            if state:
                integral = float(state.get('integral', 0.0))
                prev_meas = float(state.get('prev_meas')) if state.get('prev_meas') else None
                last_update = float(state.get('last_update', 0.0))

        now = datetime.now().timestamp()
        dt = now - last_update if last_update > 0 else 1.0

        pid = PIDController(
            kp=1.0, ki=0.1, kd=0.05,
            target_pos=self.settings['target_pos'],
            min_bid=self.settings['min_bid'],
            max_bid=self.settings['max_bid']
        )
        pid.load_state(integral, prev_meas)
        # В качестве текущей ставки для PID лучше брать реальную ставку из аукциона, если есть
        base_bid_for_pid = current_real_cpm if current_real_cpm > 0 else self.settings['min_bid']
        pid_bid = pid.update(current_pos, base_bid_for_pid, dt)

        # 6. Strategy Decision
        strategy_manager = StrategyManager(self.settings)
        final_bid, action_reason = strategy_manager.decide_bid(
            pid_bid=pid_bid,
            current_metrics={"ctr": stats.get('ctr', 0), "cr": stats.get('cr', 0)},
            competitor_bid=competitor_bid # <-- ТЕПЕРЬ ПЕРЕДАЕМ РЕАЛЬНУЮ СТАВКУ КОНКУРЕНТА
        )

        # 7. Save PID State
        new_integral, new_prev_meas = pid.get_state()
        if r_client:
            r_client.hset(campaign_key, mapping={
                'integral': new_integral,
                'prev_meas': new_prev_meas if new_prev_meas else '',
                'last_update': now
            })
            r_client.expire(campaign_key, 3600)

        # 8. Execute
        # Получаем текущую ставку из API WB (она может отличаться от аукциона) для сравнения
        # Но для метода update нам важно просто знать, изменилась ли она от нашего решения
        await self._execute_update(final_bid, base_bid_for_pid, current_pos, action_reason)

    async def _execute_update(self, new_bid, current_bid, current_pos, reason):
        if new_bid != current_bid:
            await wb_api_service.update_bid(self.token, self.campaign_id, new_bid)
            logger.info(f"Camp {self.campaign_id}: {current_bid} -> {new_bid} ({reason})")
        else:
            reason = "hold"
            
        log_bidder_action_sync(
            self.user_id, self.campaign_id, current_pos, 
            self.settings['target_pos'], current_bid, new_bid, reason
        )

@celery_app.task(name="bidder_producer_task")
def bidder_producer_task():
    """Finds active campaigns in DB and launches workers."""
    session = SyncSessionLocal()
    try:
        active_settings = session.query(BidderSettings).filter(BidderSettings.is_active == True).all()
        logger.info(f"Bidder Producer: Found {len(active_settings)} active campaigns.")
        
        for setting in active_settings:
            user = session.query(User).filter(User.id == setting.user_id).first()
            if user and user.wb_api_token:
                bidder_consumer_task.delay(user.id, user.wb_api_token, setting.campaign_id)
    finally:
        session.close()

@celery_app.task(bind=True, name="bidder_consumer_task")
def bidder_consumer_task(self, user_id: int, token: str, campaign_id: int):
    session = SyncSessionLocal()
    try:
        setting = session.query(BidderSettings).filter(
            BidderSettings.campaign_id == campaign_id, 
            BidderSettings.user_id == user_id
        ).first()
        
        if not setting: return

        worker = BidderWorker(user_id, token, setting)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(worker.process_campaign())
        loop.close()
    except Exception as e:
        logger.error(f"Bidder Worker Error for Camp {campaign_id}: {e}")
    finally:
        session.close()