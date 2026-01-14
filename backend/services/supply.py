import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any

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

    def calculate_abc(self, df_sales: pd.DataFrame, a_share: float = 80.0) -> Dict[int, str]:
        """
        ABC Analysis with customizable thresholds.
        :param a_share: Percent of revenue for 'A' category (e.g., 80.0)
        """
        if df_sales.empty:
            return {}
        
        # Aggregate by SKU
        sku_revenue = df_sales.groupby('nmId')['priceWithDisc'].sum().reset_index()
        sku_revenue = sku_revenue.sort_values(by='priceWithDisc', ascending=False)
        
        total_revenue = sku_revenue['priceWithDisc'].sum()
        if total_revenue == 0:
            return {}

        sku_revenue['cumulative'] = sku_revenue['priceWithDisc'].cumsum()
        sku_revenue['share'] = (sku_revenue['cumulative'] / total_revenue) * 100.0
        
        # Convert float threshold to decimal logic if needed, but keeping simple comparison
        # share is 0..100
        
        b_threshold = a_share + 15.0 # Usually B is next 15%
        if b_threshold > 95: b_threshold = 95 # Cap C at 5% min

        def classify(row):
            if row['share'] <= a_share: return 'A'
            elif row['share'] <= b_threshold: return 'B'
            else: return 'C'
            
        sku_revenue['abc'] = sku_revenue.apply(classify, axis=1)
        return dict(zip(sku_revenue['nmId'], sku_revenue['abc']))

    def analyze_supply(
        self, 
        stocks_raw: List[Dict[str, Any]], 
        orders_raw: List[Dict[str, Any]],
        config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Main analysis method using user-specific config.
        config expected keys: 'lead_time', 'min_stock_days', 'abc_a_share'
        """
        
        # Defaults if config missing
        lead_time = config.get('lead_time', 7)
        abc_a_share = config.get('abc_a_share', 80.0)
        
        if not stocks_raw:
            return []

        # 1. Process Stocks
        df_stocks = self._prepare_dataframe(stocks_raw)
        # Group by SKU (sum quantity across all warehouses)
        stock_map = df_stocks.groupby('nmId').agg({
            'quantity': 'sum',
            'brand': 'first',
            'subject': 'first',
            'techSize': 'first' # Size
        }).reset_index()

        # 2. Process Orders (Demand) - Last 30 Days (Hardcoded horizon for velocity accuracy)
        df_orders = self._prepare_dataframe(orders_raw)
        
        sales_velocity = {} # SKU -> Units per Day
        
        if not df_orders.empty:
            df_orders['date'] = pd.to_datetime(df_orders['date'])
            cutoff = datetime.utcnow() - timedelta(days=30)
            df_orders = df_orders[df_orders['date'] > cutoff]
            
            orders_grouped = df_orders.groupby('nmId')['quantity'].sum().reset_index()
            
            for _, row in orders_grouped.iterrows():
                sales_velocity[row['nmId']] = row['quantity'] / 30.0

        # 3. Calculate ABC using dynamic threshold
        abc_map = {}
        if not df_orders.empty and 'priceWithDisc' in df_orders.columns:
             abc_map = self.calculate_abc(df_orders, a_share=abc_a_share)

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
            
            # ROP Calculation using dynamic Lead Time
            # ROP = (Daily Sales * Lead Time) + Safety Stock
            lead_time_demand = velocity * lead_time
            safety_stock = lead_time_demand * 0.5 
            rop = int(lead_time_demand + safety_stock)
            
            # Recommendation Logic
            status = "ok"
            recommendation = "Запас в норме"
            to_order = 0
            
            if current_stock == 0:
                status = "out_of_stock"
                recommendation = "OUT OF STOCK! Срочная поставка"
                to_order = int(rop * 1.5)
            elif current_stock <= rop:
                status = "warning"
                recommendation = f"Пора заказывать (Остаток < {rop})"
                to_order = int((rop * 2) - current_stock)
            elif days_of_stock > 60:
                status = "overstock"
                recommendation = "Избыток товара (более 60 дней)"
            
            results.append({
                "sku": sku,
                "name": f"{row['subject']} {row['brand']}",
                "size": row['techSize'],
                "stock": current_stock,
                "velocity": round(velocity, 2),
                "days_to_stock": days_of_stock,
                "rop": rop,
                "abc": abc_category,
                "status": status,
                "recommendation": recommendation,
                "to_order": max(0, to_order),
                "metrics": {
                    "rop": rop,
                    "safety_stock": int(safety_stock),
                    "current_stock": current_stock
                },
                "supply": { # Legacy wrapper for frontend compat if needed
                    "status": status,
                    "days_left": days_of_stock,
                    "recommendation": recommendation,
                    "metrics": {
                        "rop": rop,
                        "safety_stock": int(safety_stock),
                        "current_stock": current_stock
                    }
                }
            })
            
        results.sort(key=lambda x: (x['abc'], -x['velocity']))
        return results

supply_service = SupplyService()