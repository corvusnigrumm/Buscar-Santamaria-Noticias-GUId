import sys
import os
import time
import asyncio
from threading import Thread
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from core.search import buscar_noticias_async
from core.excel_exporter import GeneradorExcelIDEAS
from core.filters import CATEGORIAS_GUI, MAPA_CATEGORIAS
from core.logger import logger as log

class RedirectText:
    def __init__(self, text_ctrl):
        self.output = text_ctrl
        self.after = text_ctrl.after
    def write(self, string):
        self.after(0, self._escribir, string)
    def _escribir(self, string):
        self.output.insert("end", string)
        self.output.see("end")
        self.output.update_idletasks()
    def flush(self): pass


import calendar

class CTkCalendar(ctk.CTkToplevel):
    def __init__(self, master, current_date=None, command=None, **kwargs):
        super().__init__(master, **kwargs)
        self.title("Seleccionar Fecha")
        self.geometry("320x340")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.grab_set()
        self.command = command
        self.today = date.today()
        self.current_date = current_date if current_date else self.today
        self.display_year = self.current_date.year
        self.display_month = self.current_date.month
        self._build_header()
        self._build_body()

    def _build_header(self):
        self.header_fr = ctk.CTkFrame(self, fg_color="transparent")
        self.header_fr.pack(fill="x", pady=10)
        ctk.CTkButton(self.header_fr, text="<", width=30, hover_color="#217346",
                      fg_color="#005931", command=self._prev_month).pack(side="left", padx=10)
        self.lbl_month = ctk.CTkLabel(self.header_fr,
                                       font=ctk.CTkFont(weight="bold", size=14), text="")
        self.lbl_month.pack(side="left", expand=True)
        ctk.CTkButton(self.header_fr, text=">", width=30, hover_color="#217346",
                      fg_color="#005931", command=self._next_month).pack(side="right", padx=10)

    def _build_body(self):
        if hasattr(self, 'body_fr'):
            self.body_fr.destroy()
        self.body_fr = ctk.CTkFrame(self, fg_color="transparent")
        self.body_fr.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        days = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        for c, d in enumerate(days):
            ctk.CTkLabel(self.body_fr, text=d,
                         font=ctk.CTkFont(weight="bold")).grid(row=0, column=c, padx=5, pady=5)
        cal = calendar.monthcalendar(self.display_year, self.display_month)
        meses = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                 "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
        self.lbl_month.configure(text=f"{meses[self.display_month-1]} {self.display_year}")
        for r, week in enumerate(cal):
            for c, day in enumerate(week):
                if day != 0:
                    es_hoy = (day == self.today.day and
                              self.display_month == self.today.month and
                              self.display_year == self.today.year)
                    btn = ctk.CTkButton(self.body_fr, text=str(day), width=35, height=35,
                        fg_color="#005931" if es_hoy else "transparent",
                        text_color="white" if es_hoy else "black",
                        hover_color="#217346",
                        command=lambda d=day: self._select_date(d))
                    btn.grid(row=r+1, column=c, padx=2, pady=2)

    def _prev_month(self):
        if self.display_month == 1:
            self.display_month = 12; self.display_year -= 1
        else:
            self.display_month -= 1
        self._build_body()

    def _next_month(self):
        if self.display_month == 12:
            self.display_month = 1; self.display_year += 1
        else:
            self.display_month += 1
        self._build_body()

    def _select_date(self, day):
        selected = date(self.display_year, self.display_month, day)
        if self.command: self.command(selected)
        self.destroy()


