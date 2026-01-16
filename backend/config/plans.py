"""
Subscription Plans and Add-ons Configuration for JuicyStat
"""

TIERS = {
    "start": {
        "name": "Start (Free)",
        "price": 0,
        "limits": {"ai_requests": 5, "history_days": 7},
        "features": ["slots", "notifications", "pnl_demo"]  # pnl_demo = yesterday only
    },
    "analyst": {
        "name": "Analyst (Pro)",
        "price": 1490,
        "limits": {"ai_requests": 100, "history_days": 60},
        "features": ["slots", "notifications", "pnl_full", "forensics"]
    },
    "strategist": {
        "name": "Strategist (Business)",
        "price": 4990,
        "limits": {"ai_requests": 1000, "history_days": 365},
        "features": ["slots", "notifications", "pnl_export", "forensics_cashgap", "priority_poll"]
    }
}

ADDONS = {
    "extra_ai_100": {"resource": "ai_requests", "amount": 100, "price": 490},
    "history_audit": {"feature": "deep_audit_pdf", "price": 990}
}


def get_plan_config(plan_key: str) -> dict:
    """
    Get configuration for a subscription plan.
    
    Args:
        plan_key: Plan identifier (start, analyst, strategist)
        
    Returns:
        Plan configuration dict or empty dict if not found
    """
    return TIERS.get(plan_key, {})


def has_feature(plan_key: str, feature_flag: str) -> bool:
    """
    Check if a plan includes a specific feature.
    
    Args:
        plan_key: Plan identifier
        feature_flag: Feature to check (e.g., "pnl_full", "forensics")
        
    Returns:
        True if feature is available, False otherwise
    """
    plan = get_plan_config(plan_key)
    features = plan.get("features", [])
    return feature_flag in features


def get_limit(plan_key: str, resource_key: str) -> int:
    """
    Get resource limit for a plan.
    
    Args:
        plan_key: Plan identifier
        resource_key: Resource type (e.g., "ai_requests", "history_days")
        
    Returns:
        Limit value or 0 if not found
    """
    plan = get_plan_config(plan_key)
    limits = plan.get("limits", {})
    return limits.get(resource_key, 0)

