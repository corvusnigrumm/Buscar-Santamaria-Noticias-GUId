import os
from datetime import datetime, timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from core.logger import logger

class GeneradorExcelIDEAS:
    FONT_NAME = "Century Gothic"
    NEGRO = "000000"
    BLANCO = "FFFFFF"
    GRIS_CLARO = "F5F5F5"
    GRIS_BORDE = "CCCCCC"
    COLORES_TAB = [
        "FF4444", "FFD700", "00CC66", "00CCCC", "FF66FF",
        "FF8800", "4488FF", "AA44FF", "44DDAA", "DD4488",
        "88CC00", "0088DD", "FF6644", "6644FF", "44FF88",
    ]

    def __init__(self, articulos):
        self.articulos = articulos
        self.wb = Workbook()

    def generar(self, nombre_archivo):
        logger.info("")
        logger.info("=" * 60)
        logger.info("  Generando Excel (una hoja por categoría)...")
        logger.info("=" * 60)

        por_cat = {}
        for art in self.articulos:
            cat = art.get("categoria", "GENERAL")
            por_cat.setdefault(cat, []).append(art)

        cats_ord = sorted(por_cat.keys())

        ws_res = self.wb.active
        ws_res.title = "RESUMEN"
        ws_res.sheet_properties.tabColor = self.NEGRO
        self._hoja_resumen(ws_res, por_cat, cats_ord)

        for i, cat in enumerate(cats_ord):
            nombre_hoja = cat[:31]
            ws = self.wb.create_sheet(title=nombre_hoja)
            ws.sheet_properties.tabColor = self.COLORES_TAB[i % len(self.COLORES_TAB)]
            self._hoja_datos(ws, por_cat[cat])
            logger.info(f"  ✓ Hoja '{nombre_hoja}': {len(por_cat[cat])} artículos")

        self.wb.save(nombre_archivo)
        logger.info(f"  ✓ Guardado: {nombre_archivo}")
        logger.info(f"  ✓ Total: {len(self.articulos)} en {len(cats_ord)} hojas")
        return nombre_archivo

    def _hoja_resumen(self, ws, por_cat, cats_ord):
        headers = [("CATEGORÍA", "FFFFFF"), ("ARTÍCULOS", "FFD700")]
        for ci, (h, c) in enumerate(headers, 1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.font = Font(name=self.FONT_NAME, bold=True, size=11, color=c)
            cell.fill = PatternFill(start_color=self.NEGRO, end_color=self.NEGRO, fill_type='solid')
            cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 30
        borde = Border(
            left=Side(style='hair', color=self.GRIS_BORDE),
            right=Side(style='hair', color=self.GRIS_BORDE),
            top=Side(style='hair', color=self.GRIS_BORDE),
            bottom=Side(style='hair', color=self.GRIS_BORDE))
        fp = PatternFill(start_color=self.GRIS_CLARO, end_color=self.GRIS_CLARO, fill_type='solid')
        fi = PatternFill(start_color=self.BLANCO, end_color=self.BLANCO, fill_type='solid')
        total = 0
        for idx, cat in enumerate(cats_ord):
            row = idx + 2
            cnt = len(por_cat[cat])
            total += cnt
            fill = fp if idx % 2 == 0 else fi
            c = ws.cell(row=row, column=1, value=cat)
            c.font = Font(name=self.FONT_NAME, size=10, bold=True, color="333333")
            c.alignment = Alignment(horizontal='left', vertical='center')
            c.fill = fill; c.border = borde
            c = ws.cell(row=row, column=2, value=cnt)
            c.font = Font(name=self.FONT_NAME, size=10, color="333333")
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.fill = fill; c.border = borde
        rt = len(cats_ord) + 2
        for ci, (v, clr) in enumerate([("TOTAL", "FFFFFF"), (total, "FFD700")], 1):
            c = ws.cell(row=rt, column=ci, value=v)
            c.font = Font(name=self.FONT_NAME, size=11, bold=True, color=clr)
            c.fill = PatternFill(start_color=self.NEGRO, end_color=self.NEGRO, fill_type='solid')
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.border = borde
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 15
        ws.freeze_panes = "A2"

    def _hoja_datos(self, ws, articulos):
        headers = [("FUENTE","FF4444"),("TÍTULO","FFD700"),("RESUMEN CORTO","00CC66"),
                   ("URL","00CCCC"),("FECHA","FF66FF")]
        for ci, (h, c) in enumerate(headers, 1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.font = Font(name=self.FONT_NAME, bold=True, size=10, color=c)
            cell.fill = PatternFill(start_color=self.NEGRO, end_color=self.NEGRO, fill_type='solid')
            cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 28
        borde = Border(
            left=Side(style='hair', color=self.GRIS_BORDE),
            right=Side(style='hair', color=self.GRIS_BORDE),
            top=Side(style='hair', color=self.GRIS_BORDE),
            bottom=Side(style='hair', color=self.GRIS_BORDE))
        fn = Font(name=self.FONT_NAME, size=9, color="333333")
        fl = Font(name=self.FONT_NAME, size=9, color="0563C1", underline='single')
        al = Alignment(vertical='center', wrap_text=True)
        fp = PatternFill(start_color=self.GRIS_CLARO, end_color=self.GRIS_CLARO, fill_type='solid')
        fi = PatternFill(start_color=self.BLANCO, end_color=self.BLANCO, fill_type='solid')
        arts = sorted(articulos,
                      key=lambda a: a.get("fecha_dt") or datetime.min.replace(tzinfo=timezone.utc),
                      reverse=True)
        for idx, art in enumerate(arts):
            row = idx + 2
            fill = fp if idx % 2 == 0 else fi
            c = ws.cell(row=row, column=1, value=art.get("fuente", ""))
            c.font = Font(name=self.FONT_NAME, size=9, bold=True, color="333333")
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.fill = fill; c.border = borde
            c = ws.cell(row=row, column=2, value=art.get("titulo", ""))
            c.font = fn; c.alignment = al; c.fill = fill; c.border = borde
            resumen = art.get("resumen", "")
            if len(resumen) > 150: resumen = resumen[:147] + "..."
            c = ws.cell(row=row, column=3, value=resumen)
            c.font = Font(name=self.FONT_NAME, size=8, color="666666")
            c.alignment = al; c.fill = fill; c.border = borde
            c = ws.cell(row=row, column=4, value=art.get("url", ""))
            c.font = fl; c.alignment = al; c.fill = fill; c.border = borde
            try: c.hyperlink = art["url"]
            except Exception: pass
            c = ws.cell(row=row, column=5, value=art.get("fecha_str", ""))
            c.font = fn
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.fill = fill; c.border = borde
            ws.row_dimensions[row].height = 22
        ws.column_dimensions['A'].width = 22
        ws.column_dimensions['B'].width = 55
        ws.column_dimensions['C'].width = 45
        ws.column_dimensions['D'].width = 50
        ws.column_dimensions['E'].width = 18
        uf = len(arts) + 1
        if uf > 1: ws.auto_filter.ref = f"A1:E{uf}"
        ws.freeze_panes = "A2"
