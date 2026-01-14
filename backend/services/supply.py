import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from wb_api.statistics import WBStatisticsAPI

logger = logging.getLogger("SupplyService")

class SupplyService:
    """
    Domain service for Supply Chain Analytics.
    Calculates ROP, Turnover, and ABC Analysis based on real WB data.
    """

    def _prepare_dataframe(self, data: List[Dict[str, Any]]) -> pd.DataFrame:
        if not data:
            return pd.DataFrame()
        return pd.DataFrame(data)

    def calculate_abc(self, df_sales: pd.DataFrame) -> Dict[int, str]:
        """
        ABC Analysis based on Revenue (Sales Amount).
        A: Top 80% revenue
        B: Next 15% revenue
        C: Bottom 5% revenue
        """
        if df_sales.empty:
            return {}
        
        # Aggregate by SKU
        sku_revenue = df_sales.groupby('nmId')['priceWithDisc'].sum().reset_index()
        sku_revenue = sku_revenue.sort_values(by='priceWithDisc', ascending=False)
        
        total_revenue = sku_revenue['priceWithDisc'].sum()
        sku_revenue['cumulative'] = sku_revenue['priceWithDisc'].cumsum()
        sku_revenue['share'] = sku_revenue['cumulative'] / total_revenue
        
        def classify(row):
            if row['share'] <= 0.8: return 'A'
            elif row['share'] <= 0.95: return 'B'
            else: return 'C'
            
        sku_revenue['abc'] = sku_revenue.apply(classify, axis=1)
        return dict(zip(sku_revenue['nmId'], sku_revenue['abc']))

    def analyze_supply(
        self, 
        stocks_raw: List[Dict[str, Any]], 
        orders_raw: List[Dict[str, Any]],
        lead_time: int = 7  # Days to deliver goods to WB
    ) -> List[Dict[str, Any]]:
        
        if not stocks_raw:
            return []

        # 1. Process Stocks
        df_stocks = self._prepare_dataframe(stocks_raw)
        # Group by SKU (sum quantity across all warehouses)
        stock_map = df_stocks.groupby('nmId').agg({
            'quantity': 'sum',
            'Price': 'mean',  # Basic price
            'Discount': 'mean',
            'brand': 'first',
            'subject': 'first',
            'techSize': 'first' # Size
        }).reset_index()

        # 2. Process Orders (Demand) - Last 30 Days
        df_orders = self._prepare_dataframe(orders_raw)
        
        sales_velocity = {} # SKU -> Units per Day
        
        if not df_orders.empty:
            # Convert WB date format
            df_orders['date'] = pd.to_datetime(df_orders['date'])
            # Filter last 30 days explicitly
            cutoff = datetime.utcnow() - timedelta(days=30)
            df_orders = df_orders[df_orders['date'] > cutoff]
            
            # Group by SKU
            orders_grouped = df_orders.groupby('nmId')['quantity'].sum().reset_index()
            
            # Calculate Velocity (Avg Daily Sales)
            # We assume 30 days period for valid velocity
            for _, row in orders_grouped.iterrows():
                sales_velocity[row['nmId']] = row['quantity'] / 30.0

        # 3. Calculate ABC
        # Using orders as a proxy for revenue potential (since we want to restock what SELLS)
        # Assuming priceWithDisc is available in orders or mapping it from stocks
        abc_map = {}
        if not df_orders.empty and 'priceWithDisc' in df_orders.columns:
             abc_map = self.calculate_abc(df_orders)

        # 4. Final Metrics Calculation
        results = []
        for _, row in stock_map.iterrows():
            sku = int(row['nmId'])
            current_stock = int(row['quantity'])
            
            # Defaults
            velocity = sales_velocity.get(sku, 0.0)
            abc_category = abc_map.get(sku, 'C')
            
            # Metrics
            days_of_stock = 999
            if velocity > 0:
                days_of_stock = int(current_stock / velocity)
            
            turnover_days = 0 
            # Turnover = Period Days / Turnover Ratio
            # Simplified: if we sold X in 30 days and have Y stock.
            # Turnover (Оборачиваемость) in days usually means: How many days to sell current stock?
            # Which is same as Days of Stock. 
            # Or Historical Turnover: (Avg Stock / COGS) * 365. 
            # WB usually shows "Turnover Days". We will use Days of Stock as actionable metric.
            
            # ROP (Reorder Point)
            # ROP = (Daily Sales * Lead Time) + Safety Stock
            # Safety Stock = (Max Daily Sales * Max Lead Time) - (Avg Daily Sales * Avg Lead Time)
            # Simplified for MVP: Safety Stock = 50% of Lead Time Demand
            lead_time_demand = velocity * lead_time
            safety_stock = lead_time_demand * 0.5 
            rop = int(lead_time_demand + safety_stock)
            
            # Recommendation
            status = "ok"
            recommendation = "Запас в норме"
            to_order = 0
            
            if current_stock == 0:
                status = "out_of_stock"
                recommendation = "OUT OF STOCK! Срочная поставка"
                to_order = int(rop * 1.5) # Order enough for 1.5 cycles
            elif current_stock <= rop:
                status = "warning"
                recommendation = f"Пора заказывать (Остаток < {rop})"
                to_order = int((rop * 2) - current_stock) # Target stock level = 2 * ROP
            elif days_of_stock > 60:
                status = "overstock"
                recommendation = "Избыток товара (более 60 дней)"
            
            results.append({
                "sku": sku,
                "name": f"{row['subject']} {row['brand']}", # Simplified name
                "size": row['techSize'],
                "image": "", # Frontend handles image via basket link
                "stock": current_stock,
                "velocity": round(velocity, 2), # шт/день
                "days_to_stock": days_of_stock,
                "turnover": days_of_stock, # WB terminology often aligns this
                "rop": rop,
                "abc": abc_category,
                "status": status,
                "recommendation": recommendation,
                "to_order": max(0, to_order)
            })
            
        # Sort by ABC then by Velocity
        results.sort(key=lambda x: (x['abc'], -x['velocity']))
        return results

# Singleton
supply_service = SupplyService()