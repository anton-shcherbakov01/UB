import hmac
import hashlib
from urllib.parse import parse_qsl

class AuthService:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token

    def validate_init_data(self, init_data: str) -> bool:
        try:
            parsed_data = dict(parse_qsl(init_data))
            if 'hash' not in parsed_data: return False
            received_hash = parsed_data.pop('hash')
            check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
            secret_key = hmac.new(b"WebAppData", self.bot_token.encode(), hashlib.sha256).digest()
            calc_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
            return calc_hash == received_hash
        except: return False