import json
import logging
from datetime import datetime
from celery.result import AsyncResult
from database import SyncSessionLocal, MonitoredItem, PriceHistory, SearchHistory, SeoPosition, BidderLog
from celery_app import celery_app

logger = logging.getLogger("Tasks-Utils")

def get_status(task_id: str):
    """
    Получение статуса задачи Celery.
    Используется в polling-запросах на фронтенде.
    """
    res = AsyncResult(task_id, app=celery_app)
    resp = {"task_id": task_id, "status": res.status}
    
    if res.status == 'SUCCESS':
        resp["data"] = res.result
    elif res.status == 'FAILURE':
        resp["error"] = str(res.result)
    elif res.status == 'PROGRESS':
        resp["info"] = res.info.get('status', 'Processing')
        
    return resp

def save_history_sync(user_id, sku, type, title, result_data):
    if not user_id: return
    session = SyncSessionLocal()
    try:
        if isinstance(result_data, dict):
            json_str = json.dumps(result_data, ensure_ascii=False)
        else:
            json_str = str(result_data)
            
        h = SearchHistory(user_id=user_id, sku=sku, request_type=type, title=title, result_json=json_str)
        session.add(h)
        session.commit()
    except Exception as e:
        logger.error(f"History DB error: {e}")
        session.rollback()
    finally:
        session.close()

def save_price_sync(sku, data):
    if data.get("status") == "error": return
    session = SyncSessionLocal()
    try:
        item = session.query(MonitoredItem).filter(MonitoredItem.sku == sku).first()
        if item:
            item.name = data.get("name")
            item.brand = data.get("brand")
            
            p = data.get("prices", {})
            ph = PriceHistory(
                item_id=item.id,
                wallet_price=p.get("wallet_purple", 0),
                standard_price=p.get("standard_black", 0),
                base_price=p.get("base_crossed", 0)
            )
            session.add(ph)
            session.commit()
            logger.info(f"DB: Updated price for {sku}")
    except Exception as e:
        logger.error(f"Price DB Error: {e}")
        session.rollback()
    finally:
        session.close()

def save_seo_position_sync(user_id, sku, keyword, position):
    session = SyncSessionLocal()
    try:
        pos_entry = session.query(SeoPosition).filter(
            SeoPosition.user_id == user_id, 
            SeoPosition.sku == sku, 
            SeoPosition.keyword == keyword
        ).first()
        
        if pos_entry:
            pos_entry.position = position
            pos_entry.last_check = datetime.utcnow()
        else:
            pos_entry = SeoPosition(user_id=user_id, sku=sku, keyword=keyword, position=position)
            session.add(pos_entry)
        session.commit()
    except Exception as e:
        logger.error(f"SEO DB Error: {e}")
        session.rollback()
    finally:
        session.close()

def log_bidder_action_sync(user_id, campaign_id, current_pos, target_pos, prev_bid, calc_bid, action):
    session = SyncSessionLocal()
    try:
        saved = (prev_bid - calc_bid) if (prev_bid and calc_bid) else 0
        log = BidderLog(
            user_id=user_id, campaign_id=campaign_id, current_pos=current_pos,
            target_pos=target_pos, previous_bid=prev_bid, calculated_bid=calc_bid,
            saved_amount=saved, action=action
        )
        session.add(log)
        session.commit()
    except Exception as e:
        logger.error(f"Bidder Log DB Error: {e}")
    finally:
        session.close()