# 🎮 GameZone — Analizador y sistema de ventas con Python funcional

Proyecto integrador de **Programación Lógica y Funcional (Unidad 2 · Python funcional)**.

Aplicación de escritorio con interfaz gráfica para una tienda de videojuegos y artículos afines (consolas, videojuegos, accesorios y coleccionables). Incluye dos programas:

1. **Analizador de ventas** (`gamezone.py`): procesa datos de ventas con un *pipeline* funcional y los muestra en un dashboard.
2. **Sistema de punto de venta e inventario** (`gamezone_sistema.py`): ventas, devoluciones, preventas, almacén y personal, con reportes que reutilizan el mismo pipeline.

```
datos → filtrar → transformar → agregar → resultados
```


## 📁 Contenido

| Archivo | Descripción |
|---|---|
| `gamezone.py` | Analizador funcional de datos de ventas |
| `gamezone_sistema.py` | Sistema de punto de venta e inventario (necesita `gamezone.py`) |
| `ventas_sucursal_centro.csv` | Datos de ejemplo: consolas, juegos, accesorios y coleccionables |
| `ventas_tienda_pc_gamer.csv` | Datos de ejemplo: PC gamer, periféricos, streaming y tarjetas digitales |

## ⚙️ Requisitos

- **Python 3.8 o superior**
- **tkinter** (incluido con Python en Windows y macOS; en Linux: `sudo apt install python3-tk`)
- No requiere instalar librerías externas.

## ▶️ Cómo ejecutarlo

```bash
python gamezone.py            # analizador de ventas
python gamezone_sistema.py    # sistema de punto de venta e inventario
```

> `gamezone_sistema.py` importa funciones de `gamezone.py`, así que ambos archivos deben estar **en la misma carpeta**.

## 📊 1. Analizador de ventas (`gamezone.py`)

- Genera 400 ventas de ejemplo o carga un CSV propio con **Cargar CSV…**
- **Filtros:** categoría, vendedor, rango de fechas y monto mínimo.
- **Dashboard:** ingresos, unidades, ticket promedio, producto más vendido y gráficas por categoría, vendedor, mes y producto.
- **Pestaña Pipeline:** muestra cuántos registros pasan por cada etapa.
- **Exportar resultado** a CSV.

**Formato del CSV** (la primera fila debe ser el encabezado):

```csv
producto,categoria,precio,cantidad,fecha,vendedor
Control DualSense,Accesorios,1699,2,2026-09-15,Ana
```

La fecha va en formato `AAAA-MM-DD`.

## 🛒 2. Sistema de tienda (`gamezone_sistema.py`)

| Módulo | Qué permite |
|---|---|
| **Ventas** | Buscar productos, armar el carrito y cobrar con **pago y cambio**. Descuenta el stock y genera un ticket con folio. |
| **Devoluciones** | Devolver piezas de un ticket (total o parcial), con o sin reingreso al almacén. Calcula el reembolso. |
| **Preventas** | Crear con anticipo, **cancelar** (reembolsa el anticipo) o **entregar** (cobra el saldo con cambio y descuenta del almacén). Respeta el precio pactado. |
| **Almacén** | Agregar y eliminar productos, **editar precios**, entradas y salidas de mercancía con motivo, alertas de stock bajo y kardex de movimientos. |
| **Personal** | Agregar y eliminar empleados, con sus tickets y ventas netas. |
| **Reportes** | Pipeline funcional aplicado a las ventas reales; exporta a CSV compatible con el analizador. |

Detalles útiles:

- Los datos se guardan automáticamente en `gamezone_datos.json` (se crea solo la primera vez, con datos de ejemplo).
- Para empezar de cero, usa **Restablecer datos de ejemplo** en la pestaña Reportes o borra ese archivo.
- No se puede eliminar al último empleado ni un producto con preventas activas.
- Los tickets y preventas ya registrados conservan el precio con el que se hicieron, aunque cambies el precio después.

## 🧠 Conceptos funcionales aplicados

| Concepto | Dónde se usa |
|---|---|
| **Funciones puras** | Predicados `pred_*`, `calcular_importe`, etapas del pipeline y todas las operaciones del sistema (`registrar_venta`, `devolver`, `crear_preventa`, …) |
| **Inmutabilidad** | `namedtuple` para todos los registros; los cambios se hacen con `_replace()` y devuelven copias nuevas |
| **`filter`** | `etapa_filtrar`, con predicados combinados mediante `todos()` |
| **`map`** | `etapa_transformar`: `importe = precio × cantidad` |
| **`reduce`** | `sumar_por()` y `etapa_agregar`: totales y agrupaciones; también `consolidar()` del carrito |
| **Comprensiones y generadores** | Conjuntos por comprensión, expresiones generadoras en `sum(...)` y el generador `leer_filas()` con `yield` |
| **Composición** | `ejecutar_pipeline()` encadena las etapas con `itertools.accumulate` |
| **Núcleo funcional, bordes imperativos** | En el sistema, la lógica del negocio es pura: recibe un estado y devuelve uno nuevo (o lanza `ValueError` y el estado original queda intacto). La interfaz y el guardado en JSON quedan en los bordes. |

## 👤 Autor

Castañón Haro Jesús Isaac

## 👤 Profesor

Torres Rangel Jose Ángel