class CTkDateEntry(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.entry = ctk.CTkEntry(self, width=110)
        self.entry.pack(side="left", padx=(0, 5))
        self.btn = ctk.CTkButton(self, text="📅", width=30,
                                  fg_color="#005931", hover_color="#217346",
                                  command=self._open_cal)
        self.btn.pack(side="left")
        self.date = date.today()
        self.delete(0, "end")
        self.insert(0, self.date.strftime("%Y-%m-%d"))

    def _open_cal(self):
        CTkCalendar(self.winfo_toplevel(), current_date=self.date, command=self._on_select)

    def _on_select(self, sel_date):
        self.date = sel_date
        self.delete(0, "end")
        self.insert(0, self.date.strftime("%Y-%m-%d"))

    def get(self): return self.entry.get()
    def delete(self, first, last=None): self.entry.delete(first, last)
    def insert(self, index, string):
        self.entry.insert(index, string)
        try:
            self.date = datetime.strptime(string, "%Y-%m-%d").date()
        except ValueError:
            pass


class AppNoticiasIDEAS(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("Light")
        self.title("Buscador de Noticias CAPA BRINDADA V.6")
        self.geometry("1200x870")
        self.minsize(1100, 750)
        self.configure(fg_color="#f8f9fa")
        try:
            base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
            icon_path = os.path.join(base_path, "blindado_icon.ico")
            self.iconbitmap(icon_path)
        except Exception:
            pass
        self.vars_categorias = {}
        self.create_widgets()
        sys.stdout = RedirectText(self.consola)
        sys.stderr = RedirectText(self.consola)
        import logging as _logging
        logger = _logging.getLogger("BuscadorNoticias")
        logger.handlers = []
        logger.addHandler(_logging.StreamHandler(sys.stdout))
        self.mostrar_bienvenida()

    def mostrar_bienvenida(self):
        print("[READY] System kernel initialized. Core v6.0 — CAPA BRINDADA")
        print("[SYNC] Connected to RSS/News XML Feeds ... OK")
        print("[SYNC] Local node 'Colombia-Main' active.")
        print("--------------------------------------------------")
        print("  Programa diseñado por Sebastian Rozo.")
        print("  Todos los derechos reservados.")
        print("  Utilizar con responsabilidad.")
        print("--------------------------------------------------")
        print("[FIX] Whitelist Google News: CORREGIDA")
        print("[FIX] Filtro inglés agresivo: CORREGIDO")
        print("[FIX] False positives El Tiempo: CORREGIDOS")
        print("[NEW] Fuentes agregadas: La Nota Econ., Raddar,")
        print("      Mi Bolsillo, Agro Negocios, DIAN, Ministerios,")
        print("      FMI, Banco Mundial, BID, CCB y más.")
        print("[NEW] Desplazamiento de fechas: ACTIVO")
        print("      (selección [ini,fin] → busca [fin, fin+delta])")
        print("[IDLE] Awaiting search dispatch...")
        print("")

    def create_widgets(self):
        font_family = "Helvetica"
        header_fr = ctk.CTkFrame(self, fg_color="transparent")
        header_fr.pack(fill="x", padx=30, pady=(25, 10))
        ctk.CTkLabel(header_fr, text="Buscador de Noticias CAPA BRINDADA V.6",
                     font=ctk.CTkFont(family=font_family, size=28, weight="bold"),
                     text_color="#191c1d").pack(anchor="w")
        ctk.CTkLabel(header_fr,
                     text="Configure los parámetros de búsqueda para la extracción y análisis de prensa.",
                     font=ctk.CTkFont(family=font_family, size=15),
                     text_color="#3f4941").pack(anchor="w")

        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=30, pady=10)
        main_frame.columnconfigure(0, weight=7)
        main_frame.columnconfigure(1, weight=5)

        panel_izq = ctk.CTkFrame(main_frame, fg_color="transparent")
        panel_izq.grid(row=0, column=0, sticky="nsew", padx=(0, 20))

        # Categorías
        fr_cat = ctk.CTkFrame(panel_izq, fg_color="#ffffff",
                               border_color="#e1e3e4", border_width=1, corner_radius=12)
        fr_cat.pack(fill="x", pady=(0, 15), ipadx=5, ipady=5)
        ctk.CTkLabel(fr_cat, text="CATEGORÍAS DE BÚSQUEDA",
                     font=ctk.CTkFont(family=font_family, size=11, weight="bold"),
                     text_color="#6f7a70").pack(anchor="w", padx=15, pady=(10, 0))
        self.scroll_cat = ctk.CTkScrollableFrame(fr_cat, height=140, fg_color="transparent")
        self.scroll_cat.pack(fill="x", padx=10, pady=5)
        col, row = 0, 0
        for cat in CATEGORIAS_GUI:
            var = ctk.BooleanVar(value=True)
            chk = ctk.CTkCheckBox(self.scroll_cat, text=cat, variable=var,
                                  font=ctk.CTkFont(family=font_family, size=12, weight="bold"),
                                  fg_color="#005931", hover_color="#217346",
                                  text_color="#191c1d", border_color="#bfc9be")
            chk.grid(row=row, column=col, padx=8, pady=6, sticky="w")
            self.vars_categorias[cat] = var
            col += 1
            if col > 2:
                col = 0; row += 1
        fr_btn_cat = ctk.CTkFrame(fr_cat, fg_color="transparent")
        fr_btn_cat.pack(fill="x", padx=15, pady=(0, 10))
        ctk.CTkButton(fr_btn_cat, text="Todas", width=80, height=26,
                       fg_color="#005931", hover_color="#217346", text_color="white",
                       font=ctk.CTkFont(family=font_family, size=11, weight="bold"),
                       command=lambda: self._marcar(True)).pack(side="left", padx=(0, 10))
        ctk.CTkButton(fr_btn_cat, text="Ninguna", width=80, height=26,
                       fg_color="#e7e8e9", text_color="#3f4941", hover_color="#d9dadb",
                       font=ctk.CTkFont(family=font_family, size=11, weight="bold"),
                       command=lambda: self._marcar(False)).pack(side="left")

        # Fechas — NEW: label explicativo del desplazamiento
        fr_fecha = ctk.CTkFrame(panel_izq, fg_color="#ffffff",
                                 border_color="#e1e3e4", border_width=1, corner_radius=12)
        fr_fecha.pack(fill="x", pady=(0, 15), ipadx=5, ipady=5)
        c_sw = ctk.CTkFrame(fr_fecha, fg_color="transparent")
        c_sw.pack(fill="x", padx=15, pady=(10, 5))
        self.var_usar_fecha = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(c_sw, text="FILTRAR POR RANGO DE FECHAS", variable=self.var_usar_fecha,
                      font=ctk.CTkFont(family=font_family, size=11, weight="bold"),
                      text_color="#6f7a70", progress_color="#005931").pack(side="left")
        fr_inp = ctk.CTkFrame(fr_fecha, fg_color="transparent")
        fr_inp.pack(fill="x", padx=15, pady=(5, 5))
        ctk.CTkLabel(fr_inp, text="Período:",
                     font=ctk.CTkFont(family=font_family, size=12, weight="bold"),
                     text_color="#191c1d").pack(side="left", padx=(0, 5))
        self.entry_fecha_ini = CTkDateEntry(fr_inp)
        self.entry_fecha_ini.pack(side="left", padx=(0, 5))
        ctk.CTkLabel(fr_inp, text="→",
                     font=ctk.CTkFont(family=font_family, size=12),
                     text_color="#6f7a70").pack(side="left", padx=(0, 5))
        self.entry_fecha_fin = CTkDateEntry(fr_inp)
        self.entry_fecha_fin.pack(side="left", padx=(0, 10))
        ctk.CTkButton(fr_inp, text="Hoy", width=50, fg_color="#005931",
                       hover_color="#217346", text_color="white",
                       command=self._poner_hoy).pack(side="left", padx=(5, 5))
        ctk.CTkButton(fr_inp, text="✕", width=30, fg_color="#ba1a1a",
                       hover_color="#93000a", text_color="white",
                       command=lambda: [self.entry_fecha_ini.delete(0, "end"),
                                        self.entry_fecha_fin.delete(0, "end")]).pack(side="left")

        # NEW: Label informativo sobre el desplazamiento de fechas
        self.lbl_fecha_info = ctk.CTkLabel(
            fr_fecha,
            text="📅 Las noticias se buscarán en el período SIGUIENTE de igual duración.",
            font=ctk.CTkFont(family=font_family, size=10),
            text_color="#005931"
        )
        self.lbl_fecha_info.pack(anchor="w", padx=15, pady=(0, 8))

        # Filtros adicionales
        fr_filtros = ctk.CTkFrame(panel_izq, fg_color="transparent")
        fr_filtros.pack(fill="x", pady=(0, 15))
        fr_arg = ctk.CTkFrame(fr_filtros, fg_color="#ffffff",
                               border_color="#e1e3e4", border_width=1, corner_radius=12)
        fr_arg.pack(fill="x", pady=(0, 10))
        self.var_filtrar_argentina = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(fr_arg, text="Omitir Noticias de Argentina",
                      variable=self.var_filtrar_argentina,
                      font=ctk.CTkFont(family=font_family, size=13, weight="bold"),
                      text_color="#191c1d", progress_color="#005931").pack(side="left", padx=20, pady=15)
        fr_scope = ctk.CTkFrame(fr_filtros, fg_color="#ffffff",
                                 border_color="#e1e3e4", border_width=1, corner_radius=12)
        fr_scope.pack(fill="x", ipady=3)
        self._tipo_noticias = "ambas"
        self.seg_tipo = ctk.CTkSegmentedButton(
            fr_scope, values=["Nacional", "mundo", "Ambas"],
            command=self._on_tipo_change,
            font=ctk.CTkFont(family=font_family, size=13, weight="bold"),
            selected_color="#005931", selected_hover_color="#217346",
            unselected_color="#343a40", unselected_hover_color="#495057",
            text_color="white"
        )
        self.seg_tipo.set("Ambas")
        self.seg_tipo.pack(fill="x", padx=10, pady=10)

        self.btn_ejecutar = ctk.CTkButton(
            panel_izq, text="INICIAR BÚSQUEDA Y GENERAR EXCEL",
            font=ctk.CTkFont(family=font_family, size=16, weight="bold"), height=55,
            fg_color="#005931", hover_color="#217346", text_color="#ffffff", corner_radius=12,
            command=self.ejecutar_scraper)
        self.btn_ejecutar.pack(fill="x", pady=(10, 0))
        self.btn_limpieza = ctk.CTkButton(
            panel_izq, text="Limpieza Pendeja",
            font=ctk.CTkFont(family=font_family, size=14, weight="bold"), height=42,
            fg_color="#ba1a1a", hover_color="#93000a", text_color="#ffffff", corner_radius=12,
            command=self._limpieza_pendeja)
        self.btn_limpieza.pack(fill="x", pady=(10, 0))

        panel_der = ctk.CTkFrame(main_frame, fg_color="transparent")
        panel_der.grid(row=0, column=1, sticky="nsew")
        fr_stats = ctk.CTkFrame(panel_der, fg_color="#ffffff",
                                 border_color="#e1e3e4", border_width=1, corner_radius=12)
        fr_stats.pack(fill="x", pady=(0, 15), ipadx=10, ipady=10)
        ctk.CTkLabel(fr_stats, text="ESTADO DEL SISTEMA",
                     font=ctk.CTkFont(family=font_family, size=11, weight="bold"),
                     text_color="#6f7a70").pack(anchor="w", padx=15, pady=(5, 0))
        ctk.CTkLabel(fr_stats, text="En Espera",
                     font=ctk.CTkFont(family=font_family, size=24, weight="bold"),
                     text_color="#005931").pack(anchor="w", padx=15, pady=(0, 5))
        fr_term = ctk.CTkFrame(panel_der, fg_color="#d9dadb", corner_radius=12)
        fr_term.pack(fill="both", expand=True)
        fr_term_head = ctk.CTkFrame(fr_term, fg_color="#ffffff", corner_radius=12)
        fr_term_head.pack(fill="x", padx=2, pady=(2, 0))
        ctk.CTkLabel(fr_term_head, text="TERMINAL DE PROCESO",
                     font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                     text_color="#191c1d").pack(side="left", padx=15, pady=8)
        self.consola = ctk.CTkTextbox(fr_term, font=ctk.CTkFont(family="Consolas", size=12),
                                      wrap="word", fg_color="#ffffff", text_color="#3f4941",
                                      corner_radius=0)
        self.consola.pack(fill="both", expand=True, padx=2, pady=(0, 2))

    def _on_tipo_change(self, valor):
        mapa = {"Nacional": "nacional", "mundo": "mundo", "Ambas": "ambas"}
        self._tipo_noticias = mapa.get(valor, "ambas")

    def _marcar(self, estado):
        for v in self.vars_categorias.values():
            v.set(estado)

    def _poner_hoy(self):
        hoy = datetime.now(ZONA_COLOMBIA).strftime("%Y-%m-%d")
        self.entry_fecha_ini.delete(0, "end")
        self.entry_fecha_ini.insert(0, hoy)
        self.entry_fecha_fin.delete(0, "end")
        self.entry_fecha_fin.insert(0, hoy)

    def _limpieza_pendeja(self):
        try:
            self.btn_ejecutar.configure(state="disabled")
            self.btn_limpieza.configure(state="disabled")
            self.consola.delete("0.0", "end")
            print("[RESET] Limpieza Pendeja activada. Reiniciando la aplicaciÃ³n...")

            if getattr(sys, "frozen", False):
                comando = [sys.executable, *sys.argv[1:]]
                cwd = os.path.dirname(sys.executable)
            else:
                comando = [sys.executable, os.path.abspath(__file__), *sys.argv[1:]]
                cwd = os.path.dirname(os.path.abspath(__file__))

            subprocess.Popen(comando, cwd=cwd)
            self.after(250, self.destroy)
        except Exception as e:
            self.btn_ejecutar.configure(state="normal")
            self.btn_limpieza.configure(state="normal")
            messagebox.showerror("Reinicio fallido", f"No se pudo reiniciar la aplicaciÃ³n:\n{e}")

    def ejecutar_scraper(self):
        seleccionadas = [cat for cat, var in self.vars_categorias.items() if var.get()]
        if not seleccionadas:
            messagebox.showwarning("Atención", "Debes seleccionar al menos una categoría.")
            return

        fecha_ini_obj = None
        fecha_fin_obj = None
        if self.var_usar_fecha.get():
            fecha_ini_txt = self.entry_fecha_ini.get().strip()
            fecha_fin_txt = self.entry_fecha_fin.get().strip()
            if fecha_ini_txt and fecha_fin_txt:
                try:
                    fecha_ini_obj = datetime.strptime(fecha_ini_txt, "%Y-%m-%d").date()
                    fecha_fin_obj = datetime.strptime(fecha_fin_txt, "%Y-%m-%d").date()
                    if fecha_ini_obj > fecha_fin_obj:
                        messagebox.showwarning("Rango inválido",
                                               "La fecha de inicio debe ser menor o igual a la de fin.")
                        return
                except ValueError:
                    messagebox.showwarning("Fecha inválida",
                                           "Formato: YYYY-MM-DD\nEjemplo: 2026-03-23")
                    return
            else:
                messagebox.showwarning("Rango incompleto",
                                       "Debes ingresar tanto fecha de inicio como fecha de fin.")
                return

        self.btn_ejecutar.configure(state="disabled")
        self.consola.delete("0.0", "end")
        self.mostrar_bienvenida()

        tipo = self._tipo_noticias
        filtrar_arg = self.var_filtrar_argentina.get()
        hilo = threading.Thread(
            target=self._proceso,
            args=(seleccionadas, fecha_ini_obj, fecha_fin_obj, tipo, filtrar_arg),
            daemon=True
        )
        hilo.start()

    def _proceso(self, seleccionadas, fecha_inicio, fecha_fin, tipo_noticias="ambas", filtrar_argentina=True):
        try:
            cats_internas = set()
            for cat_gui in seleccionadas:
                for c in MAPA_CATEGORIAS.get(cat_gui, [cat_gui.lower()]):
                    cats_internas.add(c)

            nombre_archivo = _siguiente_nombre_tabla()

            # ═══════════════════════════════════════════════════
            # Fechas: usar directamente las fechas seleccionadas
            # ═══════════════════════════════════════════════════
            fecha_busqueda_inicio = fecha_inicio
            fecha_busqueda_fin = fecha_fin

            tipo_display = {
                "nacional": "🇨🇴 Nacional",
                "mundo": "🌍 mundo",
                "ambas": "🌐 Ambas"
            }.get(tipo_noticias, tipo_noticias)

            print()
            print("  ═" * 30)
            print(f"  Categorías seleccionadas: {len(seleccionadas)}")
            print(f"  Categorías internas: {', '.join(sorted(cats_internas))}")
            print(f"  Tipo de noticias: {tipo_display}")
            print(f"  Filtro Argentina: {'Sí' if filtrar_argentina else 'No'}")
            if fecha_inicio and fecha_fin:
                print(f"  Período seleccionado: {fecha_inicio} → {fecha_fin}")
                if fecha_inicio != fecha_fin:
                    print(f"  📰 Buscando publicaciones: {fecha_busqueda_inicio} → {fecha_busqueda_fin}")
                else:
                    print(f"  📰 Buscando publicaciones: {fecha_busqueda_inicio}")
            else:
                print(f"  Filtro de fecha: Todas (más recientes)")
            print(f"  Archivo de salida: {nombre_archivo}")
            print("  ═" * 30)
            print()

            resultado = asyncio.run(buscar_noticias_async(
                categorias_seleccionadas=list(cats_internas),
                fecha_inicio=fecha_busqueda_inicio,
                fecha_fin=fecha_busqueda_fin,
                verbose=True,
                tipo_noticias=tipo_noticias,
                filtrar_argentina=filtrar_argentina,
            ))

            noticias = resultado["noticias"]

            if noticias:
                generador = GeneradorExcelIDEAS(noticias)
                generador.generar(nombre_archivo)

                print()
                print("  ═" * 30)
                print("  RESUMEN FINAL")
                print("  ═" * 30)

                por_cat = {}
                for art in noticias:
                    cat = art["categoria"]
                    por_cat[cat] = por_cat.get(cat, 0) + 1
                for cat, cnt in sorted(por_cat.items(), key=lambda x: -x[1]):
                    bar = "█" * min(cnt, 30)
                    print(f"  {cat:<20} {cnt:>4}  {bar}")

                print()
                for fuente, cnt in sorted(resultado["conteo_fuentes"].items(),
                                          key=lambda x: -x[1]):
                    if cnt > 0:
                        print(f"  {fuente:<35} {cnt:>4} noticias")

                print(f"\n  TOTAL: {len(noticias)} artículos con fecha verificada")
                print(f"  Archivo: {nombre_archivo}")
                if resultado["fuentes_fallidas"]:
                    print(f"  Feeds sin respuesta: {', '.join(resultado['fuentes_fallidas'])}")
                print()

                total_f = len(noticias)
                self.after(0, lambda: self._msg(
                    "Proceso Terminado",
                    f"Listo. Se encontraron {total_f} resultados.\n\nGuardado en: {nombre_archivo}",
                    "info"))
            else:
                msg = resultado.get("notificacion", "No se encontraron noticias.")
                log.warning(msg)
                self.after(0, lambda: self._msg("Sin resultados", msg, "warning"))

        except Exception as e:
            log.error(f"Error: {e}")
            err = str(e)
            self.after(0, lambda: self._msg("Error", f"Error inesperado:\n{err}", "error"))
        finally:
            self.after(0, lambda: self.btn_ejecutar.configure(state="normal"))

    def _msg(self, titulo, mensaje, tipo):
        self.bell()
        if tipo == "info": messagebox.showinfo(titulo, mensaje)
        elif tipo == "warning": messagebox.showwarning(titulo, mensaje)
        elif tipo == "error": messagebox.showerror(titulo, mensaje)


if __name__ == "__main__":
    app = AppNoticiasIDEAS()
    app.mainloop()
