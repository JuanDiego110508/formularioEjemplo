import datetime
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

import flet as ft
import pyodbc

import conexionform


# ============================================================
# FORMULARIO 4 - 22F-010
# Control consumo de agua y soda caustica lavador de gases caldera
# ============================================================

TABLA_REGISTRO = "dbo.Registro_Control_Agua_Soda_22F010"
CODIGO_FORMULARIO = "22F-010"
TITULO_FORMULARIO = "CONTROL CONSUMO DE AGUA Y SODA CAUSTICA"
SUBTITULO_FORMULARIO = "Lavador de gases de caldera"

COLOR_PRIMARIO = "#1E3A8A"
COLOR_TITULO = "#0F172A"
COLOR_FONDO = "#F8FAFC"
COLOR_BORDE = "#E2E8F0"
COLOR_EXITO = "#15803D"
COLOR_ALERTA = "#D97706"
COLOR_ERROR = "#B91C1C"
COLOR_AGUA = "#0284C7"
COLOR_SODA = "#7C3AED"

PH_MIN = Decimal("9.1")
PH_MAX = Decimal("9.5")
MAX_OBSERVACIONES = 1000
MAX_NOMBRE = 100
DIAS_RETROACTIVOS = 4

# Ajustar solo si el catalogo real de equipos es diferente.
CALDERAS = ("Caldera 1", "Caldera 2", "Caldera 3")


@dataclass(frozen=True)
class LecturaRegistro:
    id_temporal: str
    fecha: str
    hora: str
    caldera: str
    medidor_agua: Decimal
    ph: Decimal
    consumo_soda: Decimal
    responsable: str
    usuario_registro: str
    observaciones: str = ""


# Alias conservado para no romper importaciones antiguas que usen este nombre.
LecturaTurno = LecturaRegistro


def resource_path(relative_path: str) -> str:
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def parsear_decimal(
    texto: str | None,
    nombre: str,
    *,
    minimo: Decimal = Decimal("0"),
    max_enteros: int = 10,
    max_decimales: int = 2,
) -> Decimal:
    valor_texto = (texto or "").strip().replace(",", ".")
    if not valor_texto:
        raise ValueError(f"El campo {nombre} es obligatorio.")
    try:
        valor = Decimal(valor_texto)
    except InvalidOperation as ex:
        raise ValueError(f"{nombre} debe ser un numero valido.") from ex
    if not valor.is_finite():
        raise ValueError(f"{nombre} debe ser un numero finito.")
    if valor < minimo:
        raise ValueError(f"{nombre} debe ser mayor o igual a {minimo}.")
    normalizado = valor.normalize()
    decimales = max(0, -normalizado.as_tuple().exponent)
    enteros = max(1, normalizado.adjusted() + 1) if valor != 0 else 1
    if decimales > max_decimales:
        raise ValueError(f"{nombre} admite maximo {max_decimales} decimales.")
    if enteros > max_enteros:
        raise ValueError(f"{nombre} admite maximo {max_enteros} digitos enteros.")
    return valor


def ph_fuera_de_control(ph: Decimal) -> bool:
    return not (PH_MIN <= ph <= PH_MAX)


def texto_desviacion_ph(ph: Decimal) -> str:
    if ph < PH_MIN:
        return f"Bajo por {PH_MIN - ph} unidades"
    if ph > PH_MAX:
        return f"Excedido por {ph - PH_MAX} unidades"
    return "Dentro del rango operativo"


def validar_lectura(
    fecha: str,
    hora: str,
    caldera: str,
    medidor_agua: str | None,
    ph: str | None,
    consumo_soda: str | None,
    responsable: str | None,
    usuario_registro: str,
    observaciones: str = "",
    id_temporal: str | None = None,
) -> LecturaRegistro:
    try:
        fecha_obj = datetime.date.fromisoformat(fecha)
        hora_obj = datetime.time.fromisoformat(hora)
    except ValueError as ex:
        raise ValueError("La fecha o la hora no tienen un formato valido.") from ex

    hoy = datetime.date.today()
    fecha_minima = hoy - datetime.timedelta(days=DIAS_RETROACTIVOS)
    if not fecha_minima <= fecha_obj <= hoy:
        raise ValueError(
            f"La fecha debe estar entre {fecha_minima.isoformat()} y {hoy.isoformat()}."
        )
    if caldera not in CALDERAS:
        raise ValueError("Selecciona una caldera valida.")

    responsable_limpio = (responsable or "").strip()
    usuario_limpio = (usuario_registro or "").strip()
    if not responsable_limpio:
        raise ValueError("El responsable es obligatorio.")
    if not usuario_limpio:
        raise ValueError("No se identifico el usuario que registra.")
    if len(responsable_limpio) > MAX_NOMBRE:
        raise ValueError(f"El responsable admite maximo {MAX_NOMBRE} caracteres.")
    if len(usuario_limpio) > MAX_NOMBRE:
        raise ValueError(f"El usuario admite maximo {MAX_NOMBRE} caracteres.")

    return LecturaRegistro(
        id_temporal=id_temporal or uuid4().hex,
        fecha=fecha_obj.isoformat(),
        hora=hora_obj.strftime("%H:%M:%S"),
        caldera=caldera,
        medidor_agua=parsear_decimal(medidor_agua, "Medidor de agua"),
        ph=parsear_decimal(ph, "pH", max_enteros=2),
        consumo_soda=parsear_decimal(consumo_soda, "Consumo de soda caustica"),
        responsable=responsable_limpio,
        usuario_registro=usuario_limpio,
        observaciones=(observaciones or "").strip(),
    )


def _decimal_sql(valor: Decimal) -> str:
    return format(valor, "f")


def obtener_ultimos_registros_bd(
    caldera: str, anio: int, mes: int
) -> list[dict[str, Any]]:
    query = f"""
        SELECT id_registro, fecha, hora, caldera, medidor_agua, ph,
               consumo_soda, responsable, usuario_registro, observaciones
        FROM {TABLA_REGISTRO}
        WHERE caldera = ? AND YEAR(fecha) = ? AND MONTH(fecha) = ?
        ORDER BY fecha DESC, hora DESC, id_registro DESC
    """
    conn = None
    cursor = None
    try:
        conn = conexionform.obtener_conexion_formulario()
        cursor = conn.cursor()
        cursor.execute(query, caldera, anio, mes)
        columnas = [columna[0] for columna in cursor.description]
        return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
    except pyodbc.Error as ex:
        raise RuntimeError("No se pudo consultar el historial del formulario 22F-010.") from ex
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def insertar_registros_bd(
    registros: list[LecturaRegistro], observaciones: str
) -> list[int]:
    if not registros:
        raise ValueError("No hay registros pendientes para enviar.")

    observaciones = (observaciones or "").strip()
    if len(observaciones) > MAX_OBSERVACIONES:
        raise ValueError(
            f"Las observaciones admiten maximo {MAX_OBSERVACIONES} caracteres."
        )

    # Sin turnos: se evita repetir exactamente la misma lectura por fecha, hora,
    # caldera y usuario. El responsable no se usa como sustituto artificial del turno.
    claves = [
        (r.fecha, r.hora, r.caldera, r.usuario_registro)
        for r in registros
    ]
    if len(claves) != len(set(claves)):
        raise ValueError("Hay registros pendientes duplicados para la misma fecha, hora y caldera.")

    conn = None
    cursor = None
    ids: list[int] = []
    try:
        conn = conexionform.obtener_conexion_formulario()
        cursor = conn.cursor()
        for registro in registros:
            cursor.execute(
                f"""
                SELECT id_registro
                FROM {TABLA_REGISTRO} WITH (UPDLOCK, HOLDLOCK)
                WHERE fecha = ?
                  AND hora = ?
                  AND caldera = ?
                  AND usuario_registro = ?
                """,
                registro.fecha,
                registro.hora,
                registro.caldera,
                registro.usuario_registro,
            )
            if cursor.fetchone() is not None:
                raise ValueError(
                    "Ya existe un registro en SQL Server para esa fecha, hora, "
                    f"caldera y usuario: {registro.fecha} {registro.hora}, {registro.caldera}."
                )

            cursor.execute(
                f"""
                INSERT INTO {TABLA_REGISTRO} (
                    fecha, hora, caldera, medidor_agua, ph,
                    consumo_soda, responsable, usuario_registro, observaciones
                )
                OUTPUT INSERTED.id_registro
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                registro.fecha,
                registro.hora,
                registro.caldera,
                _decimal_sql(registro.medidor_agua),
                _decimal_sql(registro.ph),
                _decimal_sql(registro.consumo_soda),
                registro.responsable,
                registro.usuario_registro,
                (registro.observaciones or observaciones) or None,
            )
            fila = cursor.fetchone()
            if fila is None:
                raise RuntimeError("SQL Server no devolvio el identificador insertado.")
            ids.append(int(fila[0]))

        conn.commit()
        return ids
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def abrir_ventana(
    page: ft.Page,
    usuario_logueado: str,
    nombre_completo: str,
    on_logout=None,
):
    page.controls.clear()
    page.title = f"Formulario 4 - {CODIGO_FORMULARIO}"
    page.bgcolor = COLOR_FONDO

    # Tema blanco para toda la superficie exterior e interior de los diálogos.
    if page.theme is None:
        page.theme = ft.Theme()
    page.theme.dialog_theme = ft.DialogTheme(
        bgcolor="white",
        shadow_color="#94A3B8",
        shape=ft.RoundedRectangleBorder(radius=14),
    )
    page.window.maximized = True
    page.window.resizable = True

    formulario_activo = True
    pagina_lista = False
    fecha_fijada: str | None = None
    hora_fijada: str | None = None
    id_registro_en_edicion: str | None = None
    registros_pendientes: list[LecturaRegistro] = []
    historicos: list[dict[str, Any]] = []

    def detener_formulario():
        nonlocal formulario_activo
        formulario_activo = False

    page.on_disconnect = lambda _: detener_formulario()

    def abrir_dialogo(dialogo):
        if hasattr(page, "show_dialog"):
            page.show_dialog(dialogo)
        elif hasattr(page, "open"):
            page.open(dialogo)
        else:
            page.dialog = dialogo
            dialogo.open = True
            page.update()

    def cerrar_dialogo(dialogo=None):
        if hasattr(page, "pop_dialog") and dialogo is not None:
            page.pop_dialog()
        elif hasattr(page, "close") and dialogo is not None:
            page.close(dialogo)
        elif getattr(page, "dialog", None) is not None:
            page.dialog.open = False
            page.update()

    def snackbar(texto: str, color: str):
        barra = ft.SnackBar(ft.Text(texto), bgcolor=color)
        if hasattr(page, "open"):
            page.open(barra)
        else:
            page.snack_bar = barra
            barra.open = True
            page.update()

    ahora = datetime.datetime.now()
    fecha_minima = ahora - datetime.timedelta(days=DIAS_RETROACTIVOS)

    txt_fecha = ft.TextField(
        value=ahora.strftime("%Y-%m-%d"), read_only=True, width=150, height=45,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=8, border_color="#CBD5E1", text_size=13,
        color="#475569",
        text_style=ft.TextStyle(color="#475569", weight=ft.FontWeight.W_500),
    )
    txt_hora = ft.TextField(
        value=ahora.strftime("%H:%M:%S"), read_only=True, width=130, height=45,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=8, border_color="#CBD5E1", text_size=13,
        color="#475569",
        text_style=ft.TextStyle(color="#475569", weight=ft.FontWeight.W_500),
    )

    def obtener_fecha() -> str:
        return fecha_fijada or datetime.datetime.now().strftime("%Y-%m-%d")

    def obtener_hora() -> str:
        return hora_fijada or datetime.datetime.now().strftime("%H:%M:%S")

    dd_caldera = ft.Dropdown(
        label="Caldera N°", width=220, value=CALDERAS[0],
        options=[ft.dropdown.Option(item) for item in CALDERAS],
        border_radius=8, border_color="#CBD5E1",
        color="#475569",
        label_style=ft.TextStyle(color="#64748B"),
    )
    txt_medidor = ft.TextField(
        label="Medidor de agua", suffix=ft.Text("m³", size=13, color="#64748B"),
        keyboard_type=ft.KeyboardType.NUMBER, border_radius=8,
        border_color="#CBD5E1", focused_border_color=COLOR_AGUA,
        color="#475569",
        label_style=ft.TextStyle(color="#64748B"),
        hint_style=ft.TextStyle(color="#64748B"),
    )
    txt_ph = ft.TextField(
        label="pH", hint_text="Rango operativo 9.1 - 9.5", width=180,
        keyboard_type=ft.KeyboardType.NUMBER, border_radius=8,
        border_color="#CBD5E1", focused_border_color=COLOR_ALERTA,
        color="#475569",
        label_style=ft.TextStyle(color="#64748B"),
        hint_style=ft.TextStyle(color="#64748B"),
    )
    txt_soda = ft.TextField(
        label="Consumo soda caustica", suffix=ft.Text("kg", size=13, color="#64748B"),
        keyboard_type=ft.KeyboardType.NUMBER, border_radius=8,
        border_color="#CBD5E1", focused_border_color=COLOR_SODA,
        color="#475569",
        label_style=ft.TextStyle(color="#64748B"),
        hint_style=ft.TextStyle(color="#64748B"),
    )
    responsable_automatico = (nombre_completo or usuario_logueado or "").strip()

    txt_observaciones = ft.TextField(
        label="Observaciones", multiline=True, min_lines=2, max_lines=4,
        max_length=MAX_OBSERVACIONES,
        hint_text="Novedades, desviaciones o acciones realizadas...",
        border_radius=8, border_color="#CBD5E1",
        focused_border_color=COLOR_PRIMARIO,
        color="#475569",
        label_style=ft.TextStyle(color="#64748B"),
        hint_style=ft.TextStyle(color="#64748B"),
    )
    texto_estado_observaciones = ft.Text("Sin observaciones", size=12, color="#475569")

    def actualizar_estado_observaciones():
        valor = (txt_observaciones.value or "").strip()
        texto_estado_observaciones.value = (
            f"Observación guardada · {len(valor)} caracteres" if valor else "Sin observaciones"
        )
        texto_estado_observaciones.color = COLOR_EXITO if valor else "#475569"

    def abrir_observaciones(_):
        anterior = txt_observaciones.value or ""
        def cancelar(_):
            txt_observaciones.value = anterior
            cerrar_dialogo(dialogo)
        def guardar(_):
            txt_observaciones.value = (txt_observaciones.value or "").strip()
            actualizar_estado_observaciones()
            cerrar_dialogo(dialogo)
            page.update()
        dialogo = ft.AlertDialog(
            modal=True, bgcolor="white",
            title=ft.Text("Observaciones", color=COLOR_PRIMARIO, weight=ft.FontWeight.BOLD),
            content=ft.Container(width=620, bgcolor="white", content=txt_observaciones),
            actions=[
                ft.OutlinedButton("Cancelar", on_click=cancelar),
                ft.ElevatedButton("Guardar observación", icon=ft.Icons.SAVE_OUTLINED,
                                  bgcolor=COLOR_PRIMARIO, color="white", on_click=guardar),
            ], actions_alignment=ft.MainAxisAlignment.END,
        )
        abrir_dialogo(dialogo)

    btn_observaciones = ft.OutlinedButton(
        "Observaciones", icon=ft.Icons.NOTES_ROUNDED, on_click=abrir_observaciones,
        style=ft.ButtonStyle(color=COLOR_PRIMARIO, side=ft.BorderSide(1, COLOR_PRIMARIO),
                             shape=ft.RoundedRectangleBorder(radius=9)),
    )

    txt_error = ft.Text("", visible=False, color=COLOR_ERROR, size=12,
                        weight=ft.FontWeight.BOLD)

    btn_actualizar_ahora = ft.TextButton(
        "Usar fecha y hora actuales", icon=ft.Icons.UPDATE_ROUNDED, visible=False
    )

    def on_date_change(_):
        nonlocal fecha_fijada
        if date_picker.value:
            fecha_fijada = date_picker.value.strftime("%Y-%m-%d")
            txt_fecha.value = fecha_fijada
            btn_actualizar_ahora.visible = True
            page.update()

    def on_time_change(_):
        nonlocal hora_fijada
        if time_picker.value:
            hora_fijada = time_picker.value.strftime("%H:%M:%S")
            txt_hora.value = hora_fijada
            btn_actualizar_ahora.visible = True
            page.update()

    date_picker = ft.DatePicker(
        value=ahora, first_date=fecha_minima, last_date=ahora,
        current_date=ahora, on_change=on_date_change,
    )
    time_picker = ft.TimePicker(value=ahora.time(), on_change=on_time_change)

    def poner_ahora(_):
        nonlocal fecha_fijada, hora_fijada
        fecha_fijada = None
        hora_fijada = None
        momento = datetime.datetime.now()
        txt_fecha.value = momento.strftime("%Y-%m-%d")
        txt_hora.value = momento.strftime("%H:%M:%S")
        date_picker.value = momento
        time_picker.value = momento.time()
        btn_actualizar_ahora.visible = False
        page.update()

    btn_actualizar_ahora.on_click = poner_ahora

    contenedor_filas = ft.Column(spacing=7)
    caja_vacia = ft.Container(
        padding=25, alignment=ft.Alignment.CENTER,
        content=ft.Row([
            ft.Icon(ft.Icons.INFO_OUTLINE_ROUNDED, color="#94A3B8"),
            ft.Text("No hay registros pendientes.", color="#64748B", size=13),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
    )

    btn_enviar = ft.ElevatedButton(
        "Enviar registros pendientes", icon=ft.Icons.SEND_ROUNDED,
        bgcolor=COLOR_PRIMARIO, color="white", disabled=True,
    )

    def quitar_pendiente(id_temporal: str):
        indice = next(
            (i for i, r in enumerate(registros_pendientes)
             if r.id_temporal == id_temporal),
            None,
        )
        if indice is None:
            return
        registros_pendientes.pop(indice)
        actualizar_tabla()
        snackbar("Registro pendiente eliminado.", COLOR_ERROR)

    def ver_registro(registro: LecturaRegistro):
        filas = [
            ("Fecha y hora", f"{registro.fecha} {registro.hora}"),
            ("Caldera", registro.caldera),
            ("Medidor de agua", f"{registro.medidor_agua} m3"),
            ("pH", str(registro.ph)),
            ("Soda caustica", f"{registro.consumo_soda} kg"),
            ("Usuario responsable", registro.usuario_registro),
            ("Observaciones", registro.observaciones or "Sin observaciones"),
        ]
        dialogo = ft.AlertDialog(
            modal=True, bgcolor="white",
            shape=ft.RoundedRectangleBorder(radius=14),
            title=ft.Text("Detalle del registro", color=COLOR_PRIMARIO,
                          weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=480,
                content=ft.Column([
                    ft.Container(
                        padding=10, bgcolor="#F8FAFC", border_radius=8,
                        content=ft.Row([
                            ft.Text(k, weight=ft.FontWeight.BOLD, color="#475569"),
                            ft.Text(v, color=COLOR_TITULO),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ) for k, v in filas
                ], spacing=6, tight=True),
            ),
            actions=[ft.ElevatedButton(
                "Cerrar", on_click=lambda _: cerrar_dialogo(dialogo),
                bgcolor=COLOR_PRIMARIO, color="white",
            )],
        )
        abrir_dialogo(dialogo)

    def editar_registro(registro: LecturaRegistro):
        nonlocal id_registro_en_edicion, fecha_fijada, hora_fijada
        id_registro_en_edicion = registro.id_temporal
        fecha_fijada = registro.fecha
        hora_fijada = None
        ahora_edicion = datetime.datetime.now()
        txt_fecha.value = registro.fecha
        txt_hora.value = ahora_edicion.strftime("%H:%M:%S")
        dd_caldera.value = registro.caldera
        txt_medidor.value = str(registro.medidor_agua)
        txt_ph.value = str(registro.ph)
        txt_soda.value = str(registro.consumo_soda)
        txt_observaciones.value = registro.observaciones
        actualizar_estado_observaciones()
        btn_agregar.text = "Actualizar registro pendiente"
        btn_agregar.icon = ft.Icons.SAVE_AS_OUTLINED
        btn_actualizar_ahora.visible = True
        page.update()

    def actualizar_tabla():
        contenedor_filas.controls.clear()
        for registro in sorted(
            registros_pendientes,
            key=lambda r: (r.fecha, r.hora, r.caldera),
        ):
            desviada = ph_fuera_de_control(registro.ph)
            contenedor_filas.controls.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                    bgcolor="white", border_radius=8,
                    border=ft.Border.all(1, COLOR_BORDE),
                    content=ft.Row([
                        ft.Container(ft.Text(f"{registro.fecha}\n{registro.hora}", size=11, color="#475569"), expand=2),
                        ft.Container(ft.Text(registro.caldera, weight=ft.FontWeight.BOLD, color="#475569"), expand=2),
                        ft.Container(ft.Text(str(registro.medidor_agua), color="#475569"), expand=1),
                        ft.Container(ft.Text(
                            str(registro.ph),
                            color=COLOR_ERROR if desviada else COLOR_EXITO,
                            weight=ft.FontWeight.BOLD,
                        ), expand=1),
                        ft.Container(ft.Text(f"{registro.consumo_soda} kg", color="#475569"), expand=1),
                        ft.Container(ft.Text(registro.usuario_registro, size=11, color="#475569"), expand=2),
                        ft.Container(ft.Row([
                            ft.IconButton(
                                ft.Icons.VISIBILITY_ROUNDED, tooltip="Ver",
                                icon_color=COLOR_AGUA,
                                on_click=lambda _, r=registro: ver_registro(r),
                            ),
                            ft.IconButton(
                                ft.Icons.EDIT_OUTLINED, tooltip="Editar", icon_color=COLOR_ALERTA,
                                on_click=lambda _, r=registro: editar_registro(r),
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE_ROUNDED, tooltip="Eliminar",
                                icon_color=COLOR_ERROR,
                                on_click=lambda _, rid=registro.id_temporal: quitar_pendiente(rid),
                            ),
                        ], spacing=1, alignment=ft.MainAxisAlignment.END), expand=2),
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                )
            )
        if not registros_pendientes:
            contenedor_filas.controls.append(caja_vacia)
        btn_enviar.disabled = not registros_pendientes
        if pagina_lista:
            contenedor_filas.update()
            btn_enviar.update()

    def agregar_registro_confirmado(registro: LecturaRegistro):
        nonlocal id_registro_en_edicion
        if id_registro_en_edicion is None:
            registros_pendientes.append(registro)
            mensaje = "Lectura agregada a la tabla de pendientes."
        else:
            indice = next((i for i, r in enumerate(registros_pendientes)
                           if r.id_temporal == id_registro_en_edicion), None)
            if indice is None:
                snackbar("El registro pendiente ya no está disponible.", COLOR_ERROR)
                return
            registros_pendientes[indice] = registro
            mensaje = "Registro pendiente actualizado correctamente."
        id_registro_en_edicion = None
        txt_medidor.value = txt_ph.value = txt_soda.value = ""
        txt_observaciones.value = ""
        actualizar_estado_observaciones()
        btn_agregar.text = "Agregar registro a la tabla"
        btn_agregar.icon = ft.Icons.ADD_ROUNDED
        txt_error.visible = False
        actualizar_tabla()
        page.update()
        snackbar(mensaje, COLOR_ALERTA)

    def registrar_lectura(_):
        try:
            registro = validar_lectura(
                obtener_fecha(),
                obtener_hora(),
                dd_caldera.value or "",
                txt_medidor.value,
                txt_ph.value,
                txt_soda.value,
                responsable_automatico,
                usuario_logueado,
                (txt_observaciones.value or "").strip(),
                id_registro_en_edicion,
            )
        except ValueError as ex:
            txt_error.value = str(ex)
            txt_error.visible = True
            page.update()
            return

        txt_error.visible = False
        if not ph_fuera_de_control(registro.ph):
            agregar_registro_confirmado(registro)
            return

        alerta = ft.AlertDialog(
            modal=True,
            title=ft.Text("pH fuera del rango operativo", color=COLOR_ERROR,
                          weight=ft.FontWeight.BOLD),
            content=ft.Container(
                bgcolor="white",
                width=450,
                content=ft.Column([
                    ft.Text(f"Valor registrado: {registro.ph}"),
                    ft.Text(f"Rango esperado: {PH_MIN} - {PH_MAX}"),
                    ft.Text(texto_desviacion_ph(registro.ph), color=COLOR_ERROR,
                            weight=ft.FontWeight.BOLD),
                    ft.Text("Puedes corregirlo o conservar la lectura como desviacion.",
                            color="#475569"),
                ], spacing=8, tight=True),
            ),
            actions=[
                ft.OutlinedButton("Editar", on_click=lambda _: cerrar_dialogo(alerta)),
                ft.ElevatedButton(
                    "Continuar y agregar", bgcolor=COLOR_ALERTA, color="white",
                    on_click=lambda _: (
                        cerrar_dialogo(alerta),
                        agregar_registro_confirmado(registro),
                    ),
                ),
            ],
        )
        abrir_dialogo(alerta)

    btn_agregar = ft.ElevatedButton(
        "Agregar registro a la tabla",
        icon=ft.Icons.ADD_ROUNDED,
        bgcolor=COLOR_PRIMARIO,
        color="white",
        on_click=registrar_lectura,
    )

    def recargar_historico(_=None):
        nonlocal historicos
        fecha_obj = datetime.date.fromisoformat(obtener_fecha())
        try:
            historicos = obtener_ultimos_registros_bd(
                dd_caldera.value or CALDERAS[0], fecha_obj.year, fecha_obj.month
            )
        except RuntimeError:
            logging.exception("Error cargando historial 22F-010")
            historicos = []
            snackbar("No se pudo cargar el historial. Verifica SQL Server.", COLOR_ERROR)

    dd_caldera.on_change = recargar_historico

    def confirmar_envio(_):
        if not registros_pendientes:
            return

        resumen = ft.Column([
            ft.Container(
                padding=9, bgcolor="#F8FAFC", border_radius=8,
                content=ft.Text(
                    f"{r.fecha} {r.hora} | {r.caldera} | "
                    f"Responsable: {r.responsable} | pH {r.ph} | "
                    f"Soda {r.consumo_soda} kg",
                    size=12,
                ),
            ) for r in sorted(
                registros_pendientes,
                key=lambda item: (item.fecha, item.hora, item.caldera),
            )
        ], spacing=6, scroll=ft.ScrollMode.AUTO)

        def enviar(_):
            boton_confirmar.disabled = True
            dialogo.update()
            try:
                ids = insertar_registros_bd(registros_pendientes.copy(), "")
            except ValueError as ex:
                cerrar_dialogo(dialogo)
                snackbar(str(ex), COLOR_ERROR)
            except pyodbc.Error:
                logging.exception("Error SQL Server enviando 22F-010")
                cerrar_dialogo(dialogo)
                snackbar("No fue posible guardar. Verifica la conexion y el esquema 22F-010.", COLOR_ERROR)
            except RuntimeError as ex:
                logging.exception("SQL Server no confirmo 22F-010")
                cerrar_dialogo(dialogo)
                snackbar(str(ex), COLOR_ERROR)
            else:
                cantidad = len(ids)
                registros_pendientes.clear()
                cerrar_dialogo(dialogo)
                actualizar_tabla()
                recargar_historico()
                snackbar(f"{cantidad} registro(s) guardado(s) correctamente.", COLOR_EXITO)

        boton_confirmar = ft.ElevatedButton(
            "Enviar a base de datos", icon=ft.Icons.CLOUD_UPLOAD_ROUNDED,
            bgcolor=COLOR_EXITO, color="white", on_click=enviar,
        )
        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar envio a SQL Server", color=COLOR_PRIMARIO,
                          weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=620,
                height=min(390, 120 + len(registros_pendientes) * 52),
                content=ft.Column([
                    ft.Text("Los siguientes registros se guardaran definitivamente:",
                            color="#475569"),
                    resumen,
                ], spacing=10),
            ),
            actions=[
                ft.OutlinedButton("Cancelar", on_click=lambda _: cerrar_dialogo(dialogo)),
                boton_confirmar,
            ],
        )
        abrir_dialogo(dialogo)

    btn_enviar.on_click = confirmar_envio

    def confirmar_salida(_):
        if on_logout is None:
            return
        mensaje = (
            "Los registros pendientes se perderan."
            if registros_pendientes
            else "Volveras al menu principal."
        )
        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color="#DC2626"),
                ft.Text("¿Seguro que deseas salir?", color="#DC2626",
                        weight=ft.FontWeight.BOLD),
            ]),
            content=ft.Container(width=450, content=ft.Text(mensaje, color="#334155")),
            actions=[
                ft.OutlinedButton("Cancelar", on_click=lambda _: cerrar_dialogo(dialogo)),
                ft.ElevatedButton(
                    "Si, continuar y salir", bgcolor="#DC2626", color="white",
                    on_click=lambda _: salir(dialogo),
                ),
            ],
        )
        abrir_dialogo(dialogo)

    def salir(dialogo):
        detener_formulario()
        cerrar_dialogo(dialogo)
        on_logout()

    txt_marquee = ft.Text(
        "", size=16, color="#F8FAFC", weight=ft.FontWeight.BOLD, no_wrap=True
    )
    txt_reloj = ft.Text(
        ahora.strftime("%H:%M:%S"), size=15, weight=ft.FontWeight.BOLD,
        color=COLOR_PRIMARIO,
    )

    def animar_marquee():
        texto = (
            f" {CODIGO_FORMULARIO} {TITULO_FORMULARIO} | "
            f"RESPONSABLE: {nombre_completo or usuario_logueado} | "
            "CRYSTAL S.A.S |     "
        ) * 10
        while formulario_activo:
            try:
                texto = texto[1:] + texto[0]
                txt_marquee.value = texto
                if pagina_lista:
                    txt_marquee.update()
            except Exception:
                logging.exception("Se detuvo la animacion 22F-010")
                break
            time.sleep(0.08)

    def actualizar_reloj():
        while formulario_activo:
            momento = datetime.datetime.now()
            try:
                txt_reloj.value = momento.strftime("%H:%M:%S")
                if not fecha_fijada:
                    txt_fecha.value = momento.strftime("%Y-%m-%d")
                if not hora_fijada:
                    txt_hora.value = momento.strftime("%H:%M:%S")
                if pagina_lista:
                    txt_reloj.update()
                    if not fecha_fijada:
                        txt_fecha.update()
                    if not hora_fijada:
                        txt_hora.update()
            except Exception:
                logging.exception("Se detuvo el reloj 22F-010")
                break
            time.sleep(1)

    ruta_logo = resource_path(os.path.join("assets", "logo-crystal.png"))
    logo = (
        ft.Image(src="logo-crystal.png", width=180, height=60, fit=ft.BoxFit.CONTAIN)
        if os.path.exists(ruta_logo)
        else ft.Text("CRYSTAL S.A.S", color=COLOR_PRIMARIO,
                     weight=ft.FontWeight.BOLD)
    )

    header = ft.Container(
        bgcolor="white", border_radius=15, padding=20,
        content=ft.Column([
            ft.Row([ft.IconButton(
                ft.Icons.ARROW_BACK_ROUNDED, icon_color="white",
                bgcolor=COLOR_PRIMARIO, tooltip="Volver al menu",
                on_click=confirmar_salida,
            )]),
            ft.Row([
                logo,
                ft.Container(
                    expand=True, height=70, bgcolor=COLOR_TITULO,
                    border_radius=10, padding=12,
                    alignment=ft.Alignment.CENTER_LEFT, content=txt_marquee,
                ),
            ], spacing=15),
            ft.Divider(),
            ft.Row([
                ft.Column([
                    ft.Text(TITULO_FORMULARIO, size=24,
                            weight=ft.FontWeight.BOLD, color=COLOR_PRIMARIO),
                    ft.Text(SUBTITULO_FORMULARIO, color="#64748B"),
                    ft.Text(f"{nombre_completo} ({usuario_logueado})",
                            color="#64748B", size=12),
                ], spacing=3),
                ft.Column([
                    ft.Row([ft.Icon(ft.Icons.ACCESS_TIME, color=COLOR_PRIMARIO), txt_reloj]),
                    ft.Container(
                        padding=10, border_radius=8,
                        border=ft.Border.all(1.5, COLOR_PRIMARIO),
                        content=ft.Text(CODIGO_FORMULARIO, color=COLOR_PRIMARIO,
                                        weight=ft.FontWeight.BOLD),
                    ),
                ], horizontal_alignment=ft.CrossAxisAlignment.END),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ], spacing=8),
    )

    barra_operacion = ft.Container(
        bgcolor="white", border_radius=12, padding=18,
        border=ft.Border.all(1, COLOR_BORDE),
        content=ft.Column([
            ft.Row([
                ft.Column([
                    ft.Text("Fecha de medición", weight=ft.FontWeight.BOLD, size=13, color="#475569"),
                    ft.Row([txt_fecha, ft.IconButton(
                        ft.Icons.CALENDAR_TODAY_ROUNDED,
                        icon_color=COLOR_PRIMARIO,
                        tooltip="Seleccionar fecha",
                        on_click=lambda _: abrir_dialogo(date_picker),
                    )], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ], spacing=5),
                ft.Column([
                    ft.Text("Hora de medición", weight=ft.FontWeight.BOLD, size=13, color="#475569"),
                    ft.Row([txt_hora, ft.IconButton(
                        ft.Icons.ACCESS_TIME_ROUNDED,
                        icon_color=COLOR_PRIMARIO,
                        tooltip="Seleccionar hora",
                        on_click=lambda _: abrir_dialogo(time_picker),
                    )], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ], spacing=5),
            ], spacing=22, vertical_alignment=ft.CrossAxisAlignment.END),
            ft.Row([btn_actualizar_ahora], alignment=ft.MainAxisAlignment.END),
        ], spacing=5),
    )

    panel_captura = ft.Container(
        bgcolor="white", border_radius=15, padding=22,
        border=ft.Border.all(1, COLOR_BORDE),
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.EDIT_NOTE_ROUNDED, color=COLOR_PRIMARIO),
                ft.Text("REGISTRO DE LECTURA", size=18,
                        weight=ft.FontWeight.BOLD, color=COLOR_PRIMARIO),
            ], spacing=8),
            ft.Text(
                "Capture una lectura. No existen turnos, carrusel ni registros por turno.",
                color="#64748B", size=13,
            ),
            ft.Row([dd_caldera, txt_medidor, txt_ph, txt_soda],
                   spacing=12, run_spacing=12, wrap=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([btn_observaciones, texto_estado_observaciones], spacing=12,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True),
            txt_error,
            ft.Row([btn_agregar], alignment=ft.MainAxisAlignment.END),
        ], spacing=12),
    )

    encabezado_tabla = ft.Container(
        bgcolor="#F8FAFC", border_radius=8,
        padding=ft.Padding.symmetric(horizontal=14, vertical=11),
        border=ft.Border.all(1, COLOR_BORDE),
        content=ft.Row([
            ft.Container(ft.Text("FECHA / HORA", weight=ft.FontWeight.BOLD,
                                 color=COLOR_PRIMARIO, size=11), expand=2),
            ft.Container(ft.Text("CALDERA", weight=ft.FontWeight.BOLD,
                                 color=COLOR_PRIMARIO, size=11), expand=2),
            ft.Container(ft.Text("AGUA", weight=ft.FontWeight.BOLD,
                                 color=COLOR_PRIMARIO, size=11), expand=1),
            ft.Container(ft.Text("pH", weight=ft.FontWeight.BOLD,
                                 color=COLOR_PRIMARIO, size=11), expand=1),
            ft.Container(ft.Text("SODA", weight=ft.FontWeight.BOLD,
                                 color=COLOR_PRIMARIO, size=11), expand=1),
            ft.Container(ft.Text("USUARIO", weight=ft.FontWeight.BOLD,
                                 color=COLOR_PRIMARIO, size=11), expand=2),
            ft.Container(ft.Text("ACCIONES", weight=ft.FontWeight.BOLD,
                                 color=COLOR_PRIMARIO, size=11),
                         expand=2, alignment=ft.Alignment.CENTER_RIGHT),
        ]),
    )

    panel_pendientes = ft.Container(
        bgcolor="white", border_radius=15, padding=22,
        border=ft.Border.all(1, COLOR_BORDE),
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.TABLE_ROWS_ROUNDED, color=COLOR_PRIMARIO),
                ft.Text("TABLA DE REGISTROS PENDIENTES", size=18,
                        weight=ft.FontWeight.BOLD, color=COLOR_PRIMARIO),
            ]),
            ft.Text("Revisa las lecturas antes de enviarlas a SQL Server.",
                    color="#64748B", size=13),
            encabezado_tabla,
            contenedor_filas,
            ft.Divider(),
            ft.Row([btn_enviar], alignment=ft.MainAxisAlignment.END),
        ], spacing=10),
    )

    informacion = ft.Container(
        padding=14, bgcolor="#EFF6FF",
        border=ft.Border.all(1, "#BFDBFE"), border_radius=10,
        content=ft.Row([
            ft.Icon(ft.Icons.INFO_OUTLINE_ROUNDED, color=COLOR_PRIMARIO),
            ft.Text(
                "Cada fila conserva la fecha, la hora, la caldera y "
                "el usuario autenticado. El pH esperado es 9.1 a 9.5.",
                color=COLOR_PRIMARIO, size=13, expand=True,
            ),
        ], spacing=10),
    )

    page.add(ft.Container(
        expand=True, padding=10,
        content=ft.Column([
            header,
            barra_operacion,
            informacion,
            panel_captura,
            panel_pendientes,
        ], scroll=ft.ScrollMode.AUTO, spacing=14),
    ))

    pagina_lista = True
    actualizar_estado_observaciones()
    actualizar_tabla()
    recargar_historico()
    page.update()
    threading.Thread(target=animar_marquee, daemon=True).start()
    threading.Thread(target=actualizar_reloj, daemon=True).start()