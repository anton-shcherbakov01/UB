import os
import json
import random
import zipfile
from typing import Optional
from .config import logger

class ProxyManager:
    def __init__(self):
        self.user = os.getenv("PROXY_USER")
        self.password = os.getenv("PROXY_PASS")
        self.host = os.getenv("PROXY_HOST")
        self.port = os.getenv("PROXY_PORT")

    def get_aiohttp_proxy(self, rotate: bool = False) -> Optional[str]:
        """
        Формирует строку прокси для aiohttp.
        Если rotate=True, добавляет session-ID к юзернейму (для резистентных прокси).
        """
        if self.host and self.port:
            if self.user and self.password:
                user_str = self.user
                if rotate:
                    # Генерируем случайную сессию для ротации IP
                    session_id = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=8))
                    user_str = f"{user_str}-session-{session_id}"
                return f"http://{user_str}:{self.password}@{self.host}:{self.port}"
            return f"http://{self.host}:{self.port}"
        return None

    def create_proxy_auth_extension(self) -> Optional[str]:
        """Создает ZIP-расширение для Chrome/Edge для авторизации прокси."""
        if not self.host or not self.port or not self.user:
            return None

        folder_path = "proxy_ext"
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            
        manifest_json = json.dumps({
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Edge Proxy",
            "permissions": [
                "proxy", "tabs", "unlimitedStorage", "storage", 
                "<all_urls>", "webRequest", "webRequestBlocking"
            ],
            "background": {"scripts": ["background.js"]}
        })
        
        session_id = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10))
        auth_user = f"{self.user}-session-{session_id};country-ru"
        
        background_js = """
        var config = { mode: "fixed_servers", rules: { singleProxy: { scheme: "http", host: "%s", port: parseInt(%s) }, bypassList: ["localhost"] } };
        chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
        chrome.webRequest.onAuthRequired.addListener(function(details) { return { authCredentials: { username: "%s", password: "%s" } }; }, {urls: ["<all_urls>"]}, ['blocking']);
        """ % (self.host, self.port, auth_user, self.password)
        
        extension_path = os.path.join(folder_path, "proxy_auth_plugin.zip")
        try:
            with zipfile.ZipFile(extension_path, 'w') as zp:
                zp.writestr("manifest.json", manifest_json)
                zp.writestr("background.js", background_js)
            return extension_path
        except Exception as e:
            logger.error(f"Failed to create proxy extension: {e}")
            return None