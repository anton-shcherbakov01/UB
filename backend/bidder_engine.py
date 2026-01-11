# ================
# File: backend/bidder_engine.py
# ================
import time
from typing import Tuple, Dict

class PIDController:
    """
    Production-grade PID Controller for Real-Time Bidding.
    Features:
    - Anti-Windup (Clamping)
    - Deadband (Noise immunity)
    - Derivative on Measurement (Kick prevention)
    """

    def __init__(
        self, 
        kp: float, 
        ki: float, 
        kd: float, 
        target: float, 
        min_out: float, 
        max_out: float,
        deadband: float = 1.0
    ):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.target = target
        
        # Output limits (Bid limits)
        self.min_out = min_out
        self.max_out = max_out
        
        # Deadband threshold (Position tolerance)
        self.deadband = deadband

    def update(
        self, 
        current_val: float, 
        current_bid: float, 
        dt: float, 
        prev_error: float = 0.0, 
        integral: float = 0.0,
        prev_measurement: float = None
    ) -> Dict[str, float]:
        """
        Calculates the new bid based on position error.
        
        Args:
            current_val: Current Position (e.g., 5).
            current_bid: Current Bet in Rubles.
            dt: Time elapsed since last check (seconds).
            prev_error: Error from previous step (for standard D-term).
            integral: Accumulated integral term.
            prev_measurement: Previous position (for Derivative on Measurement).
        
        Returns:
            Dict containing: 'new_bid', 'p_term', 'i_term', 'd_term', 'error', 'integral'
        """
        
        # 1. Calculate Error
        # In auction: Lower position (1) is better. 
        # If Target=1, Current=5 -> Error = -(1 - 5) = 4 (Positive error means we need to INCREASE bid)
        # However, standard control theory implies Error = Setpoint - ProcessValue.
        # Let's map: 
        # We want to minimize Position. 
        # Error = Current_Pos - Target_Pos. 
        # If Current(5) > Target(1), Error is 4. We need positive output correction (increase bid).
        error = current_val - self.target

        # 2. Deadband Check
        # If we are very close to target (e.g. oscillating between pos 2 and 3), do nothing
        if abs(error) <= self.deadband:
            return {
                "new_bid": current_bid,
                "error": error,
                "integral": integral,
                "action": "hold"
            }

        # 3. Proportional Term
        p_term = self.kp * error

        # 4. Integral Term (with Anti-Windup via Clamping)
        # We only accumulate if logic requires it, but for Bidding, 
        # usually immediate reaction (P) is more important than history (I).
        # We clamp the integral sum to prevent it from growing indefinitely 
        # when the target is unreachable (e.g. max_bid limit hit).
        if dt > 0:
            integral += error * dt
            
            # Dynamic Clamping: The integral part shouldn't exceed 50% of the bid range alone
            # This is a heuristic to prevent "integral explosion"
            limit = (self.max_out - self.min_out) * 0.5
            integral = max(min(integral, limit), -limit)
            
        i_term = self.ki * integral

        # 5. Derivative Term (Derivative on Measurement)
        # Prevents "Derivative Kick" when target changes abruptly.
        # d(Error)/dt = d(Setpoint - PV)/dt. If Setpoint is constant, dError = -dPV.
        # We use change in measurement (Current Position).
        d_term = 0.0
        if dt > 0 and prev_measurement is not None:
            # Rate of change of position
            # If pos goes 5 -> 2 (improving), change is -3. 
            # D-term should oppose rapid changes to dampen overshoot.
            measurement_rate = (current_val - prev_measurement) / dt
            d_term = -self.kd * measurement_rate
        
        # 6. Compute Output (Delta or Absolute)
        # In this logic, PID produces the DELTA to be added to current bid
        # Because Auction is non-linear, P-controller estimates "How much to pay to jump gaps".
        # 1 position gap ~= roughly X rubles (Kp).
        
        output_delta = p_term + i_term + d_term
        
        # Calculate raw new bid
        raw_bid = current_bid + output_delta
        
        # 7. Output Saturation (Clamping)
        new_bid = max(self.min_out, min(raw_bid, self.max_out))

        return {
            "new_bid": int(new_bid),
            "error": error,
            "integral": integral,
            "p_term": p_term,
            "i_term": i_term,
            "d_term": d_term,
            "action": "update"
        }