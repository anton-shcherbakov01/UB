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
        """
        if df_sales.empty:
            return {}
        
        # Aggregate by SKU
        # Check strictly for priceWithDisc, fallback to totalPrice if needed
        price_col = 'priceWithDisc' if 'priceWithDisc' in df_sales.columns else 'totalPrice'
        
        if price_col not in df_sales.columns:
            return {}

        sku_revenue = df_sales.groupby('nmId')[price_col].sum().reset_index()
        sku_revenue = sku_revenue.sort_values(by=price_col, ascending=False)
        
        total_revenue = sku_revenue[price_col].sum()
        if total_revenue == 0:
            return {}

        sku_revenue['cumulative'] = sku_revenue[price_col].cumsum()
        sku_revenue['share'] = (sku_revenue['cumulative'] / total_revenue) * 100.0
        
        b_threshold = a_share + 15.0
        if b_threshold > 95: b_threshold = 95

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
        # Defaults
        lead_time = config.get('lead_time', 7)
        abc_a_share = config.get('abc_a_share', 80.0)
        
        if not stocks_raw:
            return []

        # 1. Process Stocks
        df_stocks = self._prepare_dataframe(stocks_raw)
        
        if df_stocks.empty:
            return []
            
        # Ensure quantity exists in stocks (usually does)
        if 'quantity' not in df_stocks.columns:
            logger.error("Stocks data missing 'quantity' column from WB API")
            return []

        # Group by SKU (sum quantity across all warehouses)
        # Using 'first' for attributes that should be identical per SKU
        agg_map = {'quantity': 'sum'}
        if 'brand' in df_stocks.columns: agg_map['brand'] = 'first'
        if 'subject' in df_stocks.columns: agg_map['subject'] = 'first'
        if 'techSize' in df_stocks.columns: agg_map['techSize'] = 'first'
        
        stock_map = df_stocks.groupby('nmId').agg(agg_map).reset_index()

        # 2. Process Orders (Demand) - Last 30 Days
        df_orders = self._prepare_dataframe(orders_raw)
        sales_velocity = {} 
        
        if not df_orders.empty:
            # FIX: WB Orders API returns a list of items, implying qty=1 per row.
            if 'quantity' not in df_orders.columns:
                df_orders['quantity'] = 1
            
            # Ensure Date parsing
            if 'date' in df_orders.columns:
                df_orders['date'] = pd.to_datetime(df_orders['date'])
                cutoff = datetime.utcnow() - timedelta(days=30)
                df_orders = df_orders[df_orders['date'] > cutoff]
            
            orders_grouped = df_orders.groupby('nmId')['quantity'].sum().reset_index()
            
            for _, row in orders_grouped.iterrows():
                sales_velocity[row['nmId']] = row['quantity'] / 30.0

        # 3. Calculate ABC
        abc_map = {}
        if not df_orders.empty:
             abc_map = self.calculate_abc(df_orders, a_share=abc_a_share)

        # 4. Final Metrics Calculation
        results = []
        for _, row in stock_map.iterrows():
            sku = int(row['nmId'])
            current_stock = int(row['quantity'])
            
            # Extract safe attributes
            brand = row.get('brand', 'Unknown')
            subject = row.get('subject', 'Product')
            size = row.get('techSize', '')
            
            # Defaults
            velocity = sales_velocity.get(sku, 0.0)
            abc_category = abc_map.get(sku, 'C')
            
            # Metrics
            days_of_stock = 999
            if velocity > 0:
                days_of_stock = int(current_stock / velocity)
            
            # ROP Calculation
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
                recommendation = "Избыток товара (>60 дней)"
            
            results.append({
                "sku": sku,
                "name": f"{subject} {brand}",
                "size": size,
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
                "supply": { 
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
    
    def calculate_cash_gap(
        self, 
        supply_analysis: List[Dict[str, Any]], 
        costs_map: Dict[int, float], # {sku: cost_price}
        balance_current: float = 0.0
    ) -> Dict[str, Any]:
        """
        4.4. Календарь кассовых разрывов.
        Прогноз даты, когда потребуются средства на закупку.
        """
        calendar = {}
        total_needed = 0.0
        
        # Сортируем товары по дате обнуления стока (days_to_stock)
        sorted_items = sorted(
            [i for i in supply_analysis if i.get('velocity', 0) > 0], 
            key=lambda x: x['days_to_stock']
        )

        for item in sorted_items:
            sku = item['sku']
            velocity = item['velocity'] # шт/день
            days_left = item['days_to_stock']
            
            # Дата X (когда товар закончится)
            out_of_stock_date = datetime.now() + timedelta(days=days_left)
            date_str = out_of_stock_date.strftime("%Y-%m-%d")
            
            # Сколько нужно закупить (по ROP или добрать до мин. остатка)
            # Если to_order уже посчитан в analyze_supply
            qty_to_order = item.get('to_order', 0)
            if qty_to_order <= 0:
                continue
                
            cost_price = costs_map.get(sku, 0)
            if cost_price == 0:
                continue # Не можем посчитать без себестоимости

            money_needed = qty_to_order * cost_price
            
            if date_str not in calendar:
                calendar[date_str] = {"needed": 0.0, "items": []}
            
            calendar[date_str]["needed"] += money_needed
            calendar[date_str]["items"].append({
                "sku": sku,
                "name": item['name'],
                "qty": qty_to_order,
                "sum": round(money_needed, 0)
            })
            total_needed += money_needed

        # Прогноз баланса (упрощенно)
        # Предполагаем, что текущая скорость продаж генерирует выручку
        # В идеале нужно вычитать комиссию и логистику, тут берем грубо "грязными" или маржинальными, если есть
        
        # Формируем итоговый Timeline
        timeline = []
        running_balance = balance_current
        
        # Собираем все уникальные даты событий
        all_dates = sorted(calendar.keys())
        
        for date_s in all_dates:
            needed = calendar[date_s]["needed"]
            dt = datetime.strptime(date_s, "%Y-%m-%d")
            days_from_now = (dt - datetime.now()).days
            
            # Приход денег от продаж за этот период (очень грубая оценка для примера)
            # В реальном проекте берем sum(velocity * price * margin) по всем товарам
            # estimated_income = daily_margin * days_from_now
            
            timeline.append({
                "date": date_s,
                "status": "GAP" if needed > running_balance else "OK", # Если бы считали приход
                "amount_needed": round(needed, 0),
                "items_count": len(calendar[date_s]["items"]),
                "details": calendar[date_s]["items"]
            })

        return {
            "total_needed_soon": round(total_needed, 0),
            "nearest_gap_date": all_dates[0] if all_dates else None,
            "timeline": timeline
        }

supply_service = SupplyService()