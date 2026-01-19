"""
Queue Service for managing task queues with priorities
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from dependencies import get_redis_client
from config.plans import has_feature

logger = logging.getLogger("QueueService")


class QueueService:
    """
    Service for managing task queues with priorities.
    Strategist users get priority queue, others get normal queue.
    """
    
    def __init__(self):
        self.redis_client = get_redis_client()
        self.priority_queue_key = "queue:priority"
        self.normal_queue_key = "queue:normal"
        self.task_info_prefix = "task:info:"
        self.user_position_prefix = "user:position:"
    
    def _get_queue_key(self, user_plan: str) -> str:
        """Get queue key based on user plan"""
        if has_feature(user_plan, "priority_poll"):
            return self.priority_queue_key
        return self.normal_queue_key
    
    def add_task_to_queue(
        self, 
        task_id: str, 
        user_id: int, 
        user_plan: str,
        task_type: str = "ai_analysis"
    ) -> Dict[str, Any]:
        """
        Add task to appropriate queue and return position info.
        
        Returns:
            {
                "queue": "priority" or "normal",
                "position": int,
                "task_id": str
            }
        """
        if not self.redis_client:
            logger.warning("Redis client not available, skipping queue management")
            return {
                "queue": "normal",
                "position": 0,
                "task_id": task_id,
                "is_priority": False
            }
        
        queue_key = self._get_queue_key(user_plan)
        is_priority = queue_key == self.priority_queue_key
        
        try:
            # Add task to queue
            position = self.redis_client.rpush(queue_key, task_id)
            
            # Store task info
            task_info = {
                "task_id": task_id,
                "user_id": user_id,
                "user_plan": user_plan,
                "task_type": task_type,
                "created_at": datetime.utcnow().isoformat(),
                "queue": "priority" if is_priority else "normal"
            }
            self.redis_client.setex(
                f"{self.task_info_prefix}{task_id}",
                3600,  # 1 hour TTL
                str(task_info)
            )
            
            # Store user position
            self.redis_client.setex(
                f"{self.user_position_prefix}{user_id}:{task_id}",
                3600,
                str(position)
            )
            
            logger.info(f"Task {task_id} added to {queue_key} at position {position}")
            
            return {
                "queue": "priority" if is_priority else "normal",
                "position": position,
                "task_id": task_id,
                "is_priority": is_priority
            }
        except Exception as e:
            logger.error(f"Error adding task to queue: {e}", exc_info=True)
            return {
                "queue": "normal",
                "position": 0,
                "task_id": task_id,
                "is_priority": False
            }
    
    def get_task_position(self, task_id: str, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get current position of task in queue.
        
        Returns:
            {
                "position": int,
                "queue": "priority" or "normal",
                "is_priority": bool,
                "total_in_queue": int
            } or None if task not found
        """
        if not self.redis_client:
            return None
        
        try:
            # Try to get from stored position
            position_key = f"{self.user_position_prefix}{user_id}:{task_id}"
            stored_position = self.redis_client.get(position_key)
            
            if stored_position:
                position = int(stored_position)
                # Check which queue it's in
                priority_pos = self.redis_client.lpos(self.priority_queue_key, task_id)
                normal_pos = self.redis_client.lpos(self.normal_queue_key, task_id)
                
                if priority_pos is not None:
                    queue = "priority"
                    total = self.redis_client.llen(self.priority_queue_key)
                    is_priority = True
                elif normal_pos is not None:
                    queue = "normal"
                    total = self.redis_client.llen(self.normal_queue_key)
                    is_priority = False
                else:
                    # Task already processed
                    return None
                
                return {
                    "position": position,
                    "queue": queue,
                    "is_priority": is_priority,
                    "total_in_queue": total
                }
        except Exception as e:
            logger.error(f"Error getting task position: {e}", exc_info=True)
        
        return None
    
    def remove_task_from_queue(self, task_id: str) -> bool:
        """Remove task from queue after processing"""
        if not self.redis_client:
            return False
        
        try:
            removed_priority = self.redis_client.lrem(self.priority_queue_key, 1, task_id)
            removed_normal = self.redis_client.lrem(self.normal_queue_key, 1, task_id)
            
            # Clean up task info
            self.redis_client.delete(f"{self.task_info_prefix}{task_id}")
            
            return removed_priority > 0 or removed_normal > 0
        except Exception as e:
            logger.error(f"Error removing task from queue: {e}", exc_info=True)
            return False


# Singleton instance
queue_service = QueueService()

