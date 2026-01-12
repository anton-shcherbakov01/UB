import logging
import asyncio
import redis
from datetime import datetime
from typing import Dict, Any, Optional

from celery_app import celery_app, REDIS_URL
from wb_api_service import wb_api_service
from database import SyncSessionLocal, User, BidderSettings
from bidder_engine import PIDController
from .utils import log_bidder_action_sync

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
            "strategy": settings.strategy
        }
        self.campaign_id = settings.campaign_id
        self.is_active = settings.is_active

    async def process_campaign(self):
        if not self.is_active: return

        campaign_key = f"bidder:state:{self.campaign_id}"
        
        # 1. Fetch Stats for CPA Guard (CTR, Conversions)
        stats = await wb_api_service.get_advert_stats(self.token, self.campaign_id)
        if not stats:
            logger.warning(f"No stats for campaign {self.campaign_id}")
            stats = {"ctr": 1.5, "views": 0} # Safe defaults

        # 2. Get Current Auction State
        info = await wb_api_service.get_current_bid_info(self.token, self.campaign_id)
        current_bid = info.get('price', 0)
        current_pos = info.get('position', 100)
        
        # 3. Load PID State
        integral, prev_meas, last_update = 0.0, None, 0.0
        if r_client:
            state = r_client.hgetall(campaign_key)
            if state:
                integral = float(state.get('integral', 0.0))
                prev_meas = float(state.get('prev_meas')) if state.get('prev_meas') else None
                last_update = float(state.get('last_update', 0.0))

        now = datetime.now().timestamp()
        dt = now - last_update if last_update > 0 else 1.0

        # 4. PID Calculation
        pid = PIDController(
            target_pos=self.settings['target_pos'],
            min_bid=self.settings['min_bid'],
            max_bid=self.settings['max_bid']
        )
        pid.load_state(integral, prev_meas)
        pid_bid = pid.update(current_pos, current_bid, dt)

        # 5. Strategy & Safety Layer
        strategy_manager = StrategyManager(self.settings)
        # Assuming conversion rate ~ 3% if not available
        conv_rate = stats.get('cr', 0.03) 
        
        final_bid, action_reason = strategy_manager.decide_bid(
            pid_bid=pid_bid,
            current_metrics={"ctr": stats.get('ctr', 0), "cr": conv_rate},
            competitor_bid=None 
        )

        # 6. Save State
        new_integral, new_prev_meas = pid.get_state()
        if r_client:
            r_client.hset(campaign_key, mapping={
                'integral': new_integral,
                'prev_meas': new_prev_meas if new_prev_meas else '',
                'last_update': now
            })
            r_client.expire(campaign_key, 3600)

        # 7. Execute Update
        if final_bid != current_bid:
            await wb_api_service.update_bid(self.token, self.campaign_id, final_bid)
            logger.info(f"Camp {self.campaign_id}: {current_bid} -> {final_bid} ({action_reason})")
        else:
            action_reason = "hold"

        # 8. Log
        log_bidder_action_sync(
            self.user_id, self.campaign_id, current_pos, 
            self.settings['target_pos'], current_bid, final_bid, action_reason
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