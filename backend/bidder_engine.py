import time
from typing import Optional, Tuple

class PIDController:
    """
    Advanced PID Controller for Real-Time Bidding.
    Features:
    - Anti-Windup (Clamping)
    - Deadband (Dead zone)
    - Derivative Kick Prevention (Derivative on Measurement)
    - Output limiting (Min/Max Bid)
    """
    def __init__(
        self, 
        kp: float, 
        ki: float, 
        kd: float, 
        target_pos: int, 
        min_bid: int, 
        max_bid: int,
        deadband: int = 1
    ):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.target_pos = target_pos
        self.min_bid = min_bid
        self.max_bid = max_bid
        self.deadband = deadband

        # State (usually loaded from external storage in stateless systems)
        self._prev_error = 0.0
        self._integral = 0.0
        self._prev_measurement: Optional[float] = None

    def load_state(self, integral: float, prev_measurement: Optional[float]):
        """Load state from Redis/DB"""
        self._integral = integral
        self._prev_measurement = prev_measurement

    def get_state(self) -> Tuple[float, Optional[float]]:
        """Export state to save in Redis/DB"""
        return self._integral, self._prev_measurement

    def update(self, current_pos: int, current_bid: int, dt: float) -> int:
        """
        Calculates new bid based on position error.
        
        :param current_pos: Current position in auction (1, 2, 3...)
        :param current_bid: Current bid amount (Rubles)
        :param dt: Time delta in seconds since last update
        :return: New calculated bid
        """
        if dt <= 0:
            return current_bid

        # 1. Error Calculation
        # Note: In auction, lower position (1) is better. 
        # If target is 1 and current is 5, error = 5 - 1 = 4 (positive error means we need to increase bid)
        # If target is 5 and current is 1, error = 1 - 5 = -4 (negative error means we can decrease bid)
        error = current_pos - self.target_pos

        # 2. Deadband Check
        if abs(error) <= self.deadband:
            return current_bid

        # 3. Proportional Term
        p_term = self.kp * error

        # 4. Integral Term with Anti-Windup (Clamping)
        # We only accumulate if the output is not saturated, or if the error opposes the saturation
        self._integral += self.ki * error * dt
        
        # Clamp Integral directly to avoid infinite accumulation
        # Heuristic: Integral part shouldn't exceed 50% of the bid range swing
        integral_limit = (self.max_bid - self.min_bid) * 0.5
        self._integral = max(-integral_limit, min(self._integral, integral_limit))

        i_term = self._integral

        # 5. Derivative Term (Derivative on Measurement)
        # Prevents "Kick" when target changes, smooths the output
        if self._prev_measurement is None:
            self._prev_measurement = current_pos
            
        # d(Error)/dt = d(SetPoint - Measurement)/dt = - d(Measurement)/dt (assuming SetPoint is constant)
        derivative = (current_pos - self._prev_measurement) / dt
        d_term = -self.kd * derivative
        
        self._prev_measurement = current_pos

        # 6. Calculate Output
        # Base the change on the P-I-D output
        adjustment = p_term + i_term + d_term
        
        # New Bid = Current Bid + Adjustment
        # We cast to int because bids are usually integers
        new_bid = int(current_bid + adjustment)

        # 7. Output Limiting
        if new_bid < self.min_bid:
            new_bid = self.min_bid
        elif new_bid > self.max_bid:
            new_bid = self.max_bid

        return new_bid