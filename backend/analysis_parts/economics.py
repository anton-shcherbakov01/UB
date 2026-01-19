import math
import numpy as np
import pandas as pd
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import ProductCost
from clickhouse_models import ch_service

logger = logging.getLogger("Analysis-Economics")

class EconomicsModule:
    
    def calculate_supply_metrics(
        self, 
        current_stock: int, 
        sales_history: List[Dict[str, Any]], 
        forecast_data: Optional[Dict[str, Any]] = None,
        lead_time_days: int = 7,  # Среднее время поставки
        lead_time_sigma: int = 2, # Отклонение времени поставки (дней)
        service_level_z: float = 1.65 # Z-score для 95% уровня сервиса
    ) -> Dict[str, Any]:
        """
        Расчет точки заказа (ROP) и страхового запаса (Safety Stock).
        """
        # 1. Определяем спрос (Demand)
        if forecast_data and forecast_data.get("status") == "success":
            avg_daily_demand = forecast_data.get("daily_avg_forecast", 0)
            forecast_points = forecast_data.get("forecast_points", [])
            demand_during_lead_time = sum([p['yhat'] for p in forecast_points[:lead_time_days]])
        else:
            if not sales_history:
                return {"status": "error", "message": "No data"}
            values = [x['qty'] for x in sales_history if x['qty'] > 0]
            if not values:
                return {"status": "error", "message": "Zero sales"}
            avg_daily_demand = np.mean(values)
            demand_during_lead_time = avg_daily_demand * lead_time_days

        # 2. Считаем стандартное отклонение спроса (sigma_Demand)
        if sales_history:
            hist_values = [x['qty'] for x in sales_history]
            sigma_demand = np.std(hist_values) if len(hist_values) > 1 else 0
        else:
            sigma_demand = 0

        # 3. Расчет Safety Stock
        term1 = lead_time_days * (sigma_demand ** 2)
        term2 = (avg_daily_demand ** 2) * (lead_time_sigma ** 2)
        safety_stock = service_level_z * math.sqrt(term1 + term2)
        
        # 4. Расчет ROP
        rop = demand_during_lead_time + safety_stock
        
        # 5. Интерпретация
        days_left = current_stock / avg_daily_demand if avg_daily_demand > 0 else 999
        
        safety_stock = int(math.ceil(safety_stock))
        rop = int(math.ceil(rop))
        days_left = int(days_left)
        
        status = "ok"
        recommendation = "Запаса достаточно"
        
        if current_stock <= 0:
            status = "out_of_stock"
            recommendation = "Товара нет в наличии!"
        elif current_stock < safety_stock:
            status = "critical"
            recommendation = "Срочно пополнить! (Ниже страхового запаса)"
        elif current_stock < rop:
            status = "warning"
            recommendation = f"Пора заказывать (Ниже точки заказа {rop} шт)"
            
        return {
            "status": status,
            "recommendation": recommendation,
            "metrics": {
                "safety_stock": safety_stock,
                "rop": rop,
                "days_left": days_left,
                "avg_daily_demand": round(avg_daily_demand, 1),
                "demand_lead_time": round(demand_during_lead_time, 1),
                "current_stock": current_stock
            },
            "inputs": {
                "lead_time": lead_time_days,
                "service_level": "95%"
            }
        }

    async def get_pnl_data(self, user_id: int, date_from: datetime, date_to: datetime, db: AsyncSession) -> List[Dict[str, Any]]:
        logger.info(f"📊 [PnL] Формирование финансового отчета для user={user_id}")

        # Согласно документации WB (Отчет о реализации):
        # retail_price_withdisc_rub - цена продажи (грязная выручка)
        # ppvz_sales_commission - комиссия WB
        # ppvz_for_pay - сумма к перечислению за товар (уже за вычетом комиссии)
        # delivery_rub - стоимость логистики
        # penalty - штрафы
        ch_query = """
        SELECT 
            toDate(sale_dt) as report_date,
            nm_id,
            sumIf(retail_price_withdisc_rub, doc_type_name = 'Продажа') as gross_sales,
            sumIf(retail_price_withdisc_rub, doc_type_name = 'Возврат') as returns_sum,
            sumIf(quantity, doc_type_name = 'Продажа') as qty_sold,
            sumIf(quantity, doc_type_name = 'Возврат') as qty_returned,
            sum(ppvz_sales_commission) as wb_commission,
            sum(delivery_rub) as logistics,
            sum(penalty) as penalties,
            sum(additional_payment) as adjustments,
            sum(ppvz_for_pay) as net_for_pay
        FROM wb_analytics.realization_reports FINAL
        WHERE supplier_id = %(uid)s 
          AND sale_dt >= %(start)s 
          AND sale_dt <= %(end)s
        GROUP BY report_date, nm_id
        ORDER BY report_date ASC
        """
        
        params = {'uid': user_id, 'start': date_from, 'end': date_to}
        
        try:
            ch_client = ch_service.get_client()
            if not ch_client:
                logger.warning("⚠️ ClickHouse client not available")
                return []
            
            result = ch_client.query(ch_query, parameters=params)
            rows = result.result_rows
        except Exception as e:
            logger.error(f"❌ ClickHouse Query Error: {e}")
            return []

        if not rows: return []

        unique_skus = list(set([row[1] for row in rows]))
        
        # Получаем себестоимость из PostgreSQL для расчета COGS
        try:
            stmt = select(ProductCost).where(ProductCost.user_id == user_id, ProductCost.sku.in_(unique_skus))
            cogs_result = await db.execute(stmt)
            costs_map = {c.sku: c.cost_price for c in cogs_result.scalars().all()}
        except Exception as e:
            logger.error(f"Error fetching product costs: {e}")
            costs_map = {}

        daily_pnl = {}
        for row in rows:
            r_date, sku, gross, returns, q_sold, q_ret, commission, logistics, penalties, adjustments, net_pay = row
            
            # Безопасное приведение типов
            gross = float(gross or 0)
            returns = float(returns or 0)
            q_sold = int(q_sold or 0)
            q_ret = int(q_ret or 0)
            commission = float(commission or 0)
            logistics = float(logistics or 0)
            penalties = float(penalties or 0)
            adjustments = float(adjustments or 0)
            net_pay = float(net_pay or 0)

            # COGS = (Продано - Возвращено) * Себестоимость за единицу
            unit_cost = costs_map.get(sku, 0)
            total_cogs = (q_sold - q_ret) * unit_cost

            date_str = r_date.strftime("%Y-%m-%d")
            if date_str not in daily_pnl:
                daily_pnl[date_str] = {
                    "date": date_str, 
                    "gross_sales": 0.0, 
                    "net_sales": 0.0, 
                    "cogs": 0.0,
                    "commission": 0.0, 
                    "logistics": 0.0, 
                    "penalties": 0.0, 
                    "cm3": 0.0
                }
            
            d = daily_pnl[date_str]
            # Выручка за период (продажи минус возвраты по розничной цене)
            d["gross_sales"] += (gross - returns)
            # Фактическая комиссия из отчета
            d["commission"] += commission
            # Логистика
            d["logistics"] += logistics
            # Штрафы и доплаты
            d["penalties"] += (penalties + adjustments)
            # Сумма к перечислению (уже очищенная от комиссии внутри WB)
            d["net_sales"] += net_pay
            # Себестоимость
            d["cogs"] += total_cogs
        
        final_output = []
        for date_str, m in sorted(daily_pnl.items()):
            # Итоговая чистая прибыль (CM3) = К перечислению - Себестоимость - Логистика - Штрафы
            # Мы вычитаем логистику и штрафы из net_sales, так как в отчетах WB 
            # поле ppvz_for_pay часто НЕ включает в себя эти расходы (они идут отдельными удержаниями).
            m["cm3"] = m["net_sales"] - m["logistics"] - m["penalties"] - m["cogs"]
            
            # Округляем все финансовые показатели
            for k in ["gross_sales", "net_sales", "cogs", "commission", "logistics", "penalties", "cm3"]:
                m[k] = round(m[k], 2)
            final_output.append(m)
            
        return final_output

    def calculate_metrics(self, raw_data: dict):
        if raw_data.get("status") == "error": return raw_data
        p = raw_data.get("prices", {})
        wallet = p.get("wallet_purple", 0)
        standard = p.get("standard_black", 0)
        base = p.get("base_crossed", 0)
        benefit = standard - wallet if standard > wallet else 0
        discount_pct = round(((base - wallet) / base * 100), 1) if base > 0 else 0
        raw_data["metrics"] = {
            "wallet_benefit": benefit,
            "total_discount_percent": discount_pct,
            "is_favorable": discount_pct > 45
        }
        return raw_data

    def calculate_transit_benefit(self, volume_liters: int):
        koledino_direct_cost = volume_liters * 30 * 1 
        kazan_transit_cost = 1500 + (volume_liters * 20 * 0) 
        benefit = koledino_direct_cost - kazan_transit_cost
        return {
            "direct_cost": koledino_direct_cost,
            "transit_cost": kazan_transit_cost,
            "benefit": benefit,
            "is_profitable": benefit > 0,
            "recommendation": "Используйте транзит через Казань" if benefit > 0 else "Прямая поставка выгоднее"
        }
    
    def calculate_real_logistics(self, volume_l: float, warehouse_tariffs: dict) -> float:
        """
        Считает логистику по формуле WB:
        База (за 5л) + (Объем - 5) * Ставка за литр
        """
        # Берем Коледино как эталон, если не знаем конкретный склад отгрузки
        # В идеале нужно смотреть остатки по складам и делать средневзвешенное
        target_wh = warehouse_tariffs.get('Коледино') or warehouse_tariffs.get('Подольск')
        
        if not target_wh:
            return 50.0 # Fallback если тарифы не загрузились
            
        base_price = target_wh['base'] # Обычно около 30-40р
        liter_price = target_wh['liter'] # Обычно около 3-7р
        
        if volume_l <= 5:
            return base_price
        
        extra_liters = volume_l - 5
        cost = base_price + (extra_liters * liter_price)
        return round(cost, 2)

    def calculate_abc_xyz(self, sales_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Расчет ABC/XYZ анализа.
        """
        if not sales_data:
            return {"status": "error", "message": "Нет данных для анализа"}

        try:
            # Конвертируем в DataFrame
            df = pd.DataFrame(sales_data)
            
            # Приведение типов (на случай строк)
            df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce').fillna(0)
            df['qty'] = pd.to_numeric(df['qty'], errors='coerce').fillna(0)
            
            # ---------------------------
            # ABC Анализ (по Выручке)
            # ---------------------------
            # Группировка по SKU
            abc_df = df.groupby('sku')['revenue'].sum().reset_index()
            # Сортировка по убыванию выручки
            abc_df = abc_df.sort_values(by='revenue', ascending=False)
            
            total_revenue = abc_df['revenue'].sum()
            if total_revenue == 0:
                return {"status": "error", "message": "Общая выручка равна 0"}

            # Кумулятивная доля
            abc_df['cumsum'] = abc_df['revenue'].cumsum()
            abc_df['share'] = abc_df['cumsum'] / total_revenue
            
            # Присвоение классов
            # A: 0-80%, B: 80-95%, C: 95-100%
            def get_abc(share):
                if share <= 0.8: return 'A'
                elif share <= 0.95: return 'B'
                return 'C'
                
            abc_df['abc_class'] = abc_df['share'].apply(get_abc)
            
            # Словарь {sku: 'A'}
            abc_map = abc_df.set_index('sku')['abc_class'].to_dict()

            # ---------------------------
            # XYZ Анализ (по Стабильности спроса)
            # ---------------------------
            # Группируем по SKU и Дате (чтобы схлопнуть продажи внутри одного дня, если есть дубли)
            daily_sales = df.groupby(['sku', 'date'])['qty'].sum().reset_index()
            
            # Считаем стд. отклонение и среднее по дням для каждого SKU
            xyz_stats = daily_sales.groupby('sku')['qty'].agg(['std', 'mean']).reset_index()
            
            # Коэффициент вариации (CV) = sigma / mu
            # Если mean = 0, CV = 0 (защита от деления на 0)
            xyz_stats['cv'] = np.where(xyz_stats['mean'] > 0, xyz_stats['std'] / xyz_stats['mean'], 0)
            # Заполняем NaN нулями (если была всего 1 продажа, std=NaN)
            xyz_stats['cv'] = xyz_stats['cv'].fillna(0)

            # Присвоение классов
            # X: 0 - 0.1 (стабильные)
            # Y: 0.1 - 0.25 (колебания)
            # Z: > 0.25 (случайные)
            def get_xyz(cv):
                if cv <= 0.1: return 'X'
                elif cv <= 0.25: return 'Y'
                return 'Z'
                
            xyz_stats['xyz_class'] = xyz_stats['cv'].apply(get_xyz)
            xyz_map = xyz_stats.set_index('sku')['xyz_class'].to_dict()

            # ---------------------------
            # Слияние результатов
            # ---------------------------
            results = {}
            # Все уникальные SKU
            all_skus = set(abc_map.keys()) | set(xyz_map.keys())
            
            summary_counts = {g: 0 for g in ["AX","AY","AZ","BX","BY","BZ","CX","CY","CZ"]}

            for sku in all_skus:
                a = abc_map.get(sku, 'C') # Если нет выручки, то C
                x = xyz_map.get(sku, 'Z') # Если нет продаж в шт, то Z
                group = f"{a}{x}"
                
                results[sku] = {
                    "abc": a,
                    "xyz": x,
                    "group": group
                }
                if group in summary_counts:
                    summary_counts[group] += 1
                    
            return {
                "status": "success",
                "items": results,
                "summary": summary_counts
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def get_return_forensics(self, user_id: int, date_from: datetime, date_to: datetime) -> Dict[str, Any]:
        """
        4.3. Форензика Возвратов.
        Анализ причин потерь: корреляция возвратов с размером (ts_name) и складом (office_name).
        """
        # 1. Агрегация по Размерам (выявление неудачных лекал)
        ch_query_sizes = """
        SELECT 
            nm_id,
            ts_name as size,
            sumIf(quantity, doc_type_name = 'Продажа') as sales,
            sumIf(quantity, doc_type_name = 'Возврат') as returns,
            sumIf(delivery_rub, doc_type_name = 'Возврат') as return_logistics_cost,
            sumIf(retail_price_withdisc_rub, doc_type_name = 'Продажа') as revenue
        FROM wb_analytics.realization_reports
        WHERE supplier_id = %(uid)s 
          AND sale_dt >= %(start)s 
          AND sale_dt <= %(end)s
        GROUP BY nm_id, size
        HAVING (sales + returns) > 5 -- Отсекаем шум
        ORDER BY returns DESC
        """

        # 2. Агрегация по Складам (выявление бракованных партий на конкретном складе)
        ch_query_warehouses = """
        SELECT 
            nm_id,
            office_name as warehouse,
            sumIf(quantity, doc_type_name = 'Продажа') as sales,
            sumIf(quantity, doc_type_name = 'Возврат') as returns,
            sumIf(delivery_rub, doc_type_name = 'Возврат') as return_logistics_cost
        FROM wb_analytics.realization_reports
        WHERE supplier_id = %(uid)s 
          AND sale_dt >= %(start)s 
          AND sale_dt <= %(end)s
        GROUP BY nm_id, warehouse
        HAVING returns > 0
        ORDER BY returns DESC
        """
        
        params = {'uid': user_id, 'start': date_from, 'end': date_to}
        
        try:
            ch_client = ch_service.get_client()
            if not ch_client:
                logger.warning("ClickHouse client not available for forensics query")
                return {"status": "error", "message": "ClickHouse connection unavailable"}
            rows_sizes = ch_client.query(ch_query_sizes, parameters=params).result_rows
            rows_wh = ch_client.query(ch_query_warehouses, parameters=params).result_rows
        except Exception as e:
            logger.error(f"Forensics Query Error: {e}")
            return {"status": "error", "message": str(e)}

        # Обработка данных по Размерам
        size_anomalies = []
        for r in rows_sizes:
            nm_id, size, sales, returns, ret_cost, rev = r
            # Приведение типов
            sales = int(sales) if sales else 0
            returns = int(returns) if returns else 0
            
            total_ops = sales + returns
            buyout_rate = round((sales / total_ops) * 100, 1) if total_ops > 0 else 0
            
            # Логика детекции аномалии: если выкуп ниже 30% при наличии продаж
            if buyout_rate < 30 and total_ops > 10:
                verdict = "Критически низкий выкуп. Проверьте лекала."
            elif buyout_rate < 50:
                verdict = "Низкий выкуп. Возможно, большемер/маломер."
            else:
                verdict = "Норма"

            size_anomalies.append({
                "nm_id": nm_id,
                "size": size,
                "buyout_rate": buyout_rate,
                "sales": sales,
                "returns": returns,
                "loss_on_returns": round(float(ret_cost), 2) if ret_cost else 0.0,
                "verdict": verdict
            })

        # Обработка данных по Складам
        wh_stats = []
        for r in rows_wh:
            nm_id, wh, sales, returns, ret_cost = r
            sales = int(sales) if sales else 0
            returns = int(returns) if returns else 0
            
            total_ops = sales + returns
            return_rate = round((returns / total_ops) * 100, 1) if total_ops > 0 else 0
            
            wh_stats.append({
                "nm_id": nm_id,
                "warehouse": wh,
                "return_rate": return_rate,
                "returns_count": returns,
                "cost": round(float(ret_cost), 2) if ret_cost else 0.0
            })

        return {
            "size_analysis": sorted(size_anomalies, key=lambda x: x['buyout_rate']),
            "warehouse_analysis": sorted(wh_stats, key=lambda x: x['return_rate'], reverse=True)[:20] # Топ 20 проблемных складов
        }