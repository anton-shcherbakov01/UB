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
        self.font_dir = os.path.join(os.path.dirname(__file__), '../fonts')

    def _setup_pdf(self):
        pdf = FPDF()
        pdf.add_page()
        
        # Подключение шрифтов (DejaVuSans поддерживает кириллицу)
        try:
            font_regular = os.path.join(self.font_dir, 'DejaVuSans.ttf')
            font_bold = os.path.join(self.font_dir, 'DejaVuSans-Bold.ttf')
            
            if os.path.exists(font_regular):
                # FPDF2 автоматически понимает Unicode для TTF шрифтов
                pdf.add_font('DejaVu', '', font_regular)
                
                # Подключаем жирный шрифт, если есть (для заголовков)
                if os.path.exists(font_bold):
                    pdf.add_font('DejaVu', 'B', font_bold)
                
                pdf.set_font('DejaVu', '', 12)
            else:
                logger.warning(f"Cyrillic font not found at {font_regular}, falling back to Arial")
                pdf.set_font("Arial", size=12)
        except Exception as e:
            logger.error(f"Font loading error: {e}")
            pdf.set_font("Arial", size=12)
            
        return pdf

    
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
    
    def _safe_cell(self, pdf, w, h, txt, border=0, align='L', fill=False):
        """
        Безопасная запись в ячейку. 
        Если шрифт не поддерживает символ, пробуем заменить на транслит/ASCII.
        """
        try:
            pdf.cell(w, h, txt=str(txt), border=border, align=align, fill=fill)
        except Exception as e:
            try:
                # Fallback: замена символов, если шрифт не тянет
                safe_txt = str(txt).encode('ascii', 'replace').decode('ascii')
                pdf.cell(w, h, txt=safe_txt, border=border, align=align, fill=fill)
            except Exception:
                pdf.cell(w, h, txt="?", border=border, align=align, fill=fill)

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
            return self._return_bytes(pdf)
        
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
        
        return self._return_bytes(pdf)
    
    def create_supply_pdf(self, analysis_data: list) -> bytes:
        """
        Генерация PDF отчета по поставкам.
        """
        pdf = self._setup_pdf()
        
        # Заголовок
        pdf.set_font_size(16)
        # Если есть жирный шрифт, используем его
        try:
            pdf.set_font('DejaVu', 'B', 16)
        except:
            pass
            
        self._safe_cell(pdf, 0, 10, txt=f"Отчет по поставкам (Supply Chain) - {datetime.now().strftime('%d.%m.%Y')}", align='C')
        pdf.ln(10)
        
        # Возвращаем обычный шрифт для таблицы
        try:
            pdf.set_font('DejaVu', '', 10)
        except:
            pdf.set_font_size(10)
        
        # Headers
        col_widths = [80, 25, 25, 20, 30]
        headers = ["Товар", "Остаток", "Скорость", "ABC", "Статус"]
        
        for i, h in enumerate(headers):
            self._safe_cell(pdf, col_widths[i], 10, txt=h, border=1, align='C')
        pdf.ln()
        
        # Rows
        pdf.set_font_size(8)
        for item in analysis_data:
            name = str(item.get('name', 'Unknown'))[:40]
            stock = str(item.get('stock', 0))
            velocity = str(round(item.get('velocity', 0), 2))
            abc = f"{item.get('abc', '-')}{item.get('xyz', '-')}"
            status = item.get('recommendation', '-')
            
            row = [name, stock, velocity, abc, status]
            
            for i, val in enumerate(row):
                align = 'L' if i == 0 else 'C'
                self._safe_cell(pdf, col_widths[i], 8, txt=val, border=1, align=align)
            
            pdf.ln()

        return self._return_bytes(pdf)
    
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
            return self._return_bytes(pdf)
        
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
        col_w = [35, 20, 30, 30, 30, 20, 20]
        headers = ["SKU", "Кол-во", "Цена", "Себест.", "Прибыль", "ROI %", "Маржа"]
        
        for i, h in enumerate(headers):
            self._safe_cell(pdf, col_w[i], 7, h, 1, 'C')
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
            
            row_data = [
                sku,
                str(quantity),
                f"{selling_price:,.0f}",
                f"{cost_price:,.0f}",
                f"{profit:,.0f}",
                f"{roi:.1f}",
                f"{margin}%"
            ]
            
            for i, val in enumerate(row_data):
                self._safe_cell(pdf, col_w[i], 5, val, 1, 'C')
            pdf.ln()
        
        # Footer
        pdf.set_y(-30)
        pdf.set_font(font_family, '', 8)
        pdf.set_text_color(128)
        pdf.cell(0, 10, f"Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align='C')
        
        return self._return_bytes(pdf)
    
    def create_forensics_pdf(self, forensics_data: Dict[str, Any]) -> bytes:
        """Create Forensics PDF report with Tables"""
        pdf = self._setup_pdf()
        
        # Заголовок
        pdf.set_font_size(16)
        try:
            pdf.set_font('DejaVu', 'B', 16)
        except:
            pass
            
        self._safe_cell(pdf, 0, 10, txt="Отчет по возвратам (Forensics)", align='C')
        pdf.ln(10)
        
        if forensics_data.get('status') == 'error':
            try:
                pdf.set_font('DejaVu', '', 12)
            except:
                pdf.set_font_size(12)
            self._safe_cell(pdf, 0, 10, txt=f"Ошибка: {forensics_data.get('message', 'Неизвестная ошибка')}", align='C')
            return self._return_bytes(pdf)
        
        # Сводка
        try:
            pdf.set_font('DejaVu', 'B', 12)
        except:
            pdf.set_font_size(12)
        self._safe_cell(pdf, 0, 8, txt="Сводка:")
        pdf.ln()
        
        try:
            pdf.set_font('DejaVu', '', 10)
        except:
            pdf.set_font_size(10)
        
        total_returns = forensics_data.get('total_returns', 0)
        self._safe_cell(pdf, 0, 6, txt=f"Всего возвратов за период: {total_returns}")
        pdf.ln(8)
        
        # --- Таблица размеров ---
        problem_sizes = forensics_data.get('problem_sizes', {})
        if problem_sizes:
            try:
                pdf.set_font('DejaVu', 'B', 11)
            except:
                pass
            self._safe_cell(pdf, 0, 8, txt="Топ проблемных размеров:")
            pdf.ln()
            
            # Headers
            col_widths = [60, 40]
            headers = ["Размер", "Кол-во возвратов"]
            try:
                pdf.set_font('DejaVu', 'B', 10)
            except:
                pass
                
            for i, h in enumerate(headers):
                self._safe_cell(pdf, col_widths[i], 8, txt=h, border=1, align='C')
            pdf.ln()
            
            # Rows
            try:
                pdf.set_font('DejaVu', '', 10)
            except:
                pass
                
            for size, count in list(problem_sizes.items())[:20]:
                self._safe_cell(pdf, col_widths[0], 7, txt=size, border=1, align='L')
                self._safe_cell(pdf, col_widths[1], 7, txt=str(count), border=1, align='C')
                pdf.ln()
            
            pdf.ln(5)
        
        # --- Таблица складов ---
        problem_warehouses = forensics_data.get('problem_warehouses', {})
        if problem_warehouses:
            try:
                pdf.set_font('DejaVu', 'B', 11)
            except:
                pass
            self._safe_cell(pdf, 0, 8, txt="Топ проблемных складов:")
            pdf.ln()
            
            # Headers
            col_widths = [100, 40]
            headers = ["Склад", "Кол-во возвратов"]
            try:
                pdf.set_font('DejaVu', 'B', 10)
            except:
                pass
                
            for i, h in enumerate(headers):
                self._safe_cell(pdf, col_widths[i], 8, txt=h, border=1, align='C')
            pdf.ln()
            
            # Rows
            try:
                pdf.set_font('DejaVu', '', 10)
            except:
                pass
                
            for warehouse, count in list(problem_warehouses.items())[:20]:
                self._safe_cell(pdf, col_widths[0], 7, txt=warehouse, border=1, align='L')
                self._safe_cell(pdf, col_widths[1], 7, txt=str(count), border=1, align='C')
                pdf.ln()
        
        return self._return_bytes(pdf)
    
    def create_cashgap_pdf(self, cashgap_data: Dict[str, Any]) -> bytes:
        """Create Cash Gap PDF report with Tables"""
        pdf = self._setup_pdf()
        
        # Заголовок
        pdf.set_font_size(16)
        try:
            pdf.set_font('DejaVu', 'B', 16)
        except:
            pass
            
        self._safe_cell(pdf, 0, 10, txt="Прогноз кассовых разрывов", align='C')
        pdf.ln(10)
        
        status = cashgap_data.get('status')
        if status == 'error' or status == 'empty':
            try:
                pdf.set_font('DejaVu', '', 12)
            except:
                pdf.set_font_size(12)
            msg = cashgap_data.get('message', 'Неизвестная ошибка')
            self._safe_cell(pdf, 0, 10, txt=f"Инфо: {msg}", align='C')
            return self._return_bytes(pdf)
        
        # Сводка
        try:
            pdf.set_font('DejaVu', 'B', 12)
        except:
            pdf.set_font_size(12)
        self._safe_cell(pdf, 0, 8, txt="Финансовая сводка:")
        pdf.ln()
        
        try:
            pdf.set_font('DejaVu', '', 10)
        except:
            pdf.set_font_size(10)
            
        gaps = cashgap_data.get('gaps', [])
        total_needed = cashgap_data.get('total_needed_soon', 0)
        nearest_date = cashgap_data.get('nearest_gap_date')
        
        self._safe_cell(pdf, 0, 6, txt=f"Общая потребность в средствах: {total_needed:,.0f} ₽")
        pdf.ln()
        if nearest_date:
            self._safe_cell(pdf, 0, 6, txt=f"Ближайший разрыв: {nearest_date}")
            pdf.ln()
        
        pdf.ln(5)
        
        # Таблица разрывов
        if gaps:
            try:
                pdf.set_font('DejaVu', 'B', 11)
            except:
                pass
            self._safe_cell(pdf, 0, 8, txt="Детализация по датам:")
            pdf.ln()
            
            # Headers
            col_widths = [50, 60, 50]
            headers = ["Дата", "Сумма разрыва", "Статус"]
            try:
                pdf.set_font('DejaVu', 'B', 10)
            except:
                pass
                
            for i, h in enumerate(headers):
                self._safe_cell(pdf, col_widths[i], 8, txt=h, border=1, align='C')
            pdf.ln()
            
            # Rows
            try:
                pdf.set_font('DejaVu', '', 10)
            except:
                pass
                
            for gap in gaps[:50]:
                date = gap.get('date', '-')
                amount = gap.get('amount', 0)
                
                self._safe_cell(pdf, col_widths[0], 7, txt=date, border=1, align='C')
                self._safe_cell(pdf, col_widths[1], 7, txt=f"{amount:,.0f} ₽", border=1, align='R')
                self._safe_cell(pdf, col_widths[2], 7, txt="Дефицит", border=1, align='C')
                pdf.ln()
        else:
            self._safe_cell(pdf, 0, 10, txt="Кассовых разрывов не прогнозируется.", align='L')
        
        return self._return_bytes(pdf)
    
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

    def _return_bytes(self, pdf) -> bytes:
        try:
            # FPDF2 возвращает bytearray для dest='S'
            output = pdf.output(dest='S')
            
            if isinstance(output, str):
                return output.encode('latin-1') # Старое поведение
            
            return bytes(output) # Новое поведение
            
        except Exception as e:
            logger.error(f"PDF Output error: {e}")
            raise e

# Singleton instance
pdf_generator = PDFGenerator()