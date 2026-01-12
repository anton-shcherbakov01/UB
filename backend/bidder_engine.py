import logging
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger("BidderEngine")

class PIDController:
    """
    Production-grade PID Controller.
    Features: Anti-Windup, Deadband, Output Clamping.
    """
    def __init__(
        self, 
        kp: float = 1.5, 
        ki: float = 0.1, 
        kd: float = 0.5, 
        target_pos: int = 1, 
        min_bid: int = 125, 
        max_bid: int = 1000,
        deadband: int = 1
    ):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.target_pos = target_pos
        self.min_bid = min_bid
        self.max_bid = max_bid
        self.deadband = deadband

        # State vars
        self._integral = 0.0
        self._prev_measurement: Optional[float] = None

    def load_state(self, integral: float, prev_measurement: Optional[float]):
        """Restores state from Redis."""
        self._integral = integral
        self._prev_measurement = prev_measurement

    def get_state(self) -> Tuple[float, Optional[float]]:
        """Returns state for persistence."""
        return self._integral, self._prev_measurement

    def update(self, current_pos: int, current_bid: int, dt: float) -> int:
        if dt <= 0: return current_bid

        # Error: In ranking, lower is better. 
        # If Target=1, Current=5 -> Error = 5-1 = 4 (Positive error means we need HIGHER bid)
        error = current_pos - self.target_pos

        # Deadband: if we are close enough, don't jitter
        if abs(error) <= self.deadband:
            return current_bid

        # P-term
        p_term = self.kp * error

        # I-term with Anti-Windup
        self._integral += self.ki * error * dt
        # Clamp integral to 50% of bid range to prevent deep saturation
        integral_limit = (self.max_bid - self.min_bid) * 0.5
        self._integral = max(-integral_limit, min(self._integral, integral_limit))
        i_term = self._integral

        # D-term (Derivative on Measurement to prevent kicks)
        if self._prev_measurement is None:
            self._prev_measurement = current_pos
        
        derivative = (current_pos - self._prev_measurement) / dt
        d_term = -self.kd * derivative
        self._prev_measurement = current_pos

        # Output
        adjustment = p_term + i_term + d_term
        new_bid = int(current_bid + adjustment)

        # Clamping
        return max(self.min_bid, min(new_bid, self.max_bid))

class StrategyManager:
    """
    Business Logic Layer for Bidding.
    Handles Financial Safety Guards (CPA) and Competitor Shadowing.
    """
    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings
        self.target_cpa = settings.get('target_cpa', 0)
        self.max_cpm = settings.get('max_cpm', 2000)
        self.strategy = settings.get('strategy', 'pid')

    def calculate_safety_cap(self, ctr: float, conversion_rate: float) -> int:
        """
        Calculates the maximum allowable bid based on Unit Economics.
        Formula: Max_CPM = Target_CPA * CR * CTR * 1000
        Example: CPA=500 rub, CR=5% (0.05), CTR=3% (0.03)
        Max_CPM = 500 * 0.05 * 0.03 * 1000 = 750 rub.
        """
        if self.target_cpa <= 0:
            return self.max_cpm

        # Fallback defaults if metrics are missing/zero
        safe_ctr = ctr if ctr > 0 else 0.015 # 1.5% fallback
        safe_cr = conversion_rate if conversion_rate > 0 else 0.03 # 3% fallback

        # Economic Limit
        economic_limit = int(self.target_cpa * safe_cr * safe_ctr * 1000)
        
        # Absolute Limit (Safety Net)
        return min(economic_limit, self.max_cpm)

    def apply_shadowing(self, competitor_bid: int) -> int:
        """Strategy: Always bid 1 ruble more than competitor."""
        bid = competitor_bid + 1
        return max(self.settings.get('min_bid', 125), min(bid, self.settings.get('max_bid', 1000)))

    def decide_bid(
        self, 
        pid_bid: int, 
        current_metrics: Dict[str, float],
        competitor_bid: Optional[int] = None
    ) -> Tuple[int, str]:
        """
        Final decision making.
        Returns: (Final Bid, Reason/Log Action)
        """
        ctr = current_metrics.get('ctr', 0) / 100.0 # API gives percents (5.5)
        cr = current_metrics.get('cr', 0)
        
        # 1. Calculate Safety Cap
        safety_cap = self.calculate_safety_cap(ctr, cr)
        
        # 2. Determine Proposed Bid
        proposed_bid = pid_bid
        if self.strategy == 'shadowing' and competitor_bid:
            proposed_bid = self.apply_shadowing(competitor_bid)
        
        # 3. Apply Safety Guard
        final_bid = proposed_bid
        reason = "update"

        if proposed_bid > safety_cap:
            final_bid = safety_cap
            reason = "cpa_guard_cap"
            logger.info(f"Bid capped by CPA Guard: Proposed {proposed_bid} -> Capped {final_bid} (TargetCPA: {self.target_cpa})")

        return final_bid, reason