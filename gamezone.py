#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GAMEZONE · Analizador funcional de datos de ventas
Proyecto integrador – Programación Lógica y Funcional, Unidad 2 (Python funcional)

Pipeline:   datos → filtrar → transformar → agregar → resultados

Requisitos: Python 3.8+ (tkinter viene incluido en la instalación de Windows/macOS).
Ejecutar:   python gamezone.py
"""
import csv
import random
import tkinter as tk
from collections import namedtuple
from datetime import date, timedelta
from functools import reduce
from itertools import accumulate
from operator import itemgetter
from tkinter import ttk, filedialog, messagebox

# ═══════════════════════════════════════════════════════════════════════════
#  1. MODELO DE DATOS (inmutable)
# ═══════════════════════════════════════════════════════════════════════════
Venta = namedtuple(
    "Venta",
    "producto categoria precio cantidad fecha vendedor importe",
    defaults=(0.0,),          # importe se calcula en la etapa "transformar"
)

# (producto, categoría, precio MXN, popularidad)
CATALOGO = (
    ("PlayStation 5", "Consolas", 12499, 3),
    ("Xbox Series X", "Consolas", 11999, 2),
    ("Nintendo Switch OLED", "Consolas", 7999, 4),
    ("Steam Deck", "Consolas", 10999, 1),
    ("Zelda: Tears of the Kingdom", "Videojuegos", 1399, 5),
    ("Mario Kart 8 Deluxe", "Videojuegos", 1299, 5),
    ("God of War Ragnarök", "Videojuegos", 1199, 4),
    ("EA Sports FC", "Videojuegos", 1499, 6),
    ("Control DualSense", "Accesorios", 1699, 6),
    ("Headset Gamer", "Accesorios", 1499, 5),
    ("Tarjeta microSD 256GB", "Accesorios", 799, 5),
    ("Cable HDMI 2.1", "Accesorios", 249, 4),
    ("Funko Pop Mario", "Coleccionables", 399, 4),
    ("Figura Kratos", "Coleccionables", 1299, 2),
    ("Póster Retro Arcade", "Coleccionables", 199, 3),
)
VENDEDORES = ("Ana", "Luis", "Carla", "Miguel")


def generar_ventas(n=400, semilla=7):
    """Datos de ejemplo (el único punto con aleatoriedad; el resto es puro)."""
    rng = random.Random(semilla)
    hoy = date.today()
    pesos = [p[3] for p in CATALOGO]

    def una_venta(_):
        producto, categoria, precio, _pop = rng.choices(CATALOGO, weights=pesos)[0]
        max_cant = 2 if categoria == "Consolas" else 4
        return Venta(producto, categoria, float(precio), rng.randint(1, max_cant),
                     hoy - timedelta(days=rng.randint(0, 179)), rng.choice(VENDEDORES))

    return tuple(map(una_venta, range(n)))


def leer_filas(ruta):
    """GENERADOR: produce una Venta por cada fila del CSV (perezoso, con yield)."""
    with open(ruta, newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            yield Venta(fila["producto"], fila["categoria"], float(fila["precio"]),
                        int(fila["cantidad"]), date.fromisoformat(fila["fecha"]),
                        fila["vendedor"])


def escribir_csv(ruta, ventas):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(Venta._fields)
        w.writerows(ventas)


# ═══════════════════════════════════════════════════════════════════════════
#  2. ETAPA FILTRAR — predicados puros que se combinan
# ═══════════════════════════════════════════════════════════════════════════
def pred_categoria(cat):
    return lambda v: cat in (None, "", "Todas") or v.categoria == cat


def pred_vendedor(vend):
    return lambda v: vend in (None, "", "Todos") or v.vendedor == vend


def pred_fechas(desde, hasta):
    return lambda v: (desde is None or v.fecha >= desde) and (hasta is None or v.fecha <= hasta)


def pred_monto(minimo):
    return lambda v: v.precio * v.cantidad >= minimo


def todos(*preds):
    """Combina predicados con AND."""
    return lambda v: all(p(v) for p in preds)


def etapa_filtrar(pred):
    return lambda datos: tuple(filter(pred, datos))


# ═══════════════════════════════════════════════════════════════════════════
#  3. ETAPA TRANSFORMAR — map: importe = precio × cantidad
# ═══════════════════════════════════════════════════════════════════════════
def calcular_importe(v):
    return v._replace(importe=round(v.precio * v.cantidad, 2))   # copia nueva, sin mutar


def etapa_transformar(datos):
    return tuple(map(calcular_importe, datos))


# ═══════════════════════════════════════════════════════════════════════════
#  4. ETAPA AGREGAR — reduce: totales e indicadores
# ═══════════════════════════════════════════════════════════════════════════
def sumar_por(clave, valor=lambda v: v.importe):
    """Fábrica de agrupadores: suma 'valor' agrupando por 'clave' usando reduce."""
    def paso(acc, v):
        k = clave(v)
        return {**acc, k: acc.get(k, 0) + valor(v)}
    return lambda ventas: reduce(paso, ventas, {})


def etapa_agregar(ventas):
    total = reduce(lambda a, v: a + v.importe, ventas, 0.0)
    unidades = sum(v.cantidad for v in ventas)                   # expresión generadora
    por_producto = sumar_por(lambda v: v.producto)(ventas)
    return {
        "registros": len(ventas),
        "total": total,
        "unidades": unidades,
        "ticket": total / len(ventas) if ventas else 0.0,
        "top_producto": max(por_producto.items(), key=itemgetter(1), default=("—", 0.0)),
        "por_categoria": sumar_por(lambda v: v.categoria)(ventas),
        "por_vendedor": sumar_por(lambda v: v.vendedor)(ventas),
        "por_mes": sumar_por(lambda v: v.fecha.strftime("%Y-%m"))(ventas),
        "por_producto": por_producto,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  5. PIPELINE — composición de etapas
# ═══════════════════════════════════════════════════════════════════════════
def construir_pipeline(pred):
    return (etapa_filtrar(pred), etapa_transformar, etapa_agregar)


def ejecutar_pipeline(datos, etapas):
    """Devuelve el estado tras cada etapa: (datos, filtrados, transformados, resultados)."""
    return tuple(accumulate(etapas, lambda estado, etapa: etapa(estado), initial=datos))


def parse_fecha(texto):
    texto = texto.strip()
    return date.fromisoformat(texto) if texto else None


def dinero(x):
    return f"${x:,.2f}"


def dinero_corto(x):
    return f"${x:,.0f}"


# ═══════════════════════════════════════════════════════════════════════════
#  6. INTERFAZ GRÁFICA (tkinter) — estética arcade / neón
# ═══════════════════════════════════════════════════════════════════════════
BG, PANEL, PANEL2 = "#0b0b1e", "#16163a", "#1f1f4f"
CYAN, PINK, LIME, GOLD = "#00e5ff", "#ff2e97", "#39ff14", "#ffd400"
TXT, MUTED = "#e8e8ff", "#8a8ab8"
FUENTE = "Consolas"

CONCEPTOS = """\
▸ Funciones puras   pred_*, calcular_importe, etapa_*  → misma entrada, misma salida, sin efectos
▸ Inmutabilidad     Venta es namedtuple; _replace() crea una copia en vez de modificar
▸ filter            etapa_filtrar(pred) con predicados combinados mediante todos()
▸ map               etapa_transformar → importe = precio × cantidad
▸ reduce            sumar_por() y etapa_agregar → totales y agrupaciones
▸ Comprensiones     {v.categoria for v in datos}  ·  sum(v.cantidad for v in ventas)
▸ Generadores       leer_filas() con yield (lectura perezosa del CSV)
▸ Composición       ejecutar_pipeline() encadena las etapas con accumulate()
"""


def dibujar_barras(cv, datos, titulo, color, por_valor=True, max_barras=6):
    cv.delete("all")
    w, h = cv.winfo_width(), cv.winfo_height()
    cv.create_text(12, 16, text=titulo.upper(), anchor="w", fill=TXT, font=(FUENTE, 10, "bold"))
    if not datos:
        cv.create_text(w / 2, h / 2, text="Sin datos con estos filtros", fill=MUTED, font=(FUENTE, 10))
        return
    orden = sorted(datos.items(), key=(lambda kv: -kv[1]) if por_valor else itemgetter(0))
    items = orden[:max_barras] if por_valor else orden[-max_barras:]
    maximo = max(v for _, v in items) or 1
    x0, x1 = 150, max(w - 95, 230)
    paso = max((h - 40) / len(items), 16)
    alto = min(paso * 0.62, 24)
    for i, (k, v) in enumerate(items):
        y = 36 + i * paso
        largo = max((x1 - x0) * v / maximo, 2)
        etiqueta = str(k) if len(str(k)) <= 17 else str(k)[:16] + "…"
        cv.create_text(x0 - 8, y + alto / 2, text=etiqueta, anchor="e", fill=MUTED, font=(FUENTE, 9))
        cv.create_rectangle(x0, y, x0 + largo, y + alto, fill=color, outline="")
        cv.create_text(x0 + largo + 6, y + alto / 2, text=dinero_corto(v), anchor="w",
                       fill=TXT, font=(FUENTE, 9, "bold"))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GAMEZONE · Analizador funcional de ventas")
        self.geometry("1200x760")
        self.minsize(1000, 660)
        self.configure(bg=BG)
        self.datos = generar_ventas()
        self.estados = ()
        self._estilos()
        self._encabezado()
        self.barra = tk.Label(self, text="", bg=PANEL, fg=MUTED, anchor="w", font=(FUENTE, 9), padx=12, pady=4)
        self.barra.pack(side="bottom", fill="x")
        cuerpo = tk.Frame(self, bg=BG)
        cuerpo.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self._panel_filtros(cuerpo)
        self._pestanas(cuerpo)
        self._limpiar()

    # ── estilos y encabezado ────────────────────────────────────────────
    def _estilos(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(18, 8),
                    font=(FUENTE, 10, "bold"), borderwidth=0)
        s.map("TNotebook.Tab", background=[("selected", PANEL2)], foreground=[("selected", CYAN)])
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TXT,
                    rowheight=24, borderwidth=0, font=(FUENTE, 10))
        s.configure("Treeview.Heading", background=PANEL2, foreground=CYAN, relief="flat",
                    font=(FUENTE, 10, "bold"))
        s.map("Treeview", background=[("selected", PINK)], foreground=[("selected", "white")])
        s.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=TXT,
                    arrowcolor=CYAN, borderwidth=0)
        s.map("TCombobox", fieldbackground=[("readonly", PANEL2)], foreground=[("readonly", TXT)])
        s.configure("Vertical.TScrollbar", background=PANEL2, troughcolor=PANEL, arrowcolor=CYAN)
        self.option_add("*TCombobox*Listbox.background", PANEL2)
        self.option_add("*TCombobox*Listbox.foreground", TXT)
        self.option_add("*TCombobox*Listbox.selectBackground", PINK)

    def _encabezado(self):
        f = tk.Frame(self, bg=BG)
        f.pack(fill="x", padx=16, pady=(12, 8))
        tk.Label(f, text="▶ GAMEZONE", bg=BG, fg=PINK, font=(FUENTE, 24, "bold")).pack(side="left")
        tk.Label(f, text="  Consolas · Videojuegos · Accesorios · Coleccionables",
                 bg=BG, fg=CYAN, font=(FUENTE, 11)).pack(side="left", pady=(10, 0))
        tk.Label(f, text="datos → filtrar → transformar → agregar → resultados",
                 bg=BG, fg=MUTED, font=(FUENTE, 10)).pack(side="right", pady=(10, 0))
        tk.Frame(self, bg=PINK, height=2).pack(fill="x", padx=16, pady=(0, 10))

    # ── panel lateral de filtros ────────────────────────────────────────
    def _panel_filtros(self, padre):
        f = tk.Frame(padre, bg=PANEL, width=250)
        f.pack(side="left", fill="y", padx=(0, 12))
        f.pack_propagate(False)
        tk.Label(f, text="◆ FILTROS", bg=PANEL, fg=LIME, font=(FUENTE, 12, "bold")).pack(anchor="w", padx=14, pady=(14, 0))
        self.v_cat, self.v_vend = tk.StringVar(), tk.StringVar()
        self.v_desde, self.v_hasta, self.v_monto = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.cb_cat = self._combo(f, "Categoría", self.v_cat)
        self.cb_vend = self._combo(f, "Vendedor", self.v_vend)
        self._entrada(f, "Desde (AAAA-MM-DD)", self.v_desde)
        self._entrada(f, "Hasta (AAAA-MM-DD)", self.v_hasta)
        self._entrada(f, "Monto mínimo por venta ($)", self.v_monto)
        tk.Frame(f, bg=PANEL, height=10).pack()
        self._boton(f, "▶ APLICAR PIPELINE", self.aplicar, LIME)
        self._boton(f, "Limpiar filtros", self._limpiar, MUTED)
        tk.Frame(f, bg=PANEL2, height=2).pack(fill="x", padx=14, pady=10)
        self._boton(f, "Cargar CSV…", self.cargar_csv, CYAN)
        self._boton(f, "Exportar resultado…", self.exportar_csv, GOLD)
        self._boton(f, "Datos de ejemplo nuevos", self.regenerar, PINK)

    def _etiqueta(self, padre, texto):
        tk.Label(padre, text=texto, bg=PANEL, fg=MUTED, font=(FUENTE, 9)).pack(anchor="w", padx=14, pady=(10, 2))

    def _combo(self, padre, texto, var):
        self._etiqueta(padre, texto)
        c = ttk.Combobox(padre, textvariable=var, state="readonly", font=(FUENTE, 10))
        c.pack(fill="x", padx=14)
        c.bind("<<ComboboxSelected>>", lambda e: self.aplicar())
        return c

    def _entrada(self, padre, texto, var):
        self._etiqueta(padre, texto)
        e = tk.Entry(padre, textvariable=var, bg=PANEL2, fg=TXT, insertbackground=CYAN,
                     relief="flat", font=(FUENTE, 10))
        e.pack(fill="x", padx=14, ipady=4)
        e.bind("<Return>", lambda ev: self.aplicar())

    def _boton(self, padre, texto, comando, color):
        tk.Button(padre, text=texto, command=comando, bg=color, fg=BG, activebackground=TXT,
                  activeforeground=BG, relief="flat", bd=0, cursor="hand2", pady=7,
                  font=(FUENTE, 10, "bold")).pack(fill="x", padx=14, pady=4)

    # ── pestañas ────────────────────────────────────────────────────────
    def _pestanas(self, padre):
        nb = ttk.Notebook(padre)
        nb.pack(side="left", fill="both", expand=True)
        dash, tabla, pipe = (tk.Frame(nb, bg=BG) for _ in range(3))
        nb.add(dash, text="  DASHBOARD  ")
        nb.add(tabla, text="  VENTAS  ")
        nb.add(pipe, text="  PIPELINE  ")
        self._tab_dashboard(dash)
        self._tab_tabla(tabla)
        self._tab_pipeline(pipe)

    def _tab_dashboard(self, padre):
        fila = tk.Frame(padre, bg=BG)
        fila.pack(fill="x", pady=(10, 4))
        self.kpi = {}
        tarjetas = (("total", "INGRESOS", LIME), ("unidades", "UNIDADES VENDIDAS", CYAN),
                    ("ticket", "TICKET PROMEDIO", GOLD), ("top", "MÁS VENDIDO ($)", PINK))
        for i, (clave, titulo, color) in enumerate(tarjetas):
            c = tk.Frame(fila, bg=PANEL, highlightbackground=color, highlightthickness=2)
            c.grid(row=0, column=i, sticky="nsew", padx=5)
            fila.columnconfigure(i, weight=1, uniform="kpi")
            tk.Label(c, text=titulo, bg=PANEL, fg=MUTED, font=(FUENTE, 9, "bold")).pack(anchor="w", padx=10, pady=(8, 0))
            lbl = tk.Label(c, text="—", bg=PANEL, fg=color, font=(FUENTE, 15, "bold"),
                           wraplength=180, justify="left")
            lbl.pack(anchor="w", padx=10, pady=(0, 8))
            self.kpi[clave] = lbl

        rejilla = tk.Frame(padre, bg=BG)
        rejilla.pack(fill="both", expand=True, pady=(4, 0))
        self.graficas = {}
        config = (("por_categoria", "Ingresos por categoría", PINK, True),
                  ("por_vendedor", "Ingresos por vendedor", CYAN, True),
                  ("por_mes", "Ingresos por mes", LIME, False),
                  ("por_producto", "Top productos", GOLD, True))
        for i, (clave, titulo, color, por_valor) in enumerate(config):
            cv = tk.Canvas(rejilla, bg=PANEL, highlightthickness=0, height=180)
            cv.grid(row=i // 2, column=i % 2, sticky="nsew", padx=5, pady=5)
            cv.bind("<Configure>", lambda e: self._dibujar_graficas())
            self.graficas[clave] = (cv, titulo, color, por_valor)
        for idx in range(2):
            rejilla.columnconfigure(idx, weight=1, uniform="g")
            rejilla.rowconfigure(idx, weight=1, uniform="g")

    def _tab_tabla(self, padre):
        cols = ("fecha", "producto", "categoria", "precio", "cantidad", "importe", "vendedor")
        anchos = (95, 230, 110, 100, 70, 110, 90)
        self.tree = ttk.Treeview(padre, columns=cols, show="headings")
        for c, a in zip(cols, anchos):
            self.tree.heading(c, text=c.upper())
            self.tree.column(c, width=a, anchor="w" if c in ("producto", "categoria", "vendedor") else "e")
        sb = ttk.Scrollbar(padre, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", pady=10)
        self.tree.pack(fill="both", expand=True, pady=10)

    def _tab_pipeline(self, padre):
        self.cv_pipe = tk.Canvas(padre, bg=PANEL, highlightthickness=0, height=180)
        self.cv_pipe.pack(fill="x", pady=(10, 8))
        self.cv_pipe.bind("<Configure>", lambda e: self._dibujar_pipeline())
        tk.Label(padre, text="CONCEPTOS FUNCIONALES USADOS", bg=BG, fg=LIME,
                 font=(FUENTE, 11, "bold")).pack(anchor="w", padx=4)
        txt = tk.Text(padre, bg=PANEL, fg=TXT, relief="flat", font=(FUENTE, 10), padx=12, pady=10, height=10)
        txt.insert("1.0", CONCEPTOS)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True, pady=(4, 10))

    # ── acciones ────────────────────────────────────────────────────────
    def aplicar(self):
        try:
            desde, hasta = parse_fecha(self.v_desde.get()), parse_fecha(self.v_hasta.get())
            minimo = float(self.v_monto.get() or 0)
        except ValueError:
            messagebox.showerror("Dato inválido", "Fechas: AAAA-MM-DD\nMonto mínimo: un número.")
            return
        pred = todos(pred_categoria(self.v_cat.get()), pred_vendedor(self.v_vend.get()),
                     pred_fechas(desde, hasta), pred_monto(minimo))
        self.estados = ejecutar_pipeline(self.datos, construir_pipeline(pred))
        self._refrescar()

    def _limpiar(self):
        for var, valor in ((self.v_cat, "Todas"), (self.v_vend, "Todos"),
                           (self.v_desde, ""), (self.v_hasta, ""), (self.v_monto, "")):
            var.set(valor)
        self.cb_cat["values"] = ("Todas", *sorted({v.categoria for v in self.datos}))
        self.cb_vend["values"] = ("Todos", *sorted({v.vendedor for v in self.datos}))
        self.aplicar()

    def regenerar(self):
        self.datos = generar_ventas(400, random.randrange(10_000))
        self._limpiar()

    def cargar_csv(self):
        ruta = filedialog.askopenfilename(title="Cargar ventas", filetypes=[("CSV", "*.csv")])
        if not ruta:
            return
        try:
            datos = tuple(leer_filas(ruta))
        except (OSError, KeyError, ValueError) as err:
            messagebox.showerror("CSV inválido",
                                 "Columnas requeridas: producto, categoria, precio, cantidad, "
                                 f"fecha (AAAA-MM-DD), vendedor.\n\nDetalle: {err!r}")
            return
        if not datos:
            messagebox.showwarning("CSV vacío", "El archivo no contiene ventas.")
            return
        self.datos = datos
        self._limpiar()

    def exportar_csv(self):
        ruta = filedialog.asksaveasfilename(title="Exportar resultado", defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")])
        if ruta:
            escribir_csv(ruta, self.estados[2])
            messagebox.showinfo("Listo", f"Se exportaron {len(self.estados[2])} ventas.")

    # ── render ──────────────────────────────────────────────────────────
    def _refrescar(self):
        datos, filtrados, transformados, res = self.estados
        self.kpi["total"].config(text=dinero(res["total"]))
        self.kpi["unidades"].config(text=f"{res['unidades']:,}")
        self.kpi["ticket"].config(text=dinero(res["ticket"]))
        nombre, monto = res["top_producto"]
        self.kpi["top"].config(text=f"{nombre}\n{dinero_corto(monto)}")
        self.tree.delete(*self.tree.get_children())
        for v in sorted(transformados, key=lambda v: v.fecha, reverse=True)[:500]:
            self.tree.insert("", "end", values=(v.fecha.isoformat(), v.producto, v.categoria,
                                                dinero(v.precio), v.cantidad, dinero(v.importe), v.vendedor))
        self.barra.config(text=f"  Registros: {len(datos)} → {len(filtrados)} tras filtrar  ·  "
                               f"Tabla muestra hasta 500 filas")
        self._dibujar_graficas()
        self._dibujar_pipeline()

    def _dibujar_graficas(self):
        if not self.estados:
            return
        res = self.estados[-1]
        for clave, (cv, titulo, color, por_valor) in self.graficas.items():
            dibujar_barras(cv, res[clave], titulo, color, por_valor)

    def _dibujar_pipeline(self):
        cv = self.cv_pipe
        cv.delete("all")
        w = cv.winfo_width()
        if not self.estados or w < 300:
            return
        datos, filtrados, transformados, res = self.estados
        nodos = (("DATOS", f"{len(datos)} reg.", "generar / leer CSV", CYAN),
                 ("FILTRAR", f"{len(filtrados)} reg.", "filter + predicados", PINK),
                 ("TRANSFORMAR", f"{len(transformados)} reg.", "map: precio × cantidad", GOLD),
                 ("AGREGAR", f"{len(res['por_producto'])} prod.", "reduce: totales y grupos", LIME),
                 ("RESULTADOS", dinero_corto(res["total"]), "KPIs y gráficas", CYAN))
        n, gap, margen = len(nodos), 34, 14
        ancho = (w - 2 * margen - gap * (n - 1)) / n
        for i, (titulo, dato, nota, color) in enumerate(nodos):
            x = margen + i * (ancho + gap)
            cv.create_rectangle(x, 25, x + ancho, 150, fill=PANEL2, outline=color, width=2)
            cv.create_text(x + ancho / 2, 50, text=titulo, fill=color, font=(FUENTE, 10, "bold"))
            cv.create_text(x + ancho / 2, 88, text=dato, fill=TXT, font=(FUENTE, 12, "bold"))
            cv.create_text(x + ancho / 2, 123, text=nota, fill=MUTED, font=(FUENTE, 8),
                           width=ancho - 10, justify="center")
            if i < n - 1:
                cv.create_line(x + ancho + 4, 88, x + ancho + gap - 4, 88, fill=TXT, width=2, arrow="last")


if __name__ == "__main__":
    App().mainloop()
