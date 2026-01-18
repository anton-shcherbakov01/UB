"""
Robokassa Payment Service (Final Fix)
"""
import os
import hashlib
import logging
from typing import Optional, Union
from urllib.parse import urlencode

logger = logging.getLogger("RobokassaService")


class RobokassaService:
    """
    Service for handling Robokassa payments.
    """
    
    def __init__(self):
        self.merchant_login = os.getenv("ROBOKASSA_MERCHANT_LOGIN", "")
        self.password1 = os.getenv("ROBOKASSA_PASSWORD1", "")
        self.password2 = os.getenv("ROBOKASSA_PASSWORD2", "")
        self.test_mode = os.getenv("ROBOKASSA_TEST_MODE", "false").lower() == "true"
        
        # URLs
        self.success_url = os.getenv("ROBOKASSA_SUCCESS_URL", "")
        self.fail_url = os.getenv("ROBOKASSA_FAIL_URL", "")
        self.result_url = os.getenv("ROBOKASSA_RESULT_URL", "")
        
        self.base_url = "https://auth.robokassa.ru/Merchant/Index.aspx"
    
    def _generate_signature(
        self, 
        out_sum: Union[float, str], 
        inv_id: int, 
        password: str, 
        shp_params: Optional[dict] = None,
        is_init: bool = True
    ) -> str:
        """
        Generate MD5 signature for Robokassa.
        """
        
        # ЛОГИКА ИСПРАВЛЕНА ЗДЕСЬ:
        if is_init:
            # При создании ссылки мы ОБЯЗАНЫ передавать сумму с точностью до копеек
            amount_str = f"{float(out_sum):.2f}"
        else:
            # При проверке ответа (Callback) мы должны использовать строку ТОЧНО как прислала Робокасса.
            # Если она прислала "1490", мы хэшируем "1490". Если "1490.00" — то "1490.00".
            amount_str = str(out_sum)
        
        # 1. Init:   Login:OutSum:InvId:Pass1[:Shp...]
        # 2. Result: OutSum:InvId:Pass2[:Shp...]
        
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
        
        # Генерируем подпись (is_init=True -> добавит .00 к сумме)
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
            inv_id_int = int(inv_id)
            
            callback_shp = {}
            if shp_params:
                for key, value in shp_params.items():
                    clean_key = key.replace("Shp_", "") if key.startswith("Shp_") else key
                    callback_shp[clean_key] = value
            
            # Генерируем ожидаемую подпись (is_init=False -> НЕ трогает формат суммы)
            # Передаем out_sum прямо строкой, как она пришла от Робокассы ("1490")
            expected_signature = self._generate_signature(
                out_sum, inv_id_int, self.password2, 
                callback_shp if callback_shp else None, 
                is_init=False
            )
            
            is_valid = expected_signature.upper() == signature_value.upper()
            
            if not is_valid:
                logger.warning(
                    f"Signature mismatch!\n"
                    f"Expected (calc): {expected_signature}\n"
                    f"Received (robo): {signature_value}\n"
                    f"Data: Sum='{out_sum}', Inv={inv_id_int}"
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