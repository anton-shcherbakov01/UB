import os
import re
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from .config import logger, get_random_ua
from .proxy import ProxyManager

class BrowserManager:
    def __init__(self):
        self.headless = os.getenv("HEADLESS", "True").lower() == "true"
        self.proxy_manager = ProxyManager()

    def init_driver(self):
        edge_options = EdgeOptions()
        if self.headless: 
            edge_options.add_argument("--headless=new")
        
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--disable-blink-features=AutomationControlled")
        edge_options.add_argument("--window-size=1920,1080")
        
        # Установка прокси расширения
        plugin_path = self.proxy_manager.create_proxy_auth_extension()
        if plugin_path:
            edge_options.add_extension(plugin_path)
            
        edge_options.add_argument(f"user-agent={get_random_ua()}")
        
        try:
            driver_bin = '/usr/local/bin/msedgedriver'
            service = EdgeService(executable_path=driver_bin)
            driver = webdriver.Edge(service=service, options=edge_options)
            driver.set_page_load_timeout(120)
            return driver
        except Exception as e:
            logger.error(f"Driver Init Error: {e}")
            raise e

    @staticmethod
    def extract_price(driver, selector):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                text = el.get_attribute('textContent')
                if not text: continue
                text = text.replace('\xa0', '').replace('&nbsp;', '').replace(' ', '').replace('₽', '')
                digits = re.sub(r'[^\d]', '', text)
                if digits: return int(digits)
        except: pass
        return 0