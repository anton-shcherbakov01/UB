"""
Quota and Resource Management Dependency for FastAPI
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db, User
# Import directly from dependencies.py file to avoid circular dependency with __init__.py
import sys
import os
import importlib.util

# Get path to parent dependencies.py file
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_deps_file = os.path.join(_parent_dir, 'dependencies.py')

# Import from the file directly
if os.path.exists(_deps_file):
    spec = importlib.util.spec_from_file_location("_deps_file_module", _deps_file)
    _deps_file_module = importlib.util.module_from_spec(spec)
    sys.modules['_deps_file_module'] = _deps_file_module
    spec.loader.exec_module(_deps_file_module)
    get_current_user = _deps_file_module.get_current_user
    get_redis_client = _deps_file_module.get_redis_client
else:
    # Fallback: import from parent package
    if _parent_dir not in sys.path:
        sys.path.insert(0, _parent_dir)
    # Use importlib to load the file directly, not the package
    spec = importlib.util.spec_from_file_location("_deps_file_module_fallback", _deps_file)
    _deps_file_module = importlib.util.module_from_spec(spec)
    sys.modules['_deps_file_module_fallback'] = _deps_file_module
    spec.loader.exec_module(_deps_file_module)
    get_current_user = _deps_file_module.get_current_user
    get_redis_client = _deps_file_module.get_redis_client

from config.plans import get_plan_config, has_feature, get_limit

logger = logging.getLogger("Quota")


class QuotaCheck:
    """
    Dependency for checking subscription quotas and features.
    
    Usage:
        @router.post("/endpoint")
        async def my_endpoint(
            user: User = Depends(QuotaCheck("ai_requests", "pnl_full"))
        ):
            ...
    """
    
    def __init__(self, resource_key: Optional[str] = None, feature_flag: Optional[str] = None):
        """
        Initialize quota check.
        
        Args:
            resource_key: Resource to check (e.g., "ai_requests")
            feature_flag: Feature flag to check (e.g., "pnl_full")
        """
        self.resource_key = resource_key
        self.feature_flag = feature_flag
    
    async def __call__(
        self,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        """
        Check quota and feature access.
        
        Returns:
            User object if checks pass
            
        Raises:
            HTTPException 403 if quota exhausted or feature missing
        """
        # 1. Check feature flag if provided
        if self.feature_flag:
            plan_config = get_plan_config(user.subscription_plan)
            if not has_feature(user.subscription_plan, self.feature_flag):
                raise HTTPException(
                    status_code=403,
                    detail=f"Feature '{self.feature_flag}' requires upgrade. Current plan: {plan_config.get('name', user.subscription_plan)}"
                )
        
        # 2. Check resource limits if provided
        if self.resource_key:
            # Ensure usage_reset_date is set
            if not user.usage_reset_date:
                user.usage_reset_date = datetime.utcnow()
                db.add(user)
                await db.commit()
            
            # Check if monthly reset is needed
            now = datetime.utcnow()
            if user.usage_reset_date and now > user.usage_reset_date:
                # Reset monthly usage
                days_passed = (now - user.usage_reset_date).days
                if days_passed >= 30:
                    # Reset usage for ai_requests if that's the resource being checked
                    if self.resource_key == "ai_requests":
                        user.ai_requests_used = 0
                    # Set next reset date (30 days from now)
                    user.usage_reset_date = now + timedelta(days=30)
                    db.add(user)
                    await db.commit()
            
            # Get limit from plan
            monthly_limit = get_limit(user.subscription_plan, self.resource_key)
            
            # Check usage
            if self.resource_key == "ai_requests":
                # Initialize values if None
                if user.ai_requests_used is None:
                    user.ai_requests_used = 0
                if user.extra_ai_balance is None:
                    user.extra_ai_balance = 0
                
                # Check monthly limit first
                if user.ai_requests_used >= monthly_limit:
                    # Check extra balance
                    if user.extra_ai_balance <= 0:
                        plan_config = get_plan_config(user.subscription_plan)
                        raise HTTPException(
                            status_code=403,
                            detail=f"AI requests quota exhausted ({user.ai_requests_used}/{monthly_limit}). Upgrade or purchase add-on."
                        )
                # If we have extra balance, we can proceed (will consume from balance)
            # Add other resource types here as needed
        
        return user


async def increment_usage(
    user: User,
    resource_key: str,
    amount: int = 1,
    db: Optional[AsyncSession] = None
) -> None:
    """
    Increment usage counter for a resource.
    Consumes monthly limit first, then extra balance.
    
    Args:
        user: User object
        resource_key: Resource type (e.g., "ai_requests")
        amount: Amount to increment (default 1)
        db: Database session (optional, will create if not provided)
    """
    if resource_key == "ai_requests":
        # Initialize values if None
        if user.ai_requests_used is None:
            user.ai_requests_used = 0
        if user.extra_ai_balance is None:
            user.extra_ai_balance = 0
        
        # Get limit from plan
        monthly_limit = get_limit(user.subscription_plan, resource_key)
        
        # Check if we need to consume from monthly limit or extra balance
        remaining_monthly = monthly_limit - user.ai_requests_used
        
        if remaining_monthly >= amount:
            # Consume from monthly limit
            user.ai_requests_used += amount
        else:
            # Consume remaining from monthly, rest from extra balance
            consumed_from_monthly = remaining_monthly
            consumed_from_balance = amount - consumed_from_monthly
            
            user.ai_requests_used = monthly_limit  # Exhaust monthly limit
            user.extra_ai_balance = max(0, user.extra_ai_balance - consumed_from_balance)
        
        # Update Redis cache for fast reads
        r_client = get_redis_client()
        if r_client:
            try:
                cache_key = f"quota:{user.id}:{resource_key}"
                r_client.setex(
                    cache_key,
                    3600,  # 1 hour TTL
                    f"{user.ai_requests_used}:{user.extra_ai_balance}"
                )
            except Exception as e:
                logger.warning(f"Redis cache update failed: {e}")
        
        # Update database
        if db:
            # Use merge to ensure user is in session (works whether user is tracked or not)
            # This is safer than add() which would fail if user is already in session
            merged_user = await db.merge(user)
            
            # Flush to ensure changes are written to the database (but don't commit yet)
            await db.flush()
            # Commit the transaction
            await db.commit()
            # Refresh specific attributes to get latest values from database
            await db.refresh(merged_user, attribute_names=["ai_requests_used", "extra_ai_balance", "usage_reset_date"])
            
            # Update original user object with merged values
            user.ai_requests_used = merged_user.ai_requests_used
            user.extra_ai_balance = merged_user.extra_ai_balance
            user.usage_reset_date = merged_user.usage_reset_date
            
            logger.info(f"Updated usage for user {user.id}: ai_requests_used={user.ai_requests_used}, extra_ai_balance={user.extra_ai_balance}")
        else:
            # If no db session provided, we need to create one and fetch user fresh
            from database import AsyncSessionLocal
            from sqlalchemy import select
            async with AsyncSessionLocal() as session:
                # Fetch user fresh from database to ensure we have the latest state
                result = await session.execute(select(User).where(User.id == user.id))
                fresh_user = result.scalar_one()
                
                # Update the fresh user object
                if resource_key == "ai_requests":
                    if fresh_user.ai_requests_used is None:
                        fresh_user.ai_requests_used = 0
                    if fresh_user.extra_ai_balance is None:
                        fresh_user.extra_ai_balance = 0
                    
                    monthly_limit = get_limit(fresh_user.subscription_plan, resource_key)
                    remaining_monthly = monthly_limit - fresh_user.ai_requests_used
                    
                    if remaining_monthly >= amount:
                        fresh_user.ai_requests_used += amount
                    else:
                        consumed_from_monthly = remaining_monthly
                        consumed_from_balance = amount - consumed_from_monthly
                        fresh_user.ai_requests_used = monthly_limit
                        fresh_user.extra_ai_balance = max(0, fresh_user.extra_ai_balance - consumed_from_balance)
                
                session.add(fresh_user)
                await session.flush()
                await session.commit()
                await session.refresh(fresh_user, attribute_names=["ai_requests_used", "extra_ai_balance", "usage_reset_date"])
                
                # Update the original user object with fresh values
                user.ai_requests_used = fresh_user.ai_requests_used
                user.extra_ai_balance = fresh_user.extra_ai_balance
                user.usage_reset_date = fresh_user.usage_reset_date
    
    # Add other resource types here as needed

