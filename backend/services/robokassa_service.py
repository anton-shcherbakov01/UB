"""
Robokassa Payment Service
"""
import os
import hashlib
import logging
from typing import Optional
from urllib.parse import urlencode

logger = logging.getLogger("RobokassaService")


class RobokassaService:
    """
    Service for handling Robokassa payments.
    """
    
    def __init__(self):
        self.merchant_login = os.getenv("ROBOKASSA_MERCHANT_LOGIN", "")
        self.password1 = os.getenv("ROBOKASSA_PASSWORD1", "")  # For payment URL generation
        self.password2 = os.getenv("ROBOKASSA_PASSWORD2", "")  # For callback verification
        self.test_mode = os.getenv("ROBOKASSA_TEST_MODE", "false").lower() == "true"
        
        # URLs
        self.success_url = os.getenv("ROBOKASSA_SUCCESS_URL", "https://t.me/juicystat_bot/juicystat")
        self.fail_url = os.getenv("ROBOKASSA_FAIL_URL", "https://t.me/juicystat_bot/app/juicystat")
        self.result_url = os.getenv("ROBOKASSA_RESULT_URL", "")
        
        # Base URLs
        if self.test_mode:
            self.base_url = "https://auth.robokassa.ru/Merchant/Index.aspx"
        else:
            self.base_url = "https://auth.robokassa.ru/Merchant/Index.aspx"
    
    def _generate_signature(self, out_sum: float, inv_id: int, password: str, shp_params: Optional[dict] = None) -> str:
        """
        Generate MD5 signature for Robokassa.
        
        Args:
            out_sum: Payment amount
            inv_id: Invoice ID
            password: Password (Password1 for URL, Password2 for callback)
            shp_params: Optional dictionary of shp_ parameters (e.g., {"user_id": 123})
            
        Returns:
            MD5 hash string
        """
        # Format amount with 2 decimal places
        amount_str = f"{out_sum:.2f}"
        
        # For payment URL: MerchantLogin:OutSum:InvId:Password1[:Shp_x=value...]
        # For callback: OutSum:InvId:Password2[:Shp_x=value...]
        # Shp parameters must be in alphabetical order!
        if password == self.password1:
            signature_string = f"{self.merchant_login}:{amount_str}:{inv_id}:{password}"
        else:
            signature_string = f"{amount_str}:{inv_id}:{password}"
        
        # Add shp_ parameters in alphabetical order (CRITICAL for signature validation)
        if shp_params:
            sorted_shp = sorted(shp_params.items())
            for key, value in sorted_shp:
                signature_string += f":Shp_{key}={value}"
        
        return hashlib.md5(signature_string.encode('utf-8')).hexdigest().upper()
    
    def create_payment_url(
        self,
        inv_id: int,
        amount: float,
        description: str,
        email: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> str:
        """
        Create payment URL for Robokassa.
        
        Args:
            inv_id: Invoice ID (unique payment identifier)
            amount: Payment amount in RUB
            description: Payment description
            email: User email (optional)
            user_id: User ID for metadata (optional)
            
        Returns:
            Payment URL string
        """
        if not self.merchant_login or not self.password1:
            raise ValueError("Robokassa credentials not configured")
        
        # Prepare shp_params dict for signature calculation (must be alphabetical order)
        shp_params = {}
        if user_id is not None:
            shp_params["user_id"] = user_id
        
        # Generate signature WITH shp_params (CRITICAL: must match URL parameters)
        signature = self._generate_signature(amount, inv_id, self.password1, shp_params)
        
        # Build parameters
        params = {
            "MerchantLogin": self.merchant_login,
            "OutSum": f"{amount:.2f}",
            "InvId": inv_id,
            "Description": description,
            "SignatureValue": signature,
            "IsTest": 1 if self.test_mode else 0,
        }
        
        # Add optional parameters
        if self.success_url:
            params["SuccessURL"] = self.success_url
        if self.fail_url:
            params["FailURL"] = self.fail_url
        if email:
            params["Email"] = email
        if user_id is not None:
            params["Shp_user_id"] = user_id
        
        # Build URL and log for debugging
        url = f"{self.base_url}?{urlencode(params)}"
        logger.info(f"Robokassa payment URL generated: inv_id={inv_id}, amount={amount}, signature={signature[:8]}...")
        logger.debug(f"Robokassa params: {params}")
        return url
    
    def verify_callback_signature(
        self,
        out_sum: str,
        inv_id: str,
        signature_value: str,
        shp_params: Optional[dict] = None
    ) -> bool:
        """
        Verify callback signature from Robokassa.
        
        Args:
            out_sum: Payment amount (as string from callback)
            inv_id: Invoice ID (as string from callback)
            signature_value: Signature from callback
            shp_params: Optional dictionary of shp_ parameters from callback
            
        Returns:
            True if signature is valid, False otherwise
        """
        if not self.password2:
            logger.error("Robokassa Password2 not configured")
            return False
        
        try:
            # Convert to float and back to ensure proper formatting
            amount = float(out_sum)
            inv_id_int = int(inv_id)
            
            # Prepare shp_params from callback (if provided)
            callback_shp = {}
            if shp_params:
                for key, value in shp_params.items():
                    # Remove "Shp_" prefix if present
                    clean_key = key.replace("Shp_", "") if key.startswith("Shp_") else key
                    callback_shp[clean_key] = value
            
            # Generate expected signature WITH shp_params (must match what Robokassa sent)
            expected_signature = self._generate_signature(amount, inv_id_int, self.password2, callback_shp if callback_shp else None)
            
            # Compare (case-insensitive)
            is_valid = expected_signature.upper() == signature_value.upper()
            if not is_valid:
                logger.warning(f"Signature mismatch: expected={expected_signature}, received={signature_value}, shp_params={shp_params}")
            return is_valid
        except (ValueError, TypeError) as e:
            logger.error(f"Error verifying signature: {e}")
            return False
    
    def get_payment_status_response(self, inv_id: int, success: bool = True) -> str:
        """
        Generate response for Robokassa ResultURL callback.
        
        Args:
            inv_id: Invoice ID
            success: Whether payment was processed successfully
            
        Returns:
            Response string (OK<InvId> or error message)
        """
        if success:
            return f"OK{inv_id}"
        else:
            return f"ERROR{inv_id}"

