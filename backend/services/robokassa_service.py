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
        self.success_url = os.getenv("ROBOKASSA_SUCCESS_URL", "https://t.me/WbAnalyticsBot/app")
        self.fail_url = os.getenv("ROBOKASSA_FAIL_URL", "https://t.me/WbAnalyticsBot/app")
        self.result_url = os.getenv("ROBOKASSA_RESULT_URL", "")
        
        # Base URLs
        if self.test_mode:
            self.base_url = "https://auth.robokassa.ru/Merchant/Index.aspx"
        else:
            self.base_url = "https://auth.robokassa.ru/Merchant/Index.aspx"
    
    def _generate_signature(self, out_sum: float, inv_id: int, password: str) -> str:
        """
        Generate MD5 signature for Robokassa.
        
        Args:
            out_sum: Payment amount
            inv_id: Invoice ID
            password: Password (Password1 for URL, Password2 for callback)
            
        Returns:
            MD5 hash string
        """
        # Format amount with 2 decimal places
        amount_str = f"{out_sum:.2f}"
        
        # For payment URL: MerchantLogin:OutSum:InvId:Password1
        # For callback: OutSum:InvId:Password2
        if password == self.password1:
            signature_string = f"{self.merchant_login}:{amount_str}:{inv_id}:{password}"
        else:
            signature_string = f"{amount_str}:{inv_id}:{password}"
        
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
        
        # Generate signature
        signature = self._generate_signature(amount, inv_id, self.password1)
        
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
        if user_id:
            params["Shp_user_id"] = user_id
        
        # Build URL
        url = f"{self.base_url}?{urlencode(params)}"
        return url
    
    def verify_callback_signature(
        self,
        out_sum: str,
        inv_id: str,
        signature_value: str
    ) -> bool:
        """
        Verify callback signature from Robokassa.
        
        Args:
            out_sum: Payment amount (as string from callback)
            inv_id: Invoice ID (as string from callback)
            signature_value: Signature from callback
            
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
            
            # Generate expected signature
            expected_signature = self._generate_signature(amount, inv_id_int, self.password2)
            
            # Compare (case-insensitive)
            return expected_signature.upper() == signature_value.upper()
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

