"""
Subscription Plans and Add-ons Configuration for JuicyStat
"""

TIERS = {
    "start": {
        "name": "Start (Free)",
        "price": 0,
        "limits": {
            "ai_requests": 5, 
            "history_days": 7, 
            "cluster_requests": 0, 
            "review_analysis_limit": 30,
            "min_summary_interval": 24 # Только раз в сутки
        },
        "features": ["slots", "notifications", "pnl_demo"]
    },
    "analyst": {
        "name": "Analyst (Pro)",
        "price": 1490,
        "limits": {
            "ai_requests": 100, 
            "history_days": 60, 
            "cluster_requests": 50, 
            "review_analysis_limit": 100,
            "min_summary_interval": 3 # Раз в 3 часа
        },
        "features": ["slots", "notifications", "pnl_full", "forensics", "seo_semantics", "unit_economy"]
    },
    "strategist": {
        "name": "Strategist (Business)",
        "price": 4990,
        "limits": {
            "ai_requests": 1000, 
            "history_days": 365, 
            "cluster_requests": 200, 
            "review_analysis_limit": 200,
            "min_summary_interval": 1 # Раз в час
        },
        "features": ["slots", "notifications", "pnl_full", "pnl_export", "forensics", "forensics_cashgap", "priority_poll", "seo_semantics", "unit_economy"]
    }
}

ADDONS = {
    "extra_ai_100": {"resource": "ai_requests", "amount": 100, "price": 490}
}


def get_plan_config(plan_key: str) -> dict:
    """
    Get configuration for a subscription plan.
    """
    if not plan_key or plan_key not in TIERS:
         if plan_key == 'free': return TIERS.get('start')
         return TIERS.get('start')
         
    return TIERS.get(plan_key, {})


def has_feature(plan_key: str, feature_flag: str) -> bool:
    """
    Check if a plan includes a specific feature.
    """
    plan = get_plan_config(plan_key)
    features = plan.get("features", [])
    return feature_flag in features


def get_limit(plan_key: str, resource_key: str) -> int:
    """
    Get resource limit for a plan.
    """
    plan = get_plan_config(plan_key)
    limits = plan.get("limits", {})
    return limits.get(resource_key, 0)