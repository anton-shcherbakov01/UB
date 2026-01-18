"""
Robokassa Payment Service (Fixed)
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
        
        self.base_url = "https://auth.robokassa.ru/Merchant/Index.aspx"
    
    def _generate_signature(
        self, 
        out_sum: float, 
        inv_id: int, 
        password: str, 
        shp_params: Optional[dict] = None,
        is_init: bool = True  # <--- ДОБАВЛЕН ФЛАГ
    ) -> str:
        """
        Generate MD5 signature for Robokassa.
        
        Args:
            out_sum: Payment amount
            inv_id: Invoice ID
            password: Password (Password1 for URL, Password2 for callback)
            shp_params: Optional dictionary of shp_ parameters
            is_init: True if generating URL for payment (includes MerchantLogin), 
                     False if verifying callback (excludes MerchantLogin).
        """
        # Format amount with 2 decimal places
        amount_str = f"{out_sum:.2f}"
        
        # For payment URL (Init): MerchantLogin:OutSum:InvId:Password1[:Shp_x=value...]
        # For callback (Result): OutSum:InvId:Password2[:Shp_x=value...]
        
        if is_init:
            signature_string = f"{self.merchant_login}:{amount_str}:{inv_id}:{password}"
        else:
            signature_string = f"{amount_str}:{inv_id}:{password}"
        
        # Add shp_ parameters in alphabetical order
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
        if not self.merchant_login or not self.password1:
            raise ValueError("Robokassa credentials not configured")
        
        shp_params = {}
        if user_id is not None:
            shp_params["user_id"] = user_id
        
        # Генерируем подпись для Инициализации (is_init=True)
        signature = self._generate_signature(
            amount, inv_id, self.password1, shp_params, is_init=True
        )
        
        params = {
            "MerchantLogin": self.merchant_login,
            "OutSum": f"{amount:.2f}",
            "InvId": inv_id,
            "Description": description,
            "SignatureValue": signature,
            "IsTest": 1 if self.test_mode else 0,
        }
        
        if self.success_url:
            params["SuccessURL"] = self.success_url
        if self.fail_url:
            params["FailURL"] = self.fail_url
        if email:
            params["Email"] = email
        if user_id is not None:
            params["Shp_user_id"] = user_id
        
        url = f"{self.base_url}?{urlencode(params)}"
        logger.info(f"Robokassa payment URL generated: inv_id={inv_id}, amount={amount}")
        return url
    
    def verify_callback_signature(
        self,
        out_sum: str,
        inv_id: str,
        signature_value: str,
        shp_params: Optional[dict] = None
    ) -> bool:
        if not self.password2:
            logger.error("Robokassa Password2 not configured")
            return False
        
        try:
            amount = float(out_sum)
            inv_id_int = int(inv_id)
            
            callback_shp = {}
            if shp_params:
                for key, value in shp_params.items():
                    # Очищаем ключи от префикса Shp_ перед передачей в генератор
                    clean_key = key.replace("Shp_", "") if key.startswith("Shp_") else key
                    callback_shp[clean_key] = value
            
            # Генерируем ожидаемую подпись для RESULT URL (is_init=False)
            expected_signature = self._generate_signature(
                amount, inv_id_int, self.password2, 
                callback_shp if callback_shp else None, 
                is_init=False
            )
            
            is_valid = expected_signature.upper() == signature_value.upper()
            
            if not is_valid:
                # Логируем, чтобы видеть разницу
                # ВАЖНО: Не логируйте пароли в продакшене, но для дебага структуры полезно
                debug_shp = callback_shp if callback_shp else "None"
                logger.warning(
                    f"Signature mismatch!\n"
                    f"Expected (calc): {expected_signature}\n"
                    f"Received (robo): {signature_value}\n"
                    f"Inputs: Sum={amount}, Inv={inv_id_int}, Shp={debug_shp}"
                )
            
            return is_valid
        except (ValueError, TypeError) as e:
            logger.error(f"Error verifying signature: {e}")
            return False

    def get_payment_status_response(self, inv_id: int, success: bool = True) -> str:
        if success:
            return f"OK{inv_id}"
        else:
            return f"ERROR{inv_id}"