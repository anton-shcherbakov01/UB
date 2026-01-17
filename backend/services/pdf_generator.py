"""
PDF Generator Service with Cyrillic support
"""
import os
import logging
from datetime import datetime
from fpdf import FPDF
from typing import List, Dict, Any, Optional

logger = logging.getLogger("PDFGenerator")


class PDFGenerator:
    """Helper class for generating PDF reports with Cyrillic support"""
    
    def __init__(self):
        self.font_paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            './fonts/DejaVuSans.ttf',
            '/usr/share/fonts/TTF/DejaVuSans.ttf',
            '/System/Library/Fonts/Supplemental/Arial.ttf',  # macOS fallback
        ]
        self.font_bold_paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            './fonts/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf',
        ]
    
    def _setup_fonts(self, pdf: FPDF) -> str:
        """Setup Cyrillic fonts for PDF. Returns font family name."""
        font_family = 'Arial'  # Fallback
        
        # Try to load DejaVu font
        for font_path in self.font_paths:
            if os.path.exists(font_path):
                try:
                    pdf.add_font('DejaVu', '', font_path, uni=True)
                    font_family = 'DejaVu'
                    
                    # Try to load bold font
                    for bold_path in self.font_bold_paths:
                        if os.path.exists(bold_path):
                            try:
                                pdf.add_font('DejaVu', 'B', bold_path, uni=True)
                                break
                            except:
                                continue
                    break
                except Exception as e:
                    logger.warning(f"Failed to load font from {font_path}: {e}")
                    continue
        
        pdf.set_font(font_family, '', 12)
        return font_family
    
    def create_pnl_pdf(self, pnl_data: List[Dict[str, Any]], date_from: str, date_to: str) -> bytes:
        """Create P&L PDF report"""
        pdf = FPDF()
        pdf.add_page()
        font_family = self._setup_fonts(pdf)
        
        # Title
        pdf.set_font(font_family, 'B', 16)
        pdf.cell(0, 10, txt="Отчет P&L (Прибыль и Убытки)", ln=1, align='C')
        pdf.ln(5)
        
        # Date range
        pdf.set_font(font_family, '', 10)
        pdf.cell(0, 8, txt=f"Период: {date_from[:10]} - {date_to[:10]}", ln=1, align='C')
        pdf.ln(5)
        
        if not pnl_data:
            pdf.set_font(font_family, '', 12)
            pdf.cell(0, 10, txt="Нет данных за выбранный период", ln=1, align='C')
            return pdf.output(dest='S').encode('latin-1')
        
        # Summary
        total_revenue = sum(item.get('revenue', 0) for item in pnl_data)
        total_cost = sum(item.get('cost', 0) for item in pnl_data)
        total_profit = total_revenue - total_cost
        total_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        pdf.set_font(font_family, 'B', 12)
        pdf.cell(0, 8, txt="Сводка:", ln=1)
        pdf.set_font(font_family, '', 10)
        pdf.cell(0, 6, txt=f"Выручка: {total_revenue:,.0f} ₽", ln=1)
        pdf.cell(0, 6, txt=f"Себестоимость: {total_cost:,.0f} ₽", ln=1)
        pdf.cell(0, 6, txt=f"Прибыль: {total_profit:,.0f} ₽", ln=1)
        pdf.cell(0, 6, txt=f"Маржа: {total_margin:.1f}%", ln=1)
        pdf.ln(5)
        
        # Table header
        pdf.set_font(font_family, 'B', 10)
        pdf.cell(40, 8, "Дата", 1)
        pdf.cell(50, 8, "Выручка", 1)
        pdf.cell(50, 8, "Себестоимость", 1)
        pdf.cell(50, 8, "Прибыль", 1)
        pdf.ln()
        
        # Table rows
        pdf.set_font(font_family, '', 9)
        for item in pnl_data[:50]:  # Limit to 50 rows
            date = item.get('date', '')[:10] if item.get('date') else ''
            revenue = item.get('revenue', 0)
            cost = item.get('cost', 0)
            profit = revenue - cost
            
            pdf.cell(40, 6, date, 1)
            pdf.cell(50, 6, f"{revenue:,.0f} ₽", 1)
            pdf.cell(50, 6, f"{cost:,.0f} ₽", 1)
            pdf.cell(50, 6, f"{profit:,.0f} ₽", 1)
            pdf.ln()
        
        return pdf.output(dest='S').encode('latin-1')
    
    def create_supply_pdf(self, supply_data: List[Dict[str, Any]]) -> bytes:
        """Create Supply analysis PDF report with ABC, velocity, ROP"""
        pdf = FPDF()
        pdf.add_page()
        font_family = self._setup_fonts(pdf)
        
        # Title
        pdf.set_font(font_family, 'B', 16)
        pdf.cell(0, 10, txt="Анализ поставок", ln=1, align='C')
        pdf.ln(5)
        
        if not supply_data:
            pdf.set_font(font_family, '', 12)
            pdf.cell(0, 10, txt="Нет данных для анализа", ln=1, align='C')
            return pdf.output(dest='S').encode('latin-1')
        
        # Summary statistics
        total_items = len(supply_data)
        out_of_stock = sum(1 for item in supply_data if item.get('status') == 'out_of_stock')
        warnings = sum(1 for item in supply_data if item.get('status') == 'warning')
        overstock = sum(1 for item in supply_data if item.get('status') == 'overstock')
        
        pdf.set_font(font_family, 'B', 11)
        pdf.cell(0, 8, txt="Сводка:", ln=1)
        pdf.set_font(font_family, '', 9)
        pdf.cell(0, 6, txt=f"Всего товаров: {total_items}", ln=1)
        pdf.cell(0, 6, txt=f"Нет в наличии: {out_of_stock}", ln=1)
        pdf.cell(0, 6, txt=f"Требуется заказ: {warnings}", ln=1)
        pdf.cell(0, 6, txt=f"Избыток: {overstock}", ln=1)
        pdf.ln(5)
        
        # Table header
        pdf.set_font(font_family, 'B', 9)
        pdf.cell(30, 7, "Артикул", 1)
        pdf.cell(50, 7, "Название", 1)
        pdf.cell(20, 7, "Остаток", 1)
        pdf.cell(20, 7, "ABC", 1)
        pdf.cell(25, 7, "Скорость", 1)
        pdf.cell(20, 7, "ROP", 1)
        pdf.cell(25, 7, "Рекомендация", 1)
        pdf.ln()
        
        # Table rows
        pdf.set_font(font_family, '', 8)
        for item in supply_data[:100]:  # Limit to 100 rows
            sku = str(item.get('sku', ''))
            name = str(item.get('name', ''))[:35]
            stock = item.get('stock', 0)
            abc = item.get('abc', 'C')
            velocity = item.get('velocity', 0)
            rop = item.get('rop', 0)
            recommendation = str(item.get('recommendation', ''))[:20]
            
            pdf.cell(30, 5, sku, 1)
            pdf.cell(50, 5, name, 1)
            pdf.cell(20, 5, str(stock), 1)
            pdf.cell(20, 5, abc, 1)
            pdf.cell(25, 5, f"{velocity:.1f}", 1)
            pdf.cell(20, 5, str(rop), 1)
            pdf.cell(25, 5, recommendation, 1)
            pdf.ln()
        
        # Footer
        pdf.set_y(-30)
        pdf.set_font(font_family, '', 8)
        pdf.set_text_color(128)
        pdf.cell(0, 10, f"Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align='C')
        
        return pdf.output(dest='S').encode('latin-1')
    
    def create_seo_tracker_pdf(self, positions: List[Dict[str, Any]], sku: Optional[str] = None, keyword: Optional[str] = None) -> bytes:
        """Create SEO Tracker PDF report with position history"""
        pdf = FPDF()
        pdf.add_page()
        font_family = self._setup_fonts(pdf)
        
        # Title
        pdf.set_font(font_family, 'B', 16)
        title = "SEO Трекер позиций"
        if sku:
            title += f": SKU {sku}"
        if keyword:
            title += f" / {keyword}"
        pdf.cell(0, 10, txt=title, ln=1, align='C')
        pdf.ln(5)
        
        if not positions:
            pdf.set_font(font_family, '', 12)
            pdf.cell(0, 10, txt="Нет данных для отчёта", ln=1, align='C')
            return pdf.output(dest='S').encode('latin-1')
        
        # Summary
        pdf.set_font(font_family, 'B', 11)
        pdf.cell(0, 8, txt="Сводка:", ln=1)
        pdf.set_font(font_family, '', 9)
        pdf.cell(0, 6, txt=f"Всего отслеживаемых позиций: {len(positions)}", ln=1)
        
        # Calculate average position
        valid_positions = [p.get('position', 0) for p in positions if p.get('position', 0) > 0]
        if valid_positions:
            avg_position = sum(valid_positions) / len(valid_positions)
            pdf.cell(0, 6, txt=f"Средняя позиция: {avg_position:.1f}", ln=1)
        
        pdf.ln(5)
        
        # Table header
        pdf.set_font(font_family, 'B', 9)
        pdf.cell(30, 7, "SKU", 1)
        pdf.cell(60, 7, "Ключевое слово", 1)
        pdf.cell(30, 7, "Позиция", 1)
        pdf.cell(40, 7, "Регион", 1)
        pdf.cell(30, 7, "Последняя проверка", 1)
        pdf.ln()
        
        # Table rows
        pdf.set_font(font_family, '', 8)
        for pos in positions[:100]:  # Limit to 100 rows
            pos_sku = str(pos.get('sku', ''))
            pos_keyword = str(pos.get('keyword', ''))[:40]
            position = pos.get('position', 0)
            geo = str(pos.get('geo', 'moscow'))[:30]
            last_check = pos.get('last_check', '')
            if isinstance(last_check, str):
                last_check = last_check[:10] if len(last_check) > 10 else last_check
            else:
                last_check = str(last_check)[:10]
            
            pdf.cell(30, 5, pos_sku, 1)
            pdf.cell(60, 5, pos_keyword, 1)
            pdf.cell(30, 5, str(position) if position > 0 else "Нет", 1)
            pdf.cell(40, 5, geo, 1)
            pdf.cell(30, 5, last_check, 1)
            pdf.ln()
        
        # Footer
        pdf.set_y(-30)
        pdf.set_font(font_family, '', 8)
        pdf.set_text_color(128)
        pdf.cell(0, 10, f"Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align='C')
        
        return pdf.output(dest='S').encode('latin-1')
    
    def create_unit_economy_pdf(self, unit_data: List[Dict[str, Any]]) -> bytes:
        """Create Unit Economy PDF report"""
        pdf = FPDF()
        pdf.add_page()
        font_family = self._setup_fonts(pdf)
        
        # Title
        pdf.set_font(font_family, 'B', 16)
        pdf.cell(0, 10, txt="Unit Экономика", ln=1, align='C')
        pdf.ln(5)
        
        if not unit_data:
            pdf.set_font(font_family, '', 12)
            pdf.cell(0, 10, txt="Нет данных для анализа", ln=1, align='C')
            return pdf.output(dest='S').encode('latin-1')
        
        # Summary
        total_profit = sum(item.get('unit_economy', {}).get('profit', 0) for item in unit_data)
        total_quantity = sum(item.get('quantity', 0) for item in unit_data)
        avg_margin = sum(item.get('unit_economy', {}).get('margin', 0) for item in unit_data) / len(unit_data) if unit_data else 0
        
        pdf.set_font(font_family, 'B', 11)
        pdf.cell(0, 8, txt="Сводка:", ln=1)
        pdf.set_font(font_family, '', 9)
        pdf.cell(0, 6, txt=f"Всего товаров: {len(unit_data)}", ln=1)
        pdf.cell(0, 6, txt=f"Общая прибыль: {total_profit:,.0f} ₽", ln=1)
        pdf.cell(0, 6, txt=f"Общее количество: {total_quantity}", ln=1)
        pdf.cell(0, 6, txt=f"Средняя маржа: {avg_margin:.1f}%", ln=1)
        pdf.ln(5)
        
        # Table header
        pdf.set_font(font_family, 'B', 8)
        pdf.cell(30, 7, "SKU", 1)
        pdf.cell(25, 7, "Кол-во", 1)
        pdf.cell(30, 7, "Цена", 1)
        pdf.cell(30, 7, "Себест.", 1)
        pdf.cell(30, 7, "Прибыль", 1)
        pdf.cell(25, 7, "ROI %", 1)
        pdf.cell(20, 7, "Маржа %", 1)
        pdf.ln()
        
        # Table rows
        pdf.set_font(font_family, '', 7)
        for item in unit_data[:100]:  # Limit to 100 rows
            sku = str(item.get('sku', ''))
            quantity = item.get('quantity', 0)
            price_struct = item.get('price_structure', {})
            selling_price = price_struct.get('selling', 0)
            cost_price = item.get('cost_price', 0)
            unit_econ = item.get('unit_economy', {})
            profit = unit_econ.get('profit', 0)
            roi = unit_econ.get('roi', 0)
            margin = unit_econ.get('margin', 0)
            
            pdf.cell(30, 5, sku, 1)
            pdf.cell(25, 5, str(quantity), 1)
            pdf.cell(30, 5, f"{selling_price:,.0f}", 1)
            pdf.cell(30, 5, f"{cost_price:,.0f}", 1)
            pdf.cell(30, 5, f"{profit:,.0f}", 1)
            pdf.cell(25, 5, f"{roi:.1f}", 1)
            pdf.cell(20, 5, f"{margin}%", 1)
            pdf.ln()
        
        # Footer
        pdf.set_y(-30)
        pdf.set_font(font_family, '', 8)
        pdf.set_text_color(128)
        pdf.cell(0, 10, f"Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align='C')
        
        return pdf.output(dest='S').encode('latin-1')
    
    def create_forensics_pdf(self, forensics_data: Dict[str, Any]) -> bytes:
        """Create Forensics PDF report"""
        pdf = FPDF()
        pdf.add_page()
        font_family = self._setup_fonts(pdf)
        
        # Title
        pdf.set_font(font_family, 'B', 16)
        pdf.cell(0, 10, txt="Форензика возвратов", ln=1, align='C')
        pdf.ln(5)
        
        if forensics_data.get('status') == 'error':
            pdf.set_font(font_family, '', 12)
            pdf.cell(0, 10, txt=f"Ошибка: {forensics_data.get('message', 'Неизвестная ошибка')}", ln=1, align='C')
            return pdf.output(dest='S').encode('latin-1')
        
        # Summary
        pdf.set_font(font_family, 'B', 12)
        pdf.cell(0, 8, txt="Сводка:", ln=1)
        pdf.set_font(font_family, '', 10)
        
        total_returns = forensics_data.get('total_returns', 0)
        problem_sizes = forensics_data.get('problem_sizes', {})
        problem_warehouses = forensics_data.get('problem_warehouses', {})
        
        pdf.cell(0, 6, txt=f"Всего возвратов: {total_returns}", ln=1)
        pdf.ln(5)
        
        # Problem sizes
        if problem_sizes:
            pdf.set_font(font_family, 'B', 11)
            pdf.cell(0, 8, txt="Проблемные размеры:", ln=1)
            pdf.set_font(font_family, '', 9)
            for size, count in list(problem_sizes.items())[:20]:
                pdf.cell(0, 6, txt=f"  {size}: {count} возвратов", ln=1)
            pdf.ln(3)
        
        # Problem warehouses
        if problem_warehouses:
            pdf.set_font(font_family, 'B', 11)
            pdf.cell(0, 8, txt="Проблемные склады:", ln=1)
            pdf.set_font(font_family, '', 9)
            for warehouse, count in list(problem_warehouses.items())[:20]:
                pdf.cell(0, 6, txt=f"  {warehouse}: {count} возвратов", ln=1)
        
        return pdf.output(dest='S').encode('latin-1')
    
    def create_cashgap_pdf(self, cashgap_data: Dict[str, Any]) -> bytes:
        """Create Cash Gap PDF report"""
        pdf = FPDF()
        pdf.add_page()
        font_family = self._setup_fonts(pdf)
        
        # Title
        pdf.set_font(font_family, 'B', 16)
        pdf.cell(0, 10, txt="Прогноз кассовых разрывов", ln=1, align='C')
        pdf.ln(5)
        
        if cashgap_data.get('status') == 'error':
            pdf.set_font(font_family, '', 12)
            pdf.cell(0, 10, txt=f"Ошибка: {cashgap_data.get('message', 'Неизвестная ошибка')}", ln=1, align='C')
            return pdf.output(dest='S').encode('latin-1')
        
        # Summary
        pdf.set_font(font_family, 'B', 12)
        pdf.cell(0, 8, txt="Прогноз:", ln=1)
        pdf.set_font(font_family, '', 10)
        
        gaps = cashgap_data.get('gaps', [])
        if gaps:
            pdf.cell(0, 6, txt=f"Найдено потенциальных разрывов: {len(gaps)}", ln=1)
            pdf.ln(3)
            
            for gap in gaps[:20]:
                date = gap.get('date', '')
                amount = gap.get('amount', 0)
                pdf.cell(0, 6, txt=f"  {date}: {amount:,.0f} ₽", ln=1)
        else:
            pdf.cell(0, 6, txt="Кассовых разрывов не прогнозируется", ln=1)
        
        return pdf.output(dest='S').encode('latin-1')
    
    def create_slots_pdf(self, slots_data: List[Dict[str, Any]]) -> bytes:
        """Create Slots analysis PDF report"""
        pdf = FPDF()
        pdf.add_page()
        font_family = self._setup_fonts(pdf)
        
        # Title
        pdf.set_font(font_family, 'B', 16)
        pdf.cell(0, 10, txt="Анализ слотов и коэффициентов", ln=1, align='C')
        pdf.ln(5)
        
        if not slots_data:
            pdf.set_font(font_family, '', 12)
            pdf.cell(0, 10, txt="Нет данных для анализа", ln=1, align='C')
            return pdf.output(dest='S').encode('latin-1')
        
        # Table header
        pdf.set_font(font_family, 'B', 10)
        pdf.cell(40, 8, "Артикул", 1)
        pdf.cell(60, 8, "Название", 1)
        pdf.cell(40, 8, "Свободно", 1)
        pdf.cell(50, 8, "Коэффициент", 1)
        pdf.ln()
        
        # Table rows
        pdf.set_font(font_family, '', 9)
        for item in slots_data[:50]:  # Limit to 50 rows
            sku = str(item.get('sku', ''))
            name = str(item.get('name', ''))[:40]
            free = item.get('free_slots', 0)
            coefficient = item.get('coefficient', 0)
            
            pdf.cell(40, 6, sku, 1)
            pdf.cell(60, 6, name, 1)
            pdf.cell(40, 6, str(free), 1)
            pdf.cell(50, 6, f"{coefficient:.2f}", 1)
            pdf.ln()
        
        return pdf.output(dest='S').encode('latin-1')


# Singleton instance
pdf_generator = PDFGenerator()

