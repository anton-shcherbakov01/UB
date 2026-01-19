"""
Dependencies package - re-exports from dependencies.py and quota module
"""
import sys
import os
import importlib.util

# Import from parent directory's dependencies.py file directly
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_deps_file = os.path.join(_parent_dir, 'dependencies.py')

# Ensure parent directory is in sys.path
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Import from the file directly to avoid module name conflict
if os.path.exists(_deps_file):
    try:
        spec = importlib.util.spec_from_file_location("_dependencies_file_module", _deps_file)
        _deps_module = importlib.util.module_from_spec(spec)
        # Use a unique name in sys.modules to avoid conflicts
        sys.modules['_dependencies_file_module'] = _deps_module
        spec.loader.exec_module(_deps_module)
        
        # Export functions from dependencies.py
        get_current_user = _deps_module.get_current_user
        get_redis_client = _deps_module.get_redis_client
        auth_manager = _deps_module.auth_manager
        SUPER_ADMIN_IDS = _deps_module.SUPER_ADMIN_IDS
        r_client = _deps_module.r_client
        
        # Try to export check_telegram_auth if it exists (for PDF downloads)
        check_telegram_auth = getattr(_deps_module, 'check_telegram_auth', None)
        
    except Exception as e:
        # If direct import fails, try using importlib with different approach
        # We need to use a different name to avoid circular import
        spec = importlib.util.spec_from_file_location("_deps_file_module_fallback", _deps_file)
        _deps_module = importlib.util.module_from_spec(spec)
        sys.modules['_deps_file_module_fallback'] = _deps_module
        spec.loader.exec_module(_deps_module)
        
        get_current_user = getattr(_deps_module, 'get_current_user', None)
        get_redis_client = getattr(_deps_module, 'get_redis_client', None)
        auth_manager = getattr(_deps_module, 'auth_manager', None)
        SUPER_ADMIN_IDS = getattr(_deps_module, 'SUPER_ADMIN_IDS', [])
        r_client = getattr(_deps_module, 'r_client', None)
        check_telegram_auth = getattr(_deps_module, 'check_telegram_auth', None)
else:
    # Fallback if file doesn't exist - shouldn't happen
    raise ImportError("dependencies.py file not found")

# Import get_db from database.py (needed for backward compatibility with routers that import from dependencies)
# This should be imported after _deps_module is loaded to avoid circular dependencies
try:
    from database import get_db
except ImportError:
    # If database import fails, we'll handle it later
    get_db = None

# Fallback implementation for check_telegram_auth if missing
if check_telegram_auth is None:
    async def check_telegram_auth(init_data: str, db):
        """
        Fallback authentication logic for Telegram WebApp data.
        Validates the hash and returns the user.
        """
        import hashlib
        import hmac
        import json
        from urllib.parse import parse_qsl
        from fastapi import HTTPException
        from sqlalchemy import select
        
        # Try to get bot token from environment
        token = os.getenv("BOT_TOKEN")
        if not token:
            print("Error: BOT_TOKEN not found for auth fallback")
            raise HTTPException(status_code=500, detail="Auth configuration error: BOT_TOKEN missing")

        try:
            # Parse init_data
            parsed_data = dict(parse_qsl(init_data))
            hash_ = parsed_data.pop('hash', None)
            if not hash_:
                return None
            
            # Sort and calculate hash
            data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
            secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
            calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
            
            if calculated_hash != hash_:
                return None
                
            user_data_str = parsed_data.get('user')
            if not user_data_str:
                return None
                
            user_data = json.loads(user_data_str)
            user_id = user_data.get('id')
            if not user_id:
                return None
            
            # Import User model here to avoid circular imports at module level
            from database import User
            
            # DB Lookup
            result = await db.execute(select(User).where(User.telegram_id == user_id))
            user = result.scalars().first()
            return user
            
        except Exception as e:
            print(f"Auth Fallback Error: {e}")
            return None

# Export quota module functions (lazy import to avoid circular dependency)
# Import quota module functions at the end after we've defined get_current_user and get_redis_client

__all__ = [
    'get_current_user',
    'get_redis_client',
    'get_db',
    'auth_manager',
    'SUPER_ADMIN_IDS',
    'r_client',
    'QuotaCheck',
    'increment_usage',
    'check_telegram_auth'
]

# Import quota module at the end (after all exports are defined)
# Use try-except to avoid breaking imports if quota module has issues
try:
    from .quota import QuotaCheck, increment_usage
except ImportError as e:
    # If quota import fails, set to None or re-raise based on needs
    # For now, we'll re-raise to see what the issue is
    raise ImportError(f"Failed to import quota module: {e}") from e