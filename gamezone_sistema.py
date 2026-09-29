#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GAMEZONE · Sistema de punto de venta e inventario
Proyecto integrador – Programación Lógica y Funcional, Unidad 2 (Python funcional)

Módulos: Ventas · Devoluciones · Preventas · Almacén · Personal · Reportes

Diseño "núcleo funcional, bordes imperativos":
  • Núcleo: cada operación del negocio es una función PURA  (estado, datos) → nuevo estado.
    Nunca modifica el estado recibido; si algo no es válido lanza ValueError y el estado
    original queda intacto.
  • Bordes: la interfaz (tkinter) y el guardado en JSON.
  • Reportes: reutilizan el pipeline funcional de gamezone.py
    (datos → filtrar → transformar → agregar → resultados).

Requisitos: Python 3.8+ y el archivo gamezone.py en la MISMA carpeta.
Ejecutar:   python gamezone_sistema.py
Los datos se guardan solos en gamezone_datos.json (junto a este archivo).
"""
import json
import random
import tkinter as tk
from collections import namedtuple
from datetime import date, datetime
from functools import reduce
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

import gamezone as gz
from gamezone import BG, PANEL, PANEL2, CYAN, PINK, LIME, GOLD, TXT, MUTED, FUENTE, dinero, dinero_corto

# ═══════════════════════════════════════════════════════════════════════════
#  1. MODELO (todo inmutable)
# ═══════════════════════════════════════════════════════════════════════════
Producto = namedtuple("Producto", "sku nombre categoria precio stock minimo")
Empleado = namedtuple("Empleado", "id nombre puesto")
Linea = namedtuple("Linea", "sku nombre categoria precio cantidad devuelto")
Ticket = namedtuple("Ticket", "folio fecha vendedor lineas nota pago cambio", defaults=(0.0, 0.0))
Devolucion = namedtuple("Devolucion", "folio fecha folio_venta sku nombre cantidad monto motivo reingresa")
Preventa = namedtuple("Preventa", "id fecha cliente sku nombre categoria cantidad precio anticipo "
                                  "llegada vendedor situacion folio_venta")
Movimiento = namedtuple("Movimiento", "fecha sku nombre tipo cantidad motivo existencia")
Estado = namedtuple("Estado", "productos empleados tickets devoluciones preventas movimientos "
                              "sig_folio sig_preventa sig_empleado")

PUESTOS = ("Gerente", "Vendedor", "Cajera", "Almacenista")
RUTA = Path(__file__).with_name("gamezone_datos.json")


def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def primero(items, pred):
    return next(filter(pred, items), None)


def buscar_producto(estado, sku):
    return primero(estado.productos, lambda p: p.sku == sku)


def buscar_ticket(estado, folio):
    return primero(estado.tickets, lambda t: t.folio == folio)


def total_ticket(t):
    return sum(l.precio * l.cantidad for l in t.lineas)


def total_neto(t):
    """Total del ticket descontando lo devuelto."""
    return sum(l.precio * (l.cantidad - l.devuelto) for l in t.lineas)


def siguiente_sku(productos):
    numeros = [int(p.sku[3:]) for p in productos if p.sku.startswith("GZ-") and p.sku[3:].isdigit()]
    return f"GZ-{max(numeros, default=0) + 1:03d}"


def numero(texto, tipo, campo):
    try:
        return tipo(str(texto).strip().replace(",", ""))
    except ValueError:
        raise ValueError(f"«{campo}» debe ser un número válido.") from None


def _exigir(condicion, mensaje):
    if not condicion:
        raise ValueError(mensaje)


# ═══════════════════════════════════════════════════════════════════════════
#  2. NÚCLEO FUNCIONAL — operaciones puras: estado → nuevo estado
# ═══════════════════════════════════════════════════════════════════════════
# ── Almacén ────────────────────────────────────────────────────────────────
def _mover_stock(estado, sku, delta, tipo, motivo, fecha):
    """Único punto por donde cambia el inventario; deja huella en el kardex."""
    p = buscar_producto(estado, sku)
    _exigir(p is not None, f"El producto {sku} no existe.")
    nuevo = p.stock + delta
    _exigir(nuevo >= 0, f"Stock insuficiente de «{p.nombre}» (hay {p.stock}).")
    return estado._replace(
        productos=tuple(q._replace(stock=nuevo) if q.sku == sku else q for q in estado.productos),
        movimientos=estado.movimientos + (Movimiento(fecha, sku, p.nombre, tipo, delta, motivo, nuevo),),
    )


def alta_producto(estado, sku, nombre, categoria, precio, stock, minimo, fecha):
    sku, nombre, categoria = sku.strip().upper(), nombre.strip(), categoria.strip()
    _exigir(sku and nombre and categoria, "SKU, nombre y categoría son obligatorios.")
    _exigir(buscar_producto(estado, sku) is None, f"Ya existe un producto con SKU {sku}.")
    _exigir(precio > 0, "El precio debe ser mayor a 0.")
    _exigir(stock >= 0 and minimo >= 0, "Existencia y mínimo no pueden ser negativos.")
    nuevo = estado._replace(productos=estado.productos + (Producto(sku, nombre, categoria, float(precio), 0, minimo),))
    return _mover_stock(nuevo, sku, stock, "Entrada", "Alta de producto", fecha) if stock else nuevo


def baja_producto(estado, sku):
    _exigir(buscar_producto(estado, sku) is not None, "El producto no existe.")
    _exigir(not any(p.sku == sku and p.situacion == "Activa" for p in estado.preventas),
            "Hay preventas activas de este producto; cancélalas o entrégalas primero.")
    return estado._replace(productos=tuple(p for p in estado.productos if p.sku != sku))


def editar_precio(estado, sku, precio):
    """Cambia el precio de venta. Tickets y preventas ya registrados conservan el precio con el que se hicieron."""
    _exigir(buscar_producto(estado, sku) is not None, "El producto no existe.")
    _exigir(precio > 0, "El precio debe ser mayor a 0.")
    return estado._replace(productos=tuple(q._replace(precio=round(float(precio), 2)) if q.sku == sku else q
                                           for q in estado.productos))


def entrada_mercancia(estado, sku, cantidad, motivo, fecha):
    _exigir(cantidad > 0, "La cantidad debe ser mayor a 0.")
    return _mover_stock(estado, sku, cantidad, "Entrada", motivo.strip() or "Reabastecimiento", fecha)


def salida_mercancia(estado, sku, cantidad, motivo, fecha):
    _exigir(cantidad > 0, "La cantidad debe ser mayor a 0.")
    return _mover_stock(estado, sku, -cantidad, "Salida", motivo.strip() or "Salida de mercancía", fecha)


# ── Personal ───────────────────────────────────────────────────────────────
def alta_empleado(estado, nombre, puesto):
    nombre, puesto = nombre.strip(), puesto.strip() or "Vendedor"
    _exigir(nombre, "El nombre es obligatorio.")
    _exigir(all(e.nombre.lower() != nombre.lower() for e in estado.empleados),
            "Ya existe un empleado con ese nombre.")
    return estado._replace(empleados=estado.empleados + (Empleado(estado.sig_empleado, nombre, puesto),),
                           sig_empleado=estado.sig_empleado + 1)


def baja_empleado(estado, id_emp):
    _exigir(any(e.id == id_emp for e in estado.empleados), "El empleado no existe.")
    _exigir(len(estado.empleados) > 1, "Debe quedar al menos un empleado registrado.")
    return estado._replace(empleados=tuple(e for e in estado.empleados if e.id != id_emp))


# ── Ventas ─────────────────────────────────────────────────────────────────
def consolidar(carrito):
    """Junta renglones repetidos: ((sku, n), ...) → un solo renglón por sku."""
    return tuple(reduce(lambda acc, it: {**acc, it[0]: acc.get(it[0], 0) + it[1]}, carrito, {}).items())


def _vender_lineas(estado, vendedor, lineas, fecha, nota="", anticipo=0.0, pago=None):
    """pago = efectivo recibido (None = pago exacto). Se cobra el total menos el anticipo, si lo hay."""
    _exigir(vendedor, "Selecciona un vendedor.")
    _exigir(lineas, "El carrito está vacío.")
    por_cobrar = round(sum(l.precio * l.cantidad for l in lineas) - anticipo, 2)
    pago = por_cobrar if pago is None else round(pago, 2)
    _exigir(pago >= 0, "El pago no puede ser negativo.")
    _exigir(pago >= por_cobrar, f"Pago insuficiente: faltan {dinero(por_cobrar - pago)}.")
    folio = estado.sig_folio
    movido = reduce(lambda e, l: _mover_stock(e, l.sku, -l.cantidad, "Venta", f"Ticket #{folio}", fecha),
                    lineas, estado)
    ticket = Ticket(folio, fecha, vendedor, lineas, nota, pago, round(pago - por_cobrar, 2))
    return movido._replace(tickets=movido.tickets + (ticket,), sig_folio=folio + 1)


def registrar_venta(estado, vendedor, carrito, fecha, pago=None):
    def a_linea(item):
        sku, cantidad = item
        p = buscar_producto(estado, sku)
        _exigir(p is not None, f"El producto {sku} ya no existe.")
        _exigir(cantidad > 0, "Las cantidades deben ser mayores a 0.")
        return Linea(p.sku, p.nombre, p.categoria, p.precio, cantidad, 0)

    return _vender_lineas(estado, vendedor, tuple(map(a_linea, consolidar(carrito))), fecha, pago=pago)


# ── Devoluciones ───────────────────────────────────────────────────────────
def devolver(estado, folio, sku, cantidad, motivo, reingresa, fecha):
    t = buscar_ticket(estado, folio)
    _exigir(t is not None, f"No existe el ticket #{folio}.")
    linea = primero(t.lineas, lambda x: x.sku == sku)
    _exigir(linea is not None, "Ese producto no está en el ticket.")
    disponible = linea.cantidad - linea.devuelto
    _exigir(0 < cantidad <= disponible, f"Cantidad inválida: se pueden devolver de 1 a {disponible}.")
    lineas = tuple(x._replace(devuelto=x.devuelto + cantidad) if x.sku == sku else x for x in t.lineas)
    registro = Devolucion(len(estado.devoluciones) + 1, fecha, folio, sku, linea.nombre, cantidad,
                          round(cantidad * linea.precio, 2), motivo.strip() or "Sin motivo", reingresa)
    nuevo = estado._replace(
        tickets=tuple(t._replace(lineas=lineas) if x.folio == folio else x for x in estado.tickets),
        devoluciones=estado.devoluciones + (registro,),
    )
    if reingresa and buscar_producto(nuevo, sku) is not None:
        nuevo = _mover_stock(nuevo, sku, cantidad, "Devolución", f"Ticket #{folio}", fecha)
    return nuevo


# ── Preventas ──────────────────────────────────────────────────────────────
def crear_preventa(estado, cliente, sku, cantidad, anticipo, llegada, vendedor, fecha):
    p = buscar_producto(estado, sku)
    _exigir(cliente.strip(), "El nombre del cliente es obligatorio.")
    _exigir(p is not None, "Selecciona un producto.")
    _exigir(cantidad > 0, "La cantidad debe ser mayor a 0.")
    _exigir(vendedor, "Selecciona un vendedor.")
    total = p.precio * cantidad
    _exigir(0 <= anticipo <= total, f"El anticipo debe estar entre $0 y {dinero(total)}.")
    pre = Preventa(estado.sig_preventa, fecha, cliente.strip(), p.sku, p.nombre, p.categoria, cantidad,
                   p.precio, float(anticipo), llegada.strip() or "Por confirmar", vendedor, "Activa", 0)
    return estado._replace(preventas=estado.preventas + (pre,), sig_preventa=estado.sig_preventa + 1)


def _preventa_activa(estado, pid):
    pre = primero(estado.preventas, lambda x: x.id == pid)
    _exigir(pre is not None, "La preventa no existe.")
    _exigir(pre.situacion == "Activa", f"La preventa #{pid} ya está {pre.situacion.lower()}.")
    return pre


def _actualizar_preventa(estado, pid, **cambios):
    return estado._replace(preventas=tuple(x._replace(**cambios) if x.id == pid else x for x in estado.preventas))


def cancelar_preventa(estado, pid):
    """Cancela la preventa (el anticipo se reembolsa al cliente)."""
    _preventa_activa(estado, pid)
    return _actualizar_preventa(estado, pid, situacion="Cancelada")


def entregar_preventa(estado, pid, vendedor, fecha, pago=None):
    """Convierte la preventa en venta respetando el precio pactado; descuenta almacén."""
    pre = _preventa_activa(estado, pid)
    linea = Linea(pre.sku, pre.nombre, pre.categoria, pre.precio, pre.cantidad, 0)
    nota = f"Preventa #{pid} · anticipo {dinero(pre.anticipo)}"
    vendido = _vender_lineas(estado, vendedor, (linea,), fecha, nota, anticipo=pre.anticipo, pago=pago)
    return _actualizar_preventa(vendido, pid, situacion="Entregada", folio_venta=vendido.sig_folio - 1)


# ── Puente hacia el pipeline de reportes (gamezone.py) ─────────────────────
def aplanar(tickets):
    """Cada renglón vendido (neto de devoluciones) → registro `gz.Venta` para el pipeline."""
    return tuple(
        gz.Venta(l.nombre, l.categoria, l.precio, l.cantidad - l.devuelto,
                 date.fromisoformat(t.fecha[:10]), t.vendedor)
        for t in tickets for l in t.lineas if l.cantidad - l.devuelto > 0
    )


# ═══════════════════════════════════════════════════════════════════════════
#  3. DATOS INICIALES Y PERSISTENCIA (JSON)
# ═══════════════════════════════════════════════════════════════════════════
def estado_inicial(fecha):
    rng = random.Random(3)

    def producto(i, dato):
        nombre, categoria, precio, _pop = dato
        consola = categoria == "Consolas"
        return Producto(f"GZ-{i:03d}", nombre, categoria, float(precio),
                        rng.randint(1, 8) if consola else rng.randint(2, 30), 3 if consola else 6)

    productos = tuple(map(producto, range(1, len(gz.CATALOGO) + 1), gz.CATALOGO))
    por_nombre = {p.nombre: p for p in productos}

    def ticket(folio, v):
        p = por_nombre[v.producto]
        return Ticket(folio, f"{v.fecha.isoformat()} 12:00", v.vendedor,
                      (Linea(p.sku, p.nombre, p.categoria, p.precio, v.cantidad, 0),), "Historial de ejemplo")

    historial = sorted(gz.generar_ventas(150, semilla=11), key=lambda v: v.fecha)
    empleados = tuple(Empleado(i, n, pu) for i, (n, pu) in enumerate(zip(gz.VENDEDORES, PUESTOS), 1))
    return Estado(
        productos=productos,
        empleados=empleados,
        tickets=tuple(map(ticket, range(1, len(historial) + 1), historial)),
        devoluciones=(),
        preventas=(),
        movimientos=tuple(Movimiento(fecha, p.sku, p.nombre, "Entrada", p.stock, "Inventario inicial", p.stock)
                          for p in productos),
        sig_folio=len(historial) + 1,
        sig_preventa=1,
        sig_empleado=len(empleados) + 1,
    )


def guardar(estado, ruta=RUTA):
    ruta.write_text(json.dumps(estado._asdict(), ensure_ascii=False, indent=1), encoding="utf-8")


def cargar(ruta=RUTA):
    d = json.loads(ruta.read_text(encoding="utf-8"))
    return Estado(
        productos=tuple(Producto(*x) for x in d["productos"]),
        empleados=tuple(Empleado(*x) for x in d["empleados"]),
        tickets=tuple(Ticket(t[0], t[1], t[2], tuple(Linea(*l) for l in t[3]), *t[4:]) for t in d["tickets"]),
        devoluciones=tuple(Devolucion(*x) for x in d["devoluciones"]),
        preventas=tuple(Preventa(*x) for x in d["preventas"]),
        movimientos=tuple(Movimiento(*x) for x in d["movimientos"]),
        sig_folio=d["sig_folio"], sig_preventa=d["sig_preventa"], sig_empleado=d["sig_empleado"],
    )


# ═══════════════════════════════════════════════════════════════════════════
#  4. WIDGETS AUXILIARES (estilo arcade / neón, tomado de gamezone.py)
# ═══════════════════════════════════════════════════════════════════════════
def etiqueta(padre, texto, color=MUTED, negrita=False, tam=9):
    return tk.Label(padre, text=texto, bg=padre.cget("bg"), fg=color,
                    font=(FUENTE, tam, "bold" if negrita else "normal"))


def entrada(padre, var, ancho=18):
    return tk.Entry(padre, textvariable=var, bg=PANEL2, fg=TXT, insertbackground=CYAN,
                    relief="flat", font=(FUENTE, 10), width=ancho)


def combo(padre, var, valores=(), ancho=18, editable=False):
    return ttk.Combobox(padre, textvariable=var, values=list(valores), width=ancho,
                        state="normal" if editable else "readonly", font=(FUENTE, 10))


def spin(padre, var, hasta=99, ancho=5):
    return tk.Spinbox(padre, from_=1, to=hasta, textvariable=var, width=ancho, bg=PANEL2, fg=TXT,
                      buttonbackground=PANEL2, insertbackground=CYAN, relief="flat", font=(FUENTE, 10))


def boton(padre, texto, comando, color):
    return tk.Button(padre, text=texto, command=comando, bg=color, fg=BG, activebackground=TXT,
                     activeforeground=BG, relief="flat", bd=0, cursor="hand2", padx=12, pady=6,
                     font=(FUENTE, 10, "bold"))


def columna(padre, texto):
    """Contenedor con etiqueta arriba, empaquetado a la izquierda (para formularios en fila)."""
    f = tk.Frame(padre, bg=padre.cget("bg"))
    f.pack(side="left", padx=(0, 10))
    etiqueta(f, texto).pack(anchor="w")
    return f


def tarjeta(padre, col, titulo, color):
    c = tk.Frame(padre, bg=PANEL, highlightbackground=color, highlightthickness=2)
    c.grid(row=0, column=col, sticky="nsew", padx=5)
    padre.columnconfigure(col, weight=1, uniform="kpi")
    etiqueta(c, titulo, MUTED, True).pack(anchor="w", padx=10, pady=(8, 0))
    lbl = tk.Label(c, text="—", bg=PANEL, fg=color, font=(FUENTE, 15, "bold"), wraplength=200, justify="left")
    lbl.pack(anchor="w", padx=10, pady=(0, 8))
    return lbl


def crear_tabla(padre, columnas, height=10):
    """columnas: ((id, título, ancho, ancla), ...) → (marco, treeview)."""
    marco = tk.Frame(padre, bg=PANEL)
    tv = ttk.Treeview(marco, columns=[c[0] for c in columnas], show="headings", height=height, selectmode="browse")
    for cid, titulo, ancho, ancla in columnas:
        tv.heading(cid, text=titulo)
        tv.column(cid, width=ancho, anchor=ancla, stretch=True)
    sb = ttk.Scrollbar(marco, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    tv.pack(side="left", fill="both", expand=True)
    return marco, tv


def seleccion(tv):
    s = tv.selection()
    return s[0] if s else None


def limpiar(tv):
    tv.delete(*tv.get_children())


def dialogo(padre, titulo, campos):
    """campos: ((clave, etiqueta, valor, opciones|None), ...) → dict con lo capturado, o None si se cancela."""
    win = tk.Toplevel(padre)
    win.title(titulo)
    win.configure(bg=PANEL)
    win.transient(padre)
    win.resizable(False, False)
    variables, foco = {}, None
    for clave, texto, valor, opciones in campos:
        etiqueta(win, texto).pack(anchor="w", padx=16, pady=(10, 2))
        var = tk.StringVar(value=str(valor))
        variables[clave] = var
        w = combo(win, var, opciones, 34, editable=True) if opciones else entrada(win, var, 36)
        w.pack(padx=16, ipady=3)
        foco = foco or w
    resultado = {}

    def aceptar(_e=None):
        resultado.update({k: v.get() for k, v in variables.items()})
        win.destroy()

    fila = tk.Frame(win, bg=PANEL)
    fila.pack(fill="x", padx=16, pady=14)
    boton(fila, "Aceptar", aceptar, LIME).pack(side="left", expand=True, fill="x", padx=(0, 4))
    boton(fila, "Cancelar", win.destroy, MUTED).pack(side="left", expand=True, fill="x", padx=(4, 0))
    win.bind("<Return>", aceptar)
    win.bind("<Escape>", lambda e: win.destroy())
    foco.focus_set()
    win.wait_visibility()
    win.grab_set()
    padre.wait_window(win)
    return resultado or None


# ═══════════════════════════════════════════════════════════════════════════
#  5. APLICACIÓN
# ═══════════════════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GAMEZONE · Sistema de punto de venta e inventario")
        self.geometry("1260x800")
        self.minsize(1100, 700)
        self.configure(bg=BG)
        gz.App._estilos(self)                     # mismo tema visual que el analizador
        self.estado = self._cargar_o_crear()
        self.carrito = ()                          # ((sku, cantidad), ...)
        self.rep = ()                              # estados del pipeline de reportes
        self.total_carrito = 0.0
        self._encabezado()
        self.barra = tk.Label(self, bg=PANEL, fg=MUTED, anchor="w", font=(FUENTE, 9), padx=12, pady=4)
        self.barra.pack(side="bottom", fill="x")
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        tabs = (("  VENTAS  ", self._tab_ventas), ("  DEVOLUCIONES  ", self._tab_devoluciones),
                ("  PREVENTAS  ", self._tab_preventas), ("  ALMACÉN  ", self._tab_almacen),
                ("  PERSONAL  ", self._tab_personal), ("  REPORTES  ", self._tab_reportes))
        for texto, construir in tabs:
            marco = tk.Frame(nb, bg=BG)
            nb.add(marco, text=texto)
            construir(marco)
        self.refrescar()

    def _cargar_o_crear(self):
        try:
            return cargar()
        except (OSError, ValueError, KeyError, TypeError):
            estado = estado_inicial(ahora())
            try:
                guardar(estado)
            except OSError:
                pass
            return estado

    def _encabezado(self):
        f = tk.Frame(self, bg=BG)
        f.pack(fill="x", padx=16, pady=(12, 8))
        tk.Label(f, text="▶ GAMEZONE", bg=BG, fg=PINK, font=(FUENTE, 24, "bold")).pack(side="left")
        tk.Label(f, text="  Sistema de punto de venta e inventario", bg=BG, fg=CYAN,
                 font=(FUENTE, 11)).pack(side="left", pady=(10, 0))
        tk.Label(f, text="Consolas · Videojuegos · Accesorios · Coleccionables", bg=BG, fg=MUTED,
                 font=(FUENTE, 10)).pack(side="right", pady=(10, 0))
        tk.Frame(self, bg=PINK, height=2).pack(fill="x", padx=16, pady=(0, 8))

    # ── ejecutor central: aplica una operación pura, guarda y refresca ─────
    def ejecutar(self, operacion):
        try:
            nuevo = operacion(self.estado)
        except ValueError as err:
            messagebox.showwarning("No se pudo completar", str(err), parent=self)
            return False
        self.estado = nuevo
        try:
            guardar(nuevo)
        except OSError as err:
            messagebox.showwarning("Sin guardar", f"La operación se aplicó pero no se pudo guardar el archivo:\n{err}",
                                   parent=self)
        self.refrescar()
        return True

    def _aviso(self, texto):
        messagebox.showinfo("Selección requerida", texto, parent=self)

    # ══ Pestaña VENTAS ════════════════════════════════════════════════════
    def _tab_ventas(self, padre):
        izq = tk.Frame(padre, bg=BG)
        izq.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=10)
        der = tk.Frame(padre, bg=BG, width=430)
        der.pack(side="left", fill="y", padx=(8, 0), pady=10)
        der.pack_propagate(False)

        fila = tk.Frame(izq, bg=BG)
        fila.pack(fill="x")
        etiqueta(fila, "CATÁLOGO", LIME, True, 11).pack(side="left")
        self.v_busca = tk.StringVar()
        self.v_busca.trace_add("write", lambda *_: self._llenar_catalogo())
        entrada(fila, self.v_busca, 26).pack(side="right", ipady=3)
        etiqueta(fila, "Buscar:").pack(side="right", padx=6)
        marco, self.tv_cat = crear_tabla(izq, (("sku", "SKU", 80, "w"), ("nombre", "PRODUCTO", 230, "w"),
                                                ("cat", "CATEGORÍA", 110, "w"), ("precio", "PRECIO", 90, "e"),
                                                ("stock", "STOCK", 60, "e")), height=18)
        marco.pack(fill="both", expand=True, pady=8)
        self.tv_cat.tag_configure("bajo", foreground=GOLD)
        self.tv_cat.tag_configure("agotado", foreground=PINK)
        self.tv_cat.bind("<Double-1>", self.agregar_carrito)
        abajo = tk.Frame(izq, bg=BG)
        abajo.pack(fill="x")
        etiqueta(abajo, "Cantidad:").pack(side="left")
        self.v_cant = tk.StringVar(value="1")
        spin(abajo, self.v_cant).pack(side="left", padx=8, ipady=2)
        boton(abajo, "＋ Agregar al carrito", self.agregar_carrito, CYAN).pack(side="left")
        etiqueta(abajo, "  (doble clic también agrega 1 pieza)").pack(side="left")

        etiqueta(der, "CARRITO", PINK, True, 11).pack(anchor="w")
        marco, self.tv_carro = crear_tabla(der, (("nombre", "PRODUCTO", 170, "w"), ("cant", "CANT", 50, "e"),
                                                  ("precio", "PRECIO", 90, "e"), ("sub", "SUBTOTAL", 100, "e")),
                                           height=10)
        marco.pack(fill="both", expand=True, pady=8)
        fila = tk.Frame(der, bg=BG)
        fila.pack(fill="x")
        boton(fila, "Quitar", self.quitar_carrito, MUTED).pack(side="left")
        boton(fila, "Vaciar", self.vaciar_carrito, MUTED).pack(side="left", padx=6)
        etiqueta(der, "Vendedor").pack(anchor="w", pady=(12, 2))
        self.v_vend_venta = tk.StringVar()
        self.cb_vend_venta = combo(der, self.v_vend_venta, ancho=30)
        self.cb_vend_venta.pack(fill="x")
        etiqueta(der, "TOTAL").pack(anchor="w", pady=(10, 0))
        self.lbl_total = tk.Label(der, text="$0.00", bg=BG, fg=LIME, font=(FUENTE, 28, "bold"))
        self.lbl_total.pack(anchor="w")
        fila = tk.Frame(der, bg=BG)
        fila.pack(fill="x", pady=(6, 0))
        etiqueta(fila, "Paga con ($):").pack(side="left")
        self.v_pago = tk.StringVar()
        self.v_pago.trace_add("write", lambda *_: self._actualizar_cambio())
        e_pago = entrada(fila, self.v_pago, 12)
        e_pago.pack(side="left", padx=8, ipady=3)
        e_pago.bind("<Return>", lambda ev: self.cobrar())
        boton(fila, "Exacto", lambda: self.v_pago.set(f"{self.total_carrito:.2f}"), MUTED).pack(side="left")
        self.lbl_cambio = tk.Label(der, bg=BG, font=(FUENTE, 16, "bold"), anchor="w")
        self.lbl_cambio.pack(fill="x", pady=(4, 0))
        boton(der, "✔ COBRAR", self.cobrar, LIME).pack(fill="x", pady=8, ipady=6)

    def agregar_carrito(self, _e=None):
        sku = seleccion(self.tv_cat)
        if sku is None:
            return self._aviso("Selecciona un producto del catálogo.")
        try:
            n = numero(self.v_cant.get(), int, "Cantidad")
        except ValueError as err:
            return messagebox.showwarning("Cantidad inválida", str(err), parent=self)
        p = buscar_producto(self.estado, sku)
        en_carro = dict(self.carrito).get(sku, 0)
        if n <= 0 or en_carro + n > p.stock:
            return messagebox.showwarning("Stock insuficiente",
                                          f"Disponible: {p.stock} pza. (ya hay {en_carro} en el carrito).", parent=self)
        self.carrito = consolidar(self.carrito + ((sku, n),))
        self._llenar_carrito()

    def quitar_carrito(self):
        sku = seleccion(self.tv_carro)
        if sku is None:
            return self._aviso("Selecciona un renglón del carrito.")
        self.carrito = tuple(i for i in self.carrito if i[0] != sku)
        self._llenar_carrito()

    def vaciar_carrito(self):
        self.carrito = ()
        self._llenar_carrito()

    def cobrar(self):
        vendedor, texto_pago = self.v_vend_venta.get(), self.v_pago.get().strip()
        if self.ejecutar(lambda e: registrar_venta(
                e, vendedor, self.carrito, ahora(), numero(texto_pago, float, "Paga con") if texto_pago else None)):
            t = self.estado.tickets[-1]
            self.carrito = ()
            self._llenar_carrito()
            self.v_pago.set("")
            messagebox.showinfo("Venta registrada",
                                f"Ticket #{t.folio}\nTotal: {dinero(total_ticket(t))}\n"
                                f"Pagó con: {dinero(t.pago)}\nCAMBIO: {dinero(t.cambio)}", parent=self)

    def _actualizar_cambio(self):
        texto = self.v_pago.get().strip()
        if not texto:
            return self.lbl_cambio.config(text="Cambio: pago exacto", fg=MUTED)
        try:
            pago = numero(texto, float, "Paga con")
        except ValueError:
            return self.lbl_cambio.config(text="Escribe un monto válido", fg=MUTED)
        diferencia = round(pago - self.total_carrito, 2)
        if diferencia >= 0:
            self.lbl_cambio.config(text=f"CAMBIO: {dinero(diferencia)}", fg=CYAN)
        else:
            self.lbl_cambio.config(text=f"Faltan {dinero(-diferencia)}", fg=PINK)

    def _llenar_catalogo(self):
        filtro = self.v_busca.get().strip().lower()
        limpiar(self.tv_cat)
        for p in filter(lambda p: filtro in f"{p.sku} {p.nombre} {p.categoria}".lower(), self.estado.productos):
            etiquetas = ("agotado",) if p.stock == 0 else ("bajo",) if p.stock <= p.minimo else ()
            self.tv_cat.insert("", "end", iid=p.sku, tags=etiquetas,
                               values=(p.sku, p.nombre, p.categoria, dinero(p.precio), p.stock))

    def _llenar_carrito(self):
        productos = {p.sku: p for p in self.estado.productos}
        self.carrito = tuple(i for i in self.carrito if i[0] in productos)   # descarta productos eliminados
        limpiar(self.tv_carro)
        for sku, n in self.carrito:
            p = productos[sku]
            self.tv_carro.insert("", "end", iid=sku, values=(p.nombre, n, dinero(p.precio), dinero(p.precio * n)))
        self.total_carrito = sum(productos[s].precio * n for s, n in self.carrito)
        self.lbl_total.config(text=dinero(self.total_carrito))
        self._actualizar_cambio()

    # ══ Pestaña DEVOLUCIONES ══════════════════════════════════════════════
    def _tab_devoluciones(self, padre):
        abajo = tk.Frame(padre, bg=BG)
        abajo.pack(side="bottom", fill="x", pady=(0, 8))
        etiqueta(abajo, "HISTORIAL DE DEVOLUCIONES", GOLD, True, 11).pack(anchor="w")
        marco, self.tv_dev = crear_tabla(abajo, (("folio", "#", 40, "e"), ("fecha", "FECHA", 120, "w"),
                                                  ("ticket", "TICKET", 70, "e"), ("producto", "PRODUCTO", 230, "w"),
                                                  ("cant", "CANT", 50, "e"), ("monto", "REEMBOLSO", 100, "e"),
                                                  ("motivo", "MOTIVO", 220, "w"), ("reing", "REINGRESÓ", 90, "center")),
                                         height=6)
        marco.pack(fill="x", pady=4)

        arriba = tk.Frame(padre, bg=BG)
        arriba.pack(fill="both", expand=True, pady=(10, 6))
        izq = tk.Frame(arriba, bg=BG)
        izq.pack(side="left", fill="both", expand=True, padx=(0, 8))
        der = tk.Frame(arriba, bg=BG)
        der.pack(side="left", fill="both", expand=True, padx=(8, 0))

        fila = tk.Frame(izq, bg=BG)
        fila.pack(fill="x")
        etiqueta(fila, "VENTAS REGISTRADAS", LIME, True, 11).pack(side="left")
        self.v_folio = tk.StringVar()
        e = entrada(fila, self.v_folio, 8)
        e.pack(side="right", ipady=3)
        e.bind("<Return>", self.ir_a_folio)
        etiqueta(fila, "Ir al folio:").pack(side="right", padx=6)
        marco, self.tv_tickets = crear_tabla(izq, (("folio", "FOLIO", 60, "e"), ("fecha", "FECHA", 120, "w"),
                                                    ("vendedor", "VENDEDOR", 90, "w"), ("total", "TOTAL NETO", 100, "e"),
                                                    ("nota", "NOTA", 150, "w")), height=10)
        marco.pack(fill="both", expand=True, pady=8)
        self.tv_tickets.bind("<<TreeviewSelect>>", self._mostrar_lineas)

        etiqueta(der, "PRODUCTOS DEL TICKET", PINK, True, 11).pack(anchor="w")
        self.lbl_info = tk.Label(der, bg=BG, fg=TXT, font=(FUENTE, 10), justify="left", anchor="w", wraplength=520)
        self.lbl_info.pack(fill="x", pady=4)
        marco, self.tv_lineas = crear_tabla(der, (("nombre", "PRODUCTO", 200, "w"), ("precio", "PRECIO", 80, "e"),
                                                   ("comprado", "COMPRADO", 80, "e"), ("devuelto", "DEVUELTO", 80, "e"),
                                                   ("disp", "DISPONIBLE", 90, "e")), height=5)
        marco.pack(fill="both", expand=True, pady=4)
        fila = tk.Frame(der, bg=BG)
        fila.pack(fill="x", pady=6)
        self.v_cant_dev, self.v_motivo, self.v_reingresa = tk.StringVar(value="1"), tk.StringVar(), tk.BooleanVar(value=True)
        c = columna(fila, "Cantidad")
        spin(c, self.v_cant_dev).pack(ipady=3)
        c = columna(fila, "Motivo")
        entrada(c, self.v_motivo, 26).pack(ipady=3)
        tk.Checkbutton(fila, text="Reingresar al almacén", variable=self.v_reingresa, bg=BG, fg=TXT, selectcolor=PANEL2,
                       activebackground=BG, activeforeground=TXT, font=(FUENTE, 9)).pack(side="left", pady=(14, 0))
        boton(der, "↩ PROCESAR DEVOLUCIÓN", self.procesar_devolucion, GOLD).pack(fill="x", pady=4, ipady=4)

    def _folio_sel(self):
        return seleccion(self.tv_tickets)

    def ir_a_folio(self, _e=None):
        folio = self.v_folio.get().strip()
        if folio in self.tv_tickets.get_children():
            self.tv_tickets.selection_set(folio)
            self.tv_tickets.see(folio)
        else:
            messagebox.showinfo("Buscar ticket", f"No existe el ticket #{folio}.", parent=self)

    def _mostrar_lineas(self, _e=None):
        limpiar(self.tv_lineas)
        folio = self._folio_sel()
        t = buscar_ticket(self.estado, int(folio)) if folio else None
        if t is None:
            self.lbl_info.config(text="Selecciona un ticket de la lista para devolver productos.")
            return
        self.lbl_info.config(text=f"Ticket #{t.folio} · {t.fecha} · Vendedor: {t.vendedor}\n"
                                  f"{t.nota or 'Venta de mostrador'} · Total neto: {dinero(total_neto(t))}"
                                  + (f"\nPagó con {dinero(t.pago)} · Cambio {dinero(t.cambio)}" if t.pago else ""))
        for l in t.lineas:
            self.tv_lineas.insert("", "end", iid=l.sku, values=(l.nombre, dinero(l.precio), l.cantidad, l.devuelto,
                                                               l.cantidad - l.devuelto))

    def procesar_devolucion(self):
        folio, sku = self._folio_sel(), seleccion(self.tv_lineas)
        if folio is None or sku is None:
            return self._aviso("Selecciona un ticket y, en la tabla de la derecha, el producto a devolver.")
        if self.ejecutar(lambda e: devolver(e, int(folio), sku, numero(self.v_cant_dev.get(), int, "Cantidad"),
                                            self.v_motivo.get(), self.v_reingresa.get(), ahora())):
            d = self.estado.devoluciones[-1]
            self.v_motivo.set("")
            messagebox.showinfo("Devolución registrada", f"Reembolso al cliente: {dinero(d.monto)}", parent=self)

    def _llenar_tickets(self):
        sel = self._folio_sel()
        limpiar(self.tv_tickets)
        for t in reversed(self.estado.tickets):
            self.tv_tickets.insert("", "end", iid=str(t.folio),
                                   values=(t.folio, t.fecha, t.vendedor, dinero(total_neto(t)), t.nota))
        if sel is not None and self.tv_tickets.exists(sel):
            self.tv_tickets.selection_set(sel)
        self._mostrar_lineas()

    def _llenar_devoluciones(self):
        limpiar(self.tv_dev)
        for d in reversed(self.estado.devoluciones):
            self.tv_dev.insert("", "end", iid=str(d.folio),
                               values=(d.folio, d.fecha, d.folio_venta, d.nombre, d.cantidad, dinero(d.monto),
                                       d.motivo, "Sí" if d.reingresa else "No"))

    # ══ Pestaña PREVENTAS ═════════════════════════════════════════════════
    def _tab_preventas(self, padre):
        fila = tk.Frame(padre, bg=BG)
        fila.pack(fill="x", pady=(12, 6))
        self.v_pre_cliente, self.v_pre_prod, self.v_pre_cant = tk.StringVar(), tk.StringVar(), tk.StringVar(value="1")
        self.v_pre_anticipo, self.v_pre_llegada, self.v_pre_vend = tk.StringVar(value="0"), tk.StringVar(), tk.StringVar()
        c = columna(fila, "Cliente")
        entrada(c, self.v_pre_cliente, 20).pack(ipady=3)
        c = columna(fila, "Producto")
        self.cb_pre_prod = combo(c, self.v_pre_prod, ancho=34)
        self.cb_pre_prod.pack(ipady=2)
        c = columna(fila, "Cant.")
        spin(c, self.v_pre_cant).pack(ipady=3)
        c = columna(fila, "Anticipo ($)")
        entrada(c, self.v_pre_anticipo, 10).pack(ipady=3)
        c = columna(fila, "Llegada estimada")
        entrada(c, self.v_pre_llegada, 16).pack(ipady=3)
        c = columna(fila, "Vendedor")
        self.cb_pre_vend = combo(c, self.v_pre_vend, ancho=12)
        self.cb_pre_vend.pack(ipady=2)
        boton(fila, "＋ Crear preventa", self.crear_pre, LIME).pack(side="left", pady=(14, 0))

        marco, self.tv_pre = crear_tabla(padre, (("id", "#", 40, "e"), ("fecha", "FECHA", 115, "w"),
                                                  ("cliente", "CLIENTE", 130, "w"), ("producto", "PRODUCTO", 210, "w"),
                                                  ("cant", "CANT", 45, "e"), ("total", "TOTAL", 90, "e"),
                                                  ("anticipo", "ANTICIPO", 90, "e"), ("llegada", "LLEGADA", 120, "w"),
                                                  ("vendedor", "VENDEDOR", 90, "w"), ("situacion", "SITUACIÓN", 90, "w")),
                                         height=16)
        marco.pack(fill="both", expand=True, pady=8)
        self.tv_pre.tag_configure("Activa", foreground=LIME)
        self.tv_pre.tag_configure("Cancelada", foreground=MUTED)
        self.tv_pre.tag_configure("Entregada", foreground=CYAN)
        fila = tk.Frame(padre, bg=BG)
        fila.pack(fill="x", pady=(0, 8))
        boton(fila, "✔ Entregar (convertir en venta)", self.entregar_pre, CYAN).pack(side="left")
        boton(fila, "✖ Cancelar preventa", self.cancelar_pre, PINK).pack(side="left", padx=8)
        etiqueta(fila, "Al cancelar se reembolsa el anticipo · al entregar se cobra el saldo y se descuenta del almacén.") \
            .pack(side="left", padx=8)

    def crear_pre(self):
        sku = self.v_pre_prod.get().split(" · ")[0]
        if self.ejecutar(lambda e: crear_preventa(
                e, self.v_pre_cliente.get(), sku, numero(self.v_pre_cant.get(), int, "Cantidad"),
                numero(self.v_pre_anticipo.get() or "0", float, "Anticipo"), self.v_pre_llegada.get(),
                self.v_pre_vend.get(), ahora())):
            self.v_pre_cliente.set("")
            self.v_pre_anticipo.set("0")
            self.v_pre_llegada.set("")

    def cancelar_pre(self):
        pid = seleccion(self.tv_pre)
        if pid is None:
            return self._aviso("Selecciona una preventa de la lista.")
        pre = primero(self.estado.preventas, lambda x: x.id == int(pid))
        if messagebox.askyesno("Cancelar preventa", f"¿Cancelar la preventa #{pid} de {pre.cliente}?\n"
                                                    f"Reembolso del anticipo: {dinero(pre.anticipo)}", parent=self):
            self.ejecutar(lambda e: cancelar_preventa(e, int(pid)))

    def entregar_pre(self):
        pid = seleccion(self.tv_pre)
        if pid is None:
            return self._aviso("Selecciona una preventa de la lista.")
        pre = primero(self.estado.preventas, lambda x: x.id == int(pid))
        saldo = round(pre.precio * pre.cantidad - pre.anticipo, 2)
        d = dialogo(self, f"Entregar preventa #{pid}",
                    (("pago", f"Paga con ($) — saldo a cobrar: {dinero(saldo)}", f"{saldo:.2f}", None),))
        if d and self.ejecutar(lambda e: entregar_preventa(e, int(pid), self.v_pre_vend.get(), ahora(),
                                                           numero(d["pago"], float, "Paga con"))):
            t = self.estado.tickets[-1]
            messagebox.showinfo("Preventa entregada",
                                f"Ticket #{t.folio}\nSaldo cobrado: {dinero(saldo)}\n"
                                f"Pagó con: {dinero(t.pago)}\nCAMBIO: {dinero(t.cambio)}", parent=self)

    def _llenar_preventas(self):
        opciones = [f"{p.sku} · {p.nombre}" for p in self.estado.productos]
        self.cb_pre_prod["values"] = opciones
        if self.v_pre_prod.get() not in opciones:
            self.v_pre_prod.set(opciones[0] if opciones else "")
        limpiar(self.tv_pre)
        for p in reversed(self.estado.preventas):
            self.tv_pre.insert("", "end", iid=str(p.id), tags=(p.situacion,),
                               values=(p.id, p.fecha, p.cliente, p.nombre, p.cantidad, dinero(p.precio * p.cantidad),
                                       dinero(p.anticipo), p.llegada, p.vendedor, p.situacion))

    # ══ Pestaña ALMACÉN ═══════════════════════════════════════════════════
    def _tab_almacen(self, padre):
        fila = tk.Frame(padre, bg=BG)
        fila.pack(fill="x", pady=(12, 6))
        boton(fila, "＋ Nuevo producto", self.nuevo_producto, LIME).pack(side="left")
        boton(fila, "▲ Entrada de mercancía", self.entrada_stock, CYAN).pack(side="left", padx=8)
        boton(fila, "▼ Salida de mercancía", self.salida_stock, GOLD).pack(side="left")
        boton(fila, "$ Editar precio", self.editar_precio_producto, "#b48cff").pack(side="left", padx=8)
        boton(fila, "✖ Eliminar producto", self.eliminar_producto, PINK).pack(side="left")
        self.lbl_alerta = tk.Label(fila, bg=BG, font=(FUENTE, 10, "bold"))
        self.lbl_alerta.pack(side="right")
        marco, self.tv_alm = crear_tabla(padre, (("sku", "SKU", 80, "w"), ("nombre", "PRODUCTO", 250, "w"),
                                                  ("cat", "CATEGORÍA", 120, "w"), ("precio", "PRECIO", 90, "e"),
                                                  ("stock", "EXISTENCIA", 90, "center"), ("minimo", "MÍNIMO", 70, "center"),
                                                  ("estado", "ESTADO", 90, "center")), height=11)
        marco.pack(fill="both", expand=True, pady=6)
        self.tv_alm.tag_configure("bajo", foreground=GOLD)
        self.tv_alm.tag_configure("agotado", foreground=PINK)
        etiqueta(padre, "MOVIMIENTOS DE ALMACÉN (KARDEX)", CYAN, True, 11).pack(anchor="w", pady=(6, 0))
        marco, self.tv_kardex = crear_tabla(padre, (("fecha", "FECHA", 120, "w"), ("sku", "SKU", 80, "w"),
                                                     ("nombre", "PRODUCTO", 230, "w"), ("tipo", "TIPO", 90, "w"),
                                                     ("cant", "CANT", 60, "center"), ("exist", "EXISTENCIA", 90, "center"),
                                                     ("motivo", "MOTIVO", 240, "w")), height=8)
        marco.pack(fill="both", expand=True, pady=(4, 8))

    def nuevo_producto(self):
        categorias = sorted({p.categoria for p in self.estado.productos})
        d = dialogo(self, "Nuevo producto", (
            ("sku", "SKU", siguiente_sku(self.estado.productos), None),
            ("nombre", "Nombre del producto", "", None),
            ("categoria", "Categoría (elige o escribe una nueva)", categorias[0] if categorias else "", categorias),
            ("precio", "Precio de venta ($)", "", None),
            ("stock", "Existencia inicial", "0", None),
            ("minimo", "Stock mínimo (para alertas)", "5", None)))
        if d:
            self.ejecutar(lambda e: alta_producto(
                e, d["sku"], d["nombre"], d["categoria"], numero(d["precio"], float, "Precio"),
                numero(d["stock"], int, "Existencia"), numero(d["minimo"], int, "Stock mínimo"), ahora()))

    def _movimiento(self, titulo, motivos, operacion):
        sku = seleccion(self.tv_alm)
        if sku is None:
            return self._aviso("Selecciona un producto de la tabla de existencias.")
        p = buscar_producto(self.estado, sku)
        d = dialogo(self, f"{titulo} · {p.nombre}", (("cantidad", f"Cantidad (existencia actual: {p.stock})", "1", None),
                                                    ("motivo", "Motivo", motivos[0], motivos)))
        if d:
            self.ejecutar(lambda e: operacion(e, sku, numero(d["cantidad"], int, "Cantidad"), d["motivo"], ahora()))

    def entrada_stock(self):
        self._movimiento("Entrada de mercancía", ("Reabastecimiento", "Compra a proveedor", "Ajuste de inventario"),
                         entrada_mercancia)

    def salida_stock(self):
        self._movimiento("Salida de mercancía", ("Merma / daño", "Robo o extravío", "Devolución a proveedor",
                                                 "Ajuste de inventario"), salida_mercancia)

    def editar_precio_producto(self):
        sku = seleccion(self.tv_alm)
        if sku is None:
            return self._aviso("Selecciona un producto de la tabla de existencias.")
        p = buscar_producto(self.estado, sku)
        d = dialogo(self, f"Editar precio · {p.nombre}",
                    (("precio", f"Nuevo precio ($) — actual: {dinero(p.precio)}", f"{p.precio:.2f}", None),))
        if d:
            self.ejecutar(lambda e: editar_precio(e, sku, numero(d["precio"], float, "Precio")))

    def eliminar_producto(self):
        sku = seleccion(self.tv_alm)
        if sku is None:
            return self._aviso("Selecciona un producto de la tabla de existencias.")
        p = buscar_producto(self.estado, sku)
        if messagebox.askyesno("Eliminar producto", f"¿Eliminar «{p.nombre}» del catálogo?\n"
                                                    "Las ventas ya registradas se conservan.", parent=self):
            self.ejecutar(lambda e: baja_producto(e, sku))

    def _llenar_almacen(self):
        sel = seleccion(self.tv_alm)
        limpiar(self.tv_alm)
        for p in self.estado.productos:
            estado, tag = ("AGOTADO", "agotado") if p.stock == 0 else ("BAJO", "bajo") if p.stock <= p.minimo else ("OK", "")
            self.tv_alm.insert("", "end", iid=p.sku, tags=(tag,),
                               values=(p.sku, p.nombre, p.categoria, dinero(p.precio), p.stock, p.minimo, estado))
        if sel is not None and self.tv_alm.exists(sel):
            self.tv_alm.selection_set(sel)
        bajos = sum(1 for p in self.estado.productos if p.stock <= p.minimo)
        self.lbl_alerta.config(text=f"⚠ {bajos} producto(s) con stock bajo" if bajos else "✔ Inventario sin alertas",
                               fg=GOLD if bajos else LIME)
        limpiar(self.tv_kardex)
        for i, m in enumerate(reversed(self.estado.movimientos[-200:])):
            self.tv_kardex.insert("", "end", iid=str(i),
                                  values=(m.fecha, m.sku, m.nombre, m.tipo, f"{m.cantidad:+d}", m.existencia, m.motivo))

    # ══ Pestaña PERSONAL ══════════════════════════════════════════════════
    def _tab_personal(self, padre):
        fila = tk.Frame(padre, bg=BG)
        fila.pack(fill="x", pady=(12, 6))
        self.v_emp_nombre, self.v_emp_puesto = tk.StringVar(), tk.StringVar(value="Vendedor")
        c = columna(fila, "Nombre completo")
        entrada(c, self.v_emp_nombre, 28).pack(ipady=3)
        c = columna(fila, "Puesto (elige o escribe)")
        combo(c, self.v_emp_puesto, PUESTOS, 18, editable=True).pack(ipady=2)
        boton(fila, "＋ Agregar empleado", self.agregar_empleado, LIME).pack(side="left", pady=(14, 0))
        boton(fila, "✖ Eliminar seleccionado", self.eliminar_empleado, PINK).pack(side="right", pady=(14, 0))
        marco, self.tv_emp = crear_tabla(padre, (("id", "ID", 50, "e"), ("nombre", "NOMBRE", 240, "w"),
                                                  ("puesto", "PUESTO", 160, "w"), ("tickets", "TICKETS", 80, "e"),
                                                  ("vendido", "VENDIDO (NETO)", 140, "e")), height=16)
        marco.pack(fill="both", expand=True, pady=8)

    def agregar_empleado(self):
        if self.ejecutar(lambda e: alta_empleado(e, self.v_emp_nombre.get(), self.v_emp_puesto.get())):
            self.v_emp_nombre.set("")

    def eliminar_empleado(self):
        eid = seleccion(self.tv_emp)
        if eid is None:
            return self._aviso("Selecciona un empleado de la lista.")
        emp = primero(self.estado.empleados, lambda x: x.id == int(eid))
        if messagebox.askyesno("Eliminar empleado", f"¿Eliminar a {emp.nombre} ({emp.puesto})?\n"
                                                    "Sus ventas anteriores se conservan en el historial.", parent=self):
            self.ejecutar(lambda e: baja_empleado(e, int(eid)))

    def _llenar_personal(self):
        tickets = self.estado.tickets
        vendido = gz.sumar_por(lambda t: t.vendedor, total_neto)(tickets)          # reduce reutilizado
        cuenta = gz.sumar_por(lambda t: t.vendedor, lambda t: 1)(tickets)
        limpiar(self.tv_emp)
        for e in self.estado.empleados:
            self.tv_emp.insert("", "end", iid=str(e.id),
                               values=(e.id, e.nombre, e.puesto, cuenta.get(e.nombre, 0), dinero(vendido.get(e.nombre, 0))))
        nombres = [e.nombre for e in self.estado.empleados]
        for cb, var in ((self.cb_vend_venta, self.v_vend_venta), (self.cb_pre_vend, self.v_pre_vend)):
            cb["values"] = nombres
            if var.get() not in nombres:
                var.set(nombres[0] if nombres else "")

    # ══ Pestaña REPORTES (pipeline funcional de gamezone.py) ══════════════
    def _tab_reportes(self, padre):
        fila = tk.Frame(padre, bg=BG)
        fila.pack(fill="x", pady=(10, 4))
        self.v_rcat, self.v_rvend = tk.StringVar(value="Todas"), tk.StringVar(value="Todos")
        self.v_rdesde, self.v_rhasta = tk.StringVar(), tk.StringVar()
        c = columna(fila, "Categoría")
        self.cb_rcat = combo(c, self.v_rcat, ancho=16)
        self.cb_rcat.pack(ipady=2)
        c = columna(fila, "Vendedor")
        self.cb_rvend = combo(c, self.v_rvend, ancho=12)
        self.cb_rvend.pack(ipady=2)
        for cb in (self.cb_rcat, self.cb_rvend):
            cb.bind("<<ComboboxSelected>>", lambda e: self._refrescar_reporte(True))
        c = columna(fila, "Desde (AAAA-MM-DD)")
        entrada(c, self.v_rdesde, 14).pack(ipady=3)
        c = columna(fila, "Hasta (AAAA-MM-DD)")
        entrada(c, self.v_rhasta, 14).pack(ipady=3)
        boton(fila, "▶ Aplicar", lambda: self._refrescar_reporte(True), LIME).pack(side="left", pady=(14, 0))
        boton(fila, "Exportar CSV…", self.exportar_reporte, GOLD).pack(side="left", padx=8, pady=(14, 0))
        boton(fila, "Restablecer datos de ejemplo", self.restablecer, PINK).pack(side="right", pady=(14, 0))

        kpis = tk.Frame(padre, bg=BG)
        kpis.pack(fill="x", pady=(6, 4))
        self.kpi = {"total": tarjeta(kpis, 0, "INGRESOS NETOS", LIME), "unidades": tarjeta(kpis, 1, "UNIDADES NETAS", CYAN),
                    "top": tarjeta(kpis, 2, "MÁS VENDIDO ($)", PINK), "dev": tarjeta(kpis, 3, "DEVUELTO (HISTÓRICO)", GOLD)}
        rejilla = tk.Frame(padre, bg=BG)
        rejilla.pack(fill="both", expand=True)
        self.graficas = {}
        config = (("por_categoria", "Ingresos por categoría", PINK, True), ("por_vendedor", "Ingresos por vendedor", CYAN, True),
                  ("por_mes", "Ingresos por mes", LIME, False), ("por_producto", "Top productos", GOLD, True))
        for i, (clave, titulo, color, por_valor) in enumerate(config):
            cv = tk.Canvas(rejilla, bg=PANEL, highlightthickness=0, height=170)
            cv.grid(row=i // 2, column=i % 2, sticky="nsew", padx=5, pady=5)
            cv.bind("<Configure>", lambda e: self._dibujar_reporte())
            self.graficas[clave] = (cv, titulo, color, por_valor)
        for idx in range(2):
            rejilla.columnconfigure(idx, weight=1, uniform="g")
            rejilla.rowconfigure(idx, weight=1, uniform="g")

    def _refrescar_reporte(self, avisar=False):
        datos = aplanar(self.estado.tickets)
        for cb, var, base, campo in ((self.cb_rcat, self.v_rcat, "Todas", "categoria"),
                                     (self.cb_rvend, self.v_rvend, "Todos", "vendedor")):
            valores = (base, *sorted({getattr(v, campo) for v in datos}))
            cb["values"] = valores
            if var.get() not in valores:
                var.set(base)
        try:
            desde, hasta = gz.parse_fecha(self.v_rdesde.get()), gz.parse_fecha(self.v_rhasta.get())
        except ValueError:
            if avisar:
                return messagebox.showerror("Fecha inválida", "Usa el formato AAAA-MM-DD.", parent=self)
            desde = hasta = None
        pred = gz.todos(gz.pred_categoria(self.v_rcat.get()), gz.pred_vendedor(self.v_rvend.get()),
                        gz.pred_fechas(desde, hasta), gz.pred_monto(0))
        self.rep = gz.ejecutar_pipeline(datos, gz.construir_pipeline(pred))    # datos→filtrar→transformar→agregar
        res = self.rep[-1]
        nombre, monto = res["top_producto"]
        self.kpi["total"].config(text=dinero(res["total"]))
        self.kpi["unidades"].config(text=f"{res['unidades']:,}")
        self.kpi["top"].config(text=f"{nombre}\n{dinero_corto(monto)}")
        self.kpi["dev"].config(text=dinero(sum(d.monto for d in self.estado.devoluciones)))
        self._dibujar_reporte()

    def _dibujar_reporte(self):
        if not self.rep:
            return
        res = self.rep[-1]
        for clave, (cv, titulo, color, por_valor) in self.graficas.items():
            gz.dibujar_barras(cv, res[clave], titulo, color, por_valor)

    def exportar_reporte(self):
        if not self.rep:
            return
        ruta = filedialog.asksaveasfilename(title="Exportar ventas", defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")])
        if ruta:
            gz.escribir_csv(ruta, self.rep[2])
            messagebox.showinfo("Listo", f"Se exportaron {len(self.rep[2])} renglones.\n"
                                         "Puedes abrirlos en gamezone.py con «Cargar CSV».", parent=self)

    def restablecer(self):
        if messagebox.askyesno("Restablecer datos", "Se borrarán TODOS los datos actuales (ventas, inventario, "
                                                    "preventas y personal) y se cargarán los de ejemplo.\n¿Continuar?",
                               parent=self):
            self.estado, self.carrito = estado_inicial(ahora()), ()
            try:
                guardar(self.estado)
            except OSError:
                pass
            self.refrescar()

    # ── refresco general ────────────────────────────────────────────────
    def refrescar(self):
        self._llenar_personal()            # primero: actualiza las listas de vendedores
        self._llenar_catalogo()
        self._llenar_carrito()
        self._llenar_tickets()
        self._llenar_devoluciones()
        self._llenar_preventas()
        self._llenar_almacen()
        self._refrescar_reporte()
        e = self.estado
        activas = sum(1 for p in e.preventas if p.situacion == "Activa")
        bajos = sum(1 for p in e.productos if p.stock <= p.minimo)
        self.barra.config(text=f"  Productos: {len(e.productos)}  ·  Empleados: {len(e.empleados)}  ·  "
                               f"Tickets: {len(e.tickets)}  ·  Preventas activas: {activas}  ·  "
                               f"Stock bajo: {bajos}  ·  Datos en {RUTA.name}")


if __name__ == "__main__":
    App().mainloop()
