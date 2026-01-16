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
    except Exception as e:
        # If direct import fails, try using importlib with different approach
        # We need to use a different name to avoid circular import
        spec = importlib.util.spec_from_file_location("_deps_file_module_fallback", _deps_file)
        _deps_module = importlib.util.module_from_spec(spec)
        sys.modules['_deps_file_module_fallback'] = _deps_module
        spec.loader.exec_module(_deps_module)
        get_current_user = _deps_module.get_current_user
        get_redis_client = _deps_module.get_redis_client
        auth_manager = _deps_module.auth_manager
        SUPER_ADMIN_IDS = _deps_module.SUPER_ADMIN_IDS
        r_client = _deps_module.r_client
else:
    # Fallback if file doesn't exist - shouldn't happen
    raise ImportError("dependencies.py file not found")

# Export quota module functions (lazy import to avoid circular dependency)
# Import quota module functions at the end after we've defined get_current_user and get_redis_client

__all__ = [
    'get_current_user',
    'get_redis_client',
    'auth_manager',
    'SUPER_ADMIN_IDS',
    'r_client',
    'QuotaCheck',
    'increment_usage'
]

# Import quota module at the end (after all exports are defined)
# Use try-except to avoid breaking imports if quota module has issues
try:
    from .quota import QuotaCheck, increment_usage
except ImportError as e:
    # If quota import fails, set to None or re-raise based on needs
    # For now, we'll re-raise to see what the issue is
    raise ImportError(f"Failed to import quota module: {e}") from e
