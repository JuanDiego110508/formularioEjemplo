import datetime
import logging
import os
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import uuid4

import flet as ft
import pyodbc

import conexionform


# ============================================================
# FORMULARIO 3 - CONTROL DE PURGAS DE CALDERA
# Sin turnos, entrega ni recibe.
# Los registros se guardan primero como borradores locales.
# ============================================================

TABLA_REGISTRO = "dbo.Registro_Control_Purgas_Caldera"
CALDERAS = (1, 2)

COLOR_PRIMARIO = "#1E3A8A"
COLOR_TITULO = "#0F172A"
COLOR_FONDO = "#F8FAFC"
COLOR_BORDE = "#E2E8F0"
COLOR_EXITO = "#15803D"
COLOR_ERROR = "#B91C1C"
COLOR_ALERTA = "#D97706"

COLUMNAS_POR_CALDERA = {
    caldera: (
        f"purga_{caldera}_ph",
        f"purga_{caldera}_alcalinidad_m",
        f"purga_{caldera}_color",
        f"purga_{caldera}_soda_g",
    )
    for caldera in CALDERAS
}

COLUMNAS_MEDICION = tuple(
    columna
    for caldera in CALDERAS
    for columna in COLUMNAS_POR_CALDERA[caldera]
)

COLUMNAS_REGISTRO = (
    "fecha",
    "hora",
    *COLUMNAS_MEDICION,
    "usuario_registro",
)

CAMPOS_NUMERICOS = frozenset(
    columna
    for caldera in CALDERAS
    for columna in (
        f"purga_{caldera}_ph",
        f"purga_{caldera}_alcalinidad_m",
        f"purga_{caldera}_soda_g",
    )
)


@dataclass(frozen=True)
class BorradorRegistro:
    id_temporal: str
    fecha: str
    hora: str
    usuario_registro: str
    valores: dict[str, object]
    observaciones: str = ""


def parsear_valor_numerico(texto: str, nombre: str) -> Decimal:
    texto_normalizado = (texto or "").strip().replace(",", ".")

    if not texto_normalizado:
        raise ValueError(f"Completa el valor de {nombre}.")
    if texto_normalizado.count(".") > 1:
        raise ValueError(f"{nombre} tiene un formato decimal inválido.")
    if any(caracter not in "0123456789." for caracter in texto_normalizado):
        raise ValueError(f"{nombre} debe ser un número positivo.")

    try:
        valor = Decimal(texto_normalizado)
    except InvalidOperation as ex:
        raise ValueError(f"{nombre} debe ser un número válido.") from ex

    if not valor.is_finite() or valor < 0:
        raise ValueError(f"{nombre} debe ser un número positivo.")

    parte_entera, _, parte_decimal = texto_normalizado.partition(".")
    if len(parte_decimal) > 2:
        raise ValueError(f"{nombre} admite máximo dos decimales.")
    if len(parte_entera.lstrip("0")) > 8:
        raise ValueError(f"{nombre} admite máximo ocho dígitos enteros.")

    return valor


def validar_registro(campos: dict[str, str]) -> dict[str, object]:
    valores: dict[str, object] = {}

    for caldera in CALDERAS:
        definiciones = (
            (f"purga_{caldera}_ph", f"pH de caldera #{caldera}"),
            (
                f"purga_{caldera}_alcalinidad_m",
                f"Alcalinidad M de caldera #{caldera}",
            ),
            (f"purga_{caldera}_color", f"Color de caldera #{caldera}"),
            (f"purga_{caldera}_soda_g", f"Soda de caldera #{caldera}"),
        )

        for campo, etiqueta in definiciones:
            entrada = (campos.get(campo) or "").strip()
            if campo in CAMPOS_NUMERICOS:
                valores[campo] = parsear_valor_numerico(entrada, etiqueta)
            else:
                if not entrada:
                    raise ValueError(f"Completa el valor de {etiqueta}.")
                if len(entrada) > 50:
                    raise ValueError(f"{etiqueta} admite máximo 50 caracteres.")
                valores[campo] = entrada

    return valores


def obtener_desviaciones(valores: dict[str, object]) -> list[str]:
    desviaciones: list[str] = []

    for caldera in CALDERAS:
        ph = valores[f"purga_{caldera}_ph"]
        alcalinidad = valores[f"purga_{caldera}_alcalinidad_m"]

        if not isinstance(ph, Decimal) or not isinstance(alcalinidad, Decimal):
            raise ValueError("Los valores numéricos del registro no son válidos.")

        if ph < Decimal("10.5") or ph > Decimal("11.5"):
            desviaciones.append(
                f"Caldera #{caldera}: pH {ph} (control 10,5 a 11,5)."
            )
        if alcalinidad > Decimal("500"):
            desviaciones.append(
                f"Caldera #{caldera}: Alcalinidad M {alcalinidad} "
                "(máximo 500 ppm)."
            )

    return desviaciones


def validar_borrador_para_bd(borrador: BorradorRegistro) -> tuple[datetime.date, datetime.time, dict[str, object], str]:
    try:
        fecha_sql = datetime.date.fromisoformat(borrador.fecha)
        hora_sql = datetime.time.fromisoformat(borrador.hora)
    except ValueError as ex:
        raise ValueError("La fecha o la hora del borrador no son válidas.") from ex

    usuario_limpio = (borrador.usuario_registro or "").strip()
    if not usuario_limpio or len(usuario_limpio) > 100:
        raise ValueError(
            "El usuario de registro debe tener entre 1 y 100 caracteres."
        )

    valores_validados = validar_registro(
        {
            campo: str(borrador.valores.get(campo, ""))
            for campo in COLUMNAS_MEDICION
        }
    )
    return fecha_sql, hora_sql, valores_validados, usuario_limpio


def insertar_borradores_bd(borradores: list[BorradorRegistro]) -> list[int]:
    if not borradores:
        raise ValueError("No hay borradores seleccionados para enviar.")

    ids_temporales = [borrador.id_temporal for borrador in borradores]
    if len(ids_temporales) != len(set(ids_temporales)):
        raise ValueError("La selección contiene borradores duplicados.")

    registros_validados = [
        validar_borrador_para_bd(borrador) for borrador in borradores
    ]

    columnas_sql = ", ".join(COLUMNAS_REGISTRO)
    placeholders = ", ".join("?" for _ in COLUMNAS_REGISTRO)

    conn = None
    cursor = None
    ids: list[int] = []

    try:
        conn = conexionform.obtener_conexion_formulario()
        cursor = conn.cursor()

        for fecha_sql, hora_sql, valores, usuario in registros_validados:
            parametros = (
                fecha_sql.isoformat(),
                hora_sql.strftime("%H:%M:%S"),
                *(valores[columna] for columna in COLUMNAS_MEDICION),
                usuario,
            )
            cursor.execute(
                f"""
                INSERT INTO {TABLA_REGISTRO} ({columnas_sql})
                OUTPUT INSERTED.id_registro
                VALUES ({placeholders})
                """,
                *parametros,
            )
            fila = cursor.fetchone()
            if fila is None:
                raise RuntimeError(
                    "SQL Server no devolvió el identificador de un registro."
                )
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
    page.title = "Formulario 3 - Control de purgas de caldera"
    page.bgcolor = COLOR_FONDO

    formulario_activo = True
    interfaz_lista = False
    fecha_fijada: str | None = None
    hora_fijada: str | None = None
    id_borrador_en_edicion: str | None = None

    borradores: list[BorradorRegistro] = []
    selecciones: dict[str, ft.Checkbox] = {}

    def detener_formulario():
        nonlocal formulario_activo
        formulario_activo = False

    page.on_disconnect = lambda _: detener_formulario()

    def mostrar_dialogo(dialogo):
        if hasattr(page, "show_dialog"):
            page.show_dialog(dialogo)
        elif hasattr(page, "open"):
            page.open(dialogo)
        else:
            page.dialog = dialogo
            dialogo.open = True
            page.update()

    def cerrar_dialogo(dialogo):
        if hasattr(page, "pop_dialog"):
            page.pop_dialog()
        elif hasattr(page, "close"):
            page.close(dialogo)
        elif getattr(page, "dialog", None) is not None:
            page.dialog.open = False
            page.update()

    def mostrar_mensaje(texto: str, color: str):
        mensaje_estado.value = texto
        mensaje_estado.color = color
        mensaje_estado.visible = True
        page.update()

    ahora = datetime.datetime.now()

    campo_fecha = ft.TextField(
        value=ahora.date().isoformat(), read_only=True, width=160, height=45,
        border_radius=8, border_color="#CBD5E1", text_size=13,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
    )
    campo_hora = ft.TextField(
        value=ahora.strftime("%H:%M:%S"), read_only=True, width=130, height=45,
        border_radius=8, border_color="#CBD5E1", text_size=13,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
    )
    txt_reloj = ft.Text(
        ahora.strftime("%H:%M:%S"),
        size=18,
        weight=ft.FontWeight.BOLD,
        color=COLOR_PRIMARIO,
    )

    def obtener_fecha() -> str:
        return fecha_fijada or datetime.datetime.now().date().isoformat()

    def obtener_hora() -> str:
        return hora_fijada or datetime.datetime.now().strftime("%H:%M:%S")

    def cambiar_fecha(_):
        nonlocal fecha_fijada
        if selector_fecha.value:
            fecha_fijada = selector_fecha.value.strftime("%Y-%m-%d")
            campo_fecha.value = fecha_fijada
            boton_ahora.visible = True
            page.update()

    def cambiar_hora(_):
        nonlocal hora_fijada
        if selector_hora.value:
            hora_fijada = selector_hora.value.strftime("%H:%M:%S")
            campo_hora.value = hora_fijada
            boton_ahora.visible = True
            page.update()

    selector_fecha = ft.DatePicker(
        value=datetime.datetime.combine(ahora.date(), datetime.time.min),
        first_date=datetime.datetime(2000, 1, 1), last_date=ahora,
        current_date=ahora, on_change=cambiar_fecha,
    )
    selector_hora = ft.TimePicker(value=ahora.time(), on_change=cambiar_hora)

    def establecer_ahora(_):
        nonlocal fecha_fijada, hora_fijada
        fecha_fijada = None
        hora_fijada = None
        momento = datetime.datetime.now()
        campo_fecha.value = momento.date().isoformat()
        campo_hora.value = momento.strftime("%H:%M:%S")
        selector_fecha.value = datetime.datetime.combine(
            momento.date(), datetime.time.min
        )
        selector_hora.value = momento.time()
        boton_ahora.visible = False
        page.update()

    boton_ahora = ft.TextButton(
        "Usar fecha y hora actuales", icon=ft.Icons.UPDATE_ROUNDED,
        visible=False, on_click=establecer_ahora,
    )

    campos: dict[str, ft.TextField] = {}
    paneles_caldera: list[ft.Container] = []

    for caldera in CALDERAS:
        fondo = "#EFF6FF" if caldera == 1 else "#FFF7ED"
        color_caldera = "#0284C7" if caldera == 1 else "#EA580C"
        color_borde = "#BFDBFE" if caldera == 1 else "#FED7AA"
        parametros = (
            (f"purga_{caldera}_ph", "pH", "UN", True),
            (f"purga_{caldera}_alcalinidad_m", "Alcalinidad M", "ppm", True),
            (f"purga_{caldera}_color", "Color", "", False),
            (f"purga_{caldera}_soda_g", "Soda adicionada", "g", True),
        )
        entradas: list[ft.TextField] = []

        for clave, nombre, unidad, numerico in parametros:
            etiqueta = f"{nombre} ({unidad})" if unidad else nombre
            control = ft.TextField(
                label=etiqueta,
                hint_text="Hasta 2 decimales" if numerico else "Texto breve",
                keyboard_type=(
                    ft.KeyboardType.NUMBER if numerico else ft.KeyboardType.TEXT
                ),
                max_length=20 if numerico else 50, width=205,
                color="#334155", label_style=ft.TextStyle(color="#475569"),
                border_radius=8, border_color="#CBD5E1",
                focused_border_color=color_caldera,
            )
            campos[clave] = control
            entradas.append(control)

        paneles_caldera.append(
            ft.Container(
                expand=True, padding=16, bgcolor=fondo,
                border=ft.Border.all(1, color_borde), border_radius=11,
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED,
                                color=color_caldera),
                        ft.Text(f"PURGA CALDERA #{caldera}", size=15,
                                weight=ft.FontWeight.BOLD, color=color_caldera),
                    ], spacing=8),
                    ft.Row(controls=entradas, spacing=10, run_spacing=10, wrap=True),
                ], spacing=12),
            )
        )

    campo_observaciones = ft.TextField(
        label="Observaciones del registro",
        hint_text="Novedades, desviaciones o acciones realizadas...",
        multiline=True,
        min_lines=3,
        max_lines=5,
        max_length=1000,
        width=900,
        border_radius=8,
        border_color="#CBD5E1",
        focused_border_color=COLOR_PRIMARIO,
    )

    mensaje_estado = ft.Text("", visible=False, size=13)
    estado_edicion = ft.Text("", visible=False, size=12, color="#1D4ED8")
    columna_borradores = ft.Column(spacing=8)
    estado_vacio = ft.Container(
        padding=18, bgcolor="#F8FAFC", border=ft.Border.all(1, COLOR_BORDE),
        border_radius=9,
        content=ft.Text(
            "Aún no hay borradores. Completa las dos calderas y guarda el registro.",
            size=13, color="#475569",
        ),
    )
    boton_enviar = ft.ElevatedButton(
        "Enviar borradores seleccionados", icon=ft.Icons.SEND_ROUNDED,
        bgcolor=COLOR_PRIMARIO, color="white", disabled=True,
    )

    def limpiar_captura():
        nonlocal id_borrador_en_edicion
        for control in campos.values():
            control.value = ""
        campo_observaciones.value = ""
        id_borrador_en_edicion = None
        estado_edicion.visible = False
        boton_guardar.text = "Guardar registro como borrador"
        boton_guardar.icon = ft.Icons.DRAFTS_OUTLINED

    def buscar_borrador(id_temporal: str) -> BorradorRegistro | None:
        return next(
            (borrador for borrador in borradores
             if borrador.id_temporal == id_temporal),
            None,
        )

    def ver_borrador(id_temporal: str):
        borrador = buscar_borrador(id_temporal)

        if borrador is None:
            mostrar_mensaje(
                "El borrador ya no está disponible.",
                COLOR_ERROR,
            )
            return

        desviaciones = obtener_desviaciones(borrador.valores)

        def crear_fila_detalle(
            etiqueta: str,
            valor: str,
            unidad: str = "",
        ):
            texto_valor = f"{valor} {unidad}" if unidad else valor

            return ft.Container(
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                bgcolor="white",
                border=ft.Border.all(1, "#E2E8F0"),
                border_radius=7,
                content=ft.Row(
                    [
                        ft.Text(
                            etiqueta,
                            size=12,
                            color="#64748B",
                            weight=ft.FontWeight.W_500,
                        ),
                        ft.Text(
                            texto_valor,
                            size=13,
                            color=COLOR_TITULO,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )

        tarjetas_caldera = []

        for caldera in CALDERAS:
            color_caldera = "#0284C7" if caldera == 1 else "#EA580C"
            fondo_caldera = "#EFF6FF" if caldera == 1 else "#FFF7ED"
            borde_caldera = "#BFDBFE" if caldera == 1 else "#FED7AA"

            tarjetas_caldera.append(
                ft.Container(
                    expand=True,
                    padding=14,
                    bgcolor=fondo_caldera,
                    border=ft.Border.all(1, borde_caldera),
                    border_radius=12,
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Container(
                                        width=38,
                                        height=38,
                                        alignment=ft.Alignment.CENTER,
                                        bgcolor="white",
                                        border_radius=9,
                                        content=ft.Icon(
                                            ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED,
                                            color=color_caldera,
                                            size=22,
                                        ),
                                    ),
                                    ft.Text(
                                        f"CALDERA #{caldera}",
                                        size=14,
                                        weight=ft.FontWeight.BOLD,
                                        color=color_caldera,
                                    ),
                                ],
                                spacing=9,
                            ),
                            crear_fila_detalle(
                                "pH",
                                str(borrador.valores[f"purga_{caldera}_ph"]),
                            ),
                            crear_fila_detalle(
                                "Alcalinidad M",
                                str(
                                    borrador.valores[
                                        f"purga_{caldera}_alcalinidad_m"
                                    ]
                                ),
                                "ppm",
                            ),
                            crear_fila_detalle(
                                "Color",
                                str(
                                    borrador.valores[
                                        f"purga_{caldera}_color"
                                    ]
                                ),
                            ),
                            crear_fila_detalle(
                                "Soda adicionada",
                                str(
                                    borrador.valores[
                                        f"purga_{caldera}_soda_g"
                                    ]
                                ),
                                "g",
                            ),
                        ],
                        spacing=8,
                    ),
                )
            )

        if desviaciones:
            bloque_control = ft.Container(
                padding=12,
                bgcolor="#FEF2F2",
                border=ft.Border.all(1, "#FECACA"),
                border_radius=10,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.WARNING_AMBER_ROUNDED,
                                    color=COLOR_ERROR,
                                    size=20,
                                ),
                                ft.Text(
                                    "DESVIACIONES DETECTADAS",
                                    color=COLOR_ERROR,
                                    weight=ft.FontWeight.BOLD,
                                    size=13,
                                ),
                            ],
                            spacing=7,
                        ),
                        *[
                            ft.Text(
                                f"• {desviacion}",
                                size=12,
                                color="#7F1D1D",
                            )
                            for desviacion in desviaciones
                        ],
                    ],
                    spacing=6,
                ),
            )
        else:
            bloque_control = ft.Container(
                padding=12,
                bgcolor="#F0FDF4",
                border=ft.Border.all(1, "#BBF7D0"),
                border_radius=10,
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE_ROUNDED,
                            color=COLOR_EXITO,
                            size=21,
                        ),
                        ft.Text(
                            "Valores dentro de los controles definidos.",
                            color=COLOR_EXITO,
                            weight=ft.FontWeight.BOLD,
                            size=13,
                        ),
                    ],
                    spacing=8,
                ),
            )

        dialogo = ft.AlertDialog(
            modal=True,
            bgcolor="white",
            title=ft.Container(
                padding=ft.Padding.only(bottom=6),
                content=ft.Row(
                    [
                        ft.Container(
                            width=42,
                            height=42,
                            alignment=ft.Alignment.CENTER,
                            bgcolor="#EFF6FF",
                            border_radius=10,
                            content=ft.Icon(
                                ft.Icons.VISIBILITY_ROUNDED,
                                color=COLOR_PRIMARIO,
                                size=23,
                            ),
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    "Vista previa del borrador",
                                    size=18,
                                    color=COLOR_PRIMARIO,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(
                                    "Revisa la información antes de enviarla.",
                                    size=12,
                                    color="#64748B",
                                ),
                            ],
                            spacing=2,
                        ),
                    ],
                    spacing=11,
                ),
            ),
            content=ft.Container(
                width=700,
                height=520,
                bgcolor="white",
                content=ft.Column(
                    [
                        ft.Container(
                            padding=12,
                            bgcolor="#F8FAFC",
                            border=ft.Border.all(1, COLOR_BORDE),
                            border_radius=10,
                            content=ft.Row(
                                [
                                    ft.Row(
                                        [
                                            ft.Icon(
                                                ft.Icons.CALENDAR_MONTH_ROUNDED,
                                                color=COLOR_PRIMARIO,
                                                size=20,
                                            ),
                                            ft.Text(
                                                borrador.fecha,
                                                weight=ft.FontWeight.BOLD,
                                                color=COLOR_TITULO,
                                            ),
                                        ],
                                        spacing=6,
                                    ),
                                    ft.Row(
                                        [
                                            ft.Icon(
                                                ft.Icons.ACCESS_TIME_ROUNDED,
                                                color=COLOR_PRIMARIO,
                                                size=20,
                                            ),
                                            ft.Text(
                                                borrador.hora,
                                                weight=ft.FontWeight.BOLD,
                                                color=COLOR_TITULO,
                                            ),
                                        ],
                                        spacing=6,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                        ),
                        ft.Row(
                            tarjetas_caldera,
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        ft.Container(
                            padding=12,
                            bgcolor="#F8FAFC",
                            border=ft.Border.all(1, COLOR_BORDE),
                            border_radius=10,
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Icon(
                                                ft.Icons.COMMENT_OUTLINED,
                                                color=COLOR_PRIMARIO,
                                                size=20,
                                            ),
                                            ft.Text(
                                                "OBSERVACIONES",
                                                weight=ft.FontWeight.BOLD,
                                                color=COLOR_TITULO,
                                            ),
                                        ],
                                        spacing=7,
                                    ),
                                    ft.Text(
                                        borrador.observaciones
                                        or "Sin observaciones.",
                                        color="#475569",
                                        size=13,
                                    ),
                                ],
                                spacing=7,
                            ),
                        ),
                        bloque_control,
                    ],
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                ),
            ),
            actions=[
                ft.OutlinedButton(
                    "Cargar para editar",
                    icon=ft.Icons.EDIT_OUTLINED,
                    on_click=lambda _: (
                        cerrar_dialogo(dialogo),
                        cargar_borrador(id_temporal),
                    ),
                    style=ft.ButtonStyle(
                        color=COLOR_PRIMARIO,
                        side=ft.BorderSide(1, COLOR_PRIMARIO),
                    ),
                ),
                ft.ElevatedButton(
                    "Cerrar",
                    icon=ft.Icons.CLOSE_ROUNDED,
                    bgcolor=COLOR_PRIMARIO,
                    color="white",
                    on_click=lambda _: cerrar_dialogo(dialogo),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        mostrar_dialogo(dialogo)

    def actualizar_lista_borradores():
        columna_borradores.controls.clear()
        seleccionados = 0

        for borrador in sorted(borradores, key=lambda item: (item.fecha, item.hora)):
            checkbox = selecciones[borrador.id_temporal]
            seleccionados += int(bool(checkbox.value))
            desviaciones = obtener_desviaciones(borrador.valores)
            detalle = (
                f"{len(desviaciones)} desviación(es) detectada(s)."
                if desviaciones else
                "Valores dentro de los controles definidos."
            )
            color_detalle = COLOR_ALERTA if desviaciones else COLOR_EXITO

            columna_borradores.controls.append(
                ft.Container(
                    padding=12, bgcolor="white",
                    border=ft.Border.all(1, COLOR_BORDE), border_radius=9,
                    content=ft.Row([
                        checkbox,
                        ft.Column([
                            ft.Text(
                                f"Registro del {borrador.fecha} a las {borrador.hora}",
                                weight=ft.FontWeight.BOLD, color=COLOR_TITULO,
                            ),
                            ft.Text(
                                f"Usuario: {borrador.usuario_registro} | {detalle}",
                                size=12, color=color_detalle,
                            ),
                            ft.Text(
                                f"Observaciones: {borrador.observaciones or 'Sin observaciones'}",
                                size=11,
                                color="#64748B",
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ], spacing=3, expand=True),
                        ft.IconButton(
                            icon=ft.Icons.VISIBILITY_ROUNDED,
                            tooltip="Ver borrador",
                            icon_color=COLOR_PRIMARIO,
                            on_click=lambda _, rid=borrador.id_temporal: ver_borrador(rid),
                        ),
                        ft.OutlinedButton(
                            "Cargar / editar", icon=ft.Icons.EDIT_OUTLINED,
                            on_click=lambda _, rid=borrador.id_temporal: cargar_borrador(rid),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                            tooltip="Eliminar borrador", icon_color=COLOR_ERROR,
                            on_click=lambda _, rid=borrador.id_temporal: eliminar_borrador(rid),
                        ),
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                )
            )

        estado_vacio.visible = not borradores
        boton_enviar.disabled = seleccionados == 0
        page.update()

    def cargar_borrador(id_temporal: str):
        nonlocal id_borrador_en_edicion, fecha_fijada, hora_fijada
        borrador = buscar_borrador(id_temporal)
        if borrador is None:
            mostrar_mensaje("El borrador ya no está disponible.", COLOR_ERROR)
            return

        id_borrador_en_edicion = id_temporal

        # La fecha original del borrador se conserva durante la edición.
        fecha_fijada = borrador.fecha
        campo_fecha.value = borrador.fecha
        selector_fecha.value = datetime.datetime.combine(
        datetime.date.fromisoformat(borrador.fecha),
        datetime.time.min,
        )

        # La hora no se fija al cargar el borrador.
        # Continúa avanzando y al actualizar se guarda la hora actual.
        hora_fijada = None
        momento_actual = datetime.datetime.now()
        campo_hora.value = momento_actual.strftime("%H:%M:%S")
        selector_hora.value = momento_actual.time()

        # Se mantiene visible porque la fecha está fijada al día del borrador.
        boton_ahora.visible = True

        for nombre, valor in borrador.valores.items():
            if nombre in campos:
                campos[nombre].value = str(valor)
        campo_observaciones.value = borrador.observaciones

        boton_guardar.text = "Actualizar borrador"
        boton_guardar.icon = ft.Icons.SAVE_AS_OUTLINED
        estado_edicion.value = "Estás editando un borrador existente."
        estado_edicion.visible = True
        mensaje_estado.visible = False
        page.update()

    def eliminar_borrador(id_temporal: str):
        nonlocal id_borrador_en_edicion
        borrador = buscar_borrador(id_temporal)
        if borrador is None:
            return
        borradores.remove(borrador)
        selecciones.pop(id_temporal, None)

        if id_borrador_en_edicion == id_temporal:
            limpiar_captura()

        actualizar_lista_borradores()
        mostrar_mensaje("Borrador eliminado.", COLOR_ERROR)

    def guardar_borrador_confirmado(
        dialogo,
        fecha: str,
        hora: str,
        valores: dict[str, object],
    ):
        cerrar_dialogo(dialogo)
        guardar_o_actualizar_borrador(fecha, hora, valores)

    def guardar_o_actualizar_borrador(
        fecha: str,
        hora: str,
        valores: dict[str, object],
    ):
        nonlocal id_borrador_en_edicion

        if id_borrador_en_edicion is None:
            id_temporal = uuid4().hex
            borrador = BorradorRegistro(
                id_temporal=id_temporal,
                fecha=fecha,
                hora=hora,
                usuario_registro=usuario_logueado.strip(),
                valores=dict(valores),
                observaciones=(campo_observaciones.value or "").strip(),
            )
            borradores.append(borrador)
            selecciones[id_temporal] = ft.Checkbox(
                label="Incluir", value=True,
                on_change=lambda _: actualizar_lista_borradores(),
            )
            mensaje = "Registro guardado como borrador para revisión."
        else:
            anterior = buscar_borrador(id_borrador_en_edicion)
            if anterior is None:
                id_borrador_en_edicion = None
                mostrar_mensaje("No fue posible actualizar el borrador.", COLOR_ERROR)
                return
            indice = borradores.index(anterior)
            borradores[indice] = BorradorRegistro(
                id_temporal=anterior.id_temporal,
                fecha=fecha,
                hora=hora,
                usuario_registro=usuario_logueado.strip(),
                valores=dict(valores),
                observaciones=(campo_observaciones.value or "").strip(),
            )
            mensaje = "Borrador actualizado correctamente."

        limpiar_captura()
        actualizar_lista_borradores()
        mostrar_mensaje(mensaje, COLOR_EXITO)

    def guardar_borrador(_):
        mensaje_estado.visible = False
        try:
            valores = validar_registro({
                nombre: control.value or ""
                for nombre, control in campos.items()
            })
        except ValueError as ex:
            mostrar_mensaje(str(ex), COLOR_ERROR)
            return

        fecha = obtener_fecha()
        hora = obtener_hora()
        desviaciones = obtener_desviaciones(valores)

        if not desviaciones:
            guardar_o_actualizar_borrador(fecha, hora, valores)
            return

        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                f"{len(desviaciones)} valor(es) fuera del control",
                color="#991B1B", weight=ft.FontWeight.BOLD,
            ),
            content=ft.Container(
                width=520, height=280,
                content=ft.Column([
                    ft.Text(
                        "Puedes corregir los valores o conservarlos en el borrador.",
                        size=13, color="#475569",
                    ),
                    *[
                        ft.Container(
                            padding=9, bgcolor="#FEF2F2",
                            border=ft.Border.all(1, "#FECACA"), border_radius=8,
                            content=ft.Text(item, color="#7F1D1D", size=13),
                        ) for item in desviaciones
                    ],
                ], spacing=8, scroll=ft.ScrollMode.AUTO),
            ),
            actions=[
                ft.OutlinedButton(
                    "Volver a revisar",
                    on_click=lambda _: cerrar_dialogo(dialogo),
                ),
                ft.ElevatedButton(
                    "Conservar como borrador", icon=ft.Icons.DRAFTS_OUTLINED,
                    bgcolor=COLOR_ALERTA, color="white",
                    on_click=lambda _: guardar_borrador_confirmado(
                        dialogo, fecha, hora, valores
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        mostrar_dialogo(dialogo)

    boton_guardar = ft.ElevatedButton(
        "Guardar registro como borrador", icon=ft.Icons.DRAFTS_OUTLINED,
        bgcolor=COLOR_PRIMARIO, color="white", on_click=guardar_borrador,
    )

    def completar_envio(ids_seleccionados: list[str]):
        seleccionados = [
            borrador for borrador in borradores
            if borrador.id_temporal in ids_seleccionados
        ]
        boton_enviar.disabled = True
        page.update()

        try:
            ids_bd = insertar_borradores_bd(seleccionados)
        except ValueError as ex:
            mostrar_mensaje(str(ex), COLOR_ERROR)
        except pyodbc.Error:
            logging.exception("SQL Server rechazó el envío del Formulario 3.")
            mostrar_mensaje(
                "No fue posible enviar los registros. Verifica la conexión, "
                "la tabla y sus columnas en SQL Server.",
                COLOR_ERROR,
            )
        except RuntimeError as ex:
            logging.exception("SQL Server no confirmó el Formulario 3.")
            mostrar_mensaje(str(ex), COLOR_ERROR)
        else:
            borradores[:] = [
                borrador for borrador in borradores
                if borrador.id_temporal not in ids_seleccionados
            ]
            for id_temporal in ids_seleccionados:
                selecciones.pop(id_temporal, None)
            actualizar_lista_borradores()
            mostrar_mensaje(
                f"Se enviaron {len(ids_bd)} registro(s) a SQL Server. "
                f"Identificadores: {', '.join(map(str, ids_bd))}.",
                COLOR_EXITO,
            )
        finally:
            actualizar_lista_borradores()

    def confirmar_envio(dialogo, ids_seleccionados: list[str]):
        cerrar_dialogo(dialogo)
        completar_envio(ids_seleccionados)

    def enviar_borradores(_):
        ids_seleccionados = [
            borrador.id_temporal
            for borrador in borradores
            if selecciones[borrador.id_temporal].value
        ]
        if not ids_seleccionados:
            mostrar_mensaje("Selecciona al menos un borrador para enviar.", COLOR_ERROR)
            return

        seleccionados = [
            borrador for borrador in borradores
            if borrador.id_temporal in ids_seleccionados
        ]
        desviaciones = sum(
            len(obtener_desviaciones(borrador.valores))
            for borrador in seleccionados
        )

        resumen = ft.Column([
            ft.Container(
                padding=9, bgcolor="#F8FAFC", border_radius=8,
                content=ft.Text(
                    f"{borrador.fecha} {borrador.hora} | "
                    f"Usuario: {borrador.usuario_registro} | "
                    f"pH C1: {borrador.valores['purga_1_ph']} | "
                    f"pH C2: {borrador.valores['purga_2_ph']} | "
                    f"Observaciones: {borrador.observaciones or 'Sin observaciones'}",
                    size=12,
                ),
            ) for borrador in seleccionados
        ], spacing=6, scroll=ft.ScrollMode.AUTO)

        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Confirmar envío a SQL Server",
                color=COLOR_PRIMARIO, weight=ft.FontWeight.BOLD,
            ),
            content=ft.Container(
                width=620,
                height=min(410, 150 + len(seleccionados) * 55),
                content=ft.Column([
                    ft.Text(
                        f"Se enviarán {len(seleccionados)} registro(s). "
                        f"Desviaciones encontradas: {desviaciones}.",
                        color="#475569",
                    ),
                    resumen,
                    ft.Text(
                        "Después de confirmar, los registros quedarán guardados "
                        "definitivamente en la base de datos.",
                        size=12, color="#64748B",
                    ),
                ], spacing=10),
            ),
            actions=[
                ft.OutlinedButton(
                    "Cancelar", on_click=lambda _: cerrar_dialogo(dialogo),
                ),
                ft.ElevatedButton(
                    "Confirmar y enviar", icon=ft.Icons.CLOUD_UPLOAD_ROUNDED,
                    bgcolor=COLOR_EXITO, color="white",
                    on_click=lambda _: confirmar_envio(
                        dialogo, ids_seleccionados
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        mostrar_dialogo(dialogo)

    boton_enviar.on_click = enviar_borradores

    def confirmar_salida(_):
        if on_logout is None:
            return
        mensaje = (
            f"Hay {len(borradores)} borrador(es) sin enviar. Se perderán al salir."
            if borradores else
            "Volverás al menú principal."
        )
        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED,
                        color="#DC2626", size=28),
                ft.Text("¿Seguro que deseas salir?", size=18,
                        weight=ft.FontWeight.BOLD, color="#DC2626"),
            ], spacing=8),
            content=ft.Text(mensaje, size=13, color="#334155"),
            actions=[
                ft.OutlinedButton(
                    "Cancelar", on_click=lambda _: cerrar_dialogo(dialogo),
                ),
                ft.ElevatedButton(
                    "Sí, continuar y salir",
                    on_click=lambda _: salir(dialogo),
                    bgcolor="#DC2626", color="white",
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        mostrar_dialogo(dialogo)

    def salir(dialogo):
        detener_formulario()
        cerrar_dialogo(dialogo)
        on_logout()

    marquee = ft.Text(
        "", size=16, color="#F8FAFC",
        weight=ft.FontWeight.BOLD, no_wrap=True,
    )

    def animar_marquee():
        texto = (
            " CONTROL DE PURGAS DE CALDERA • BORRADORES DE REGISTRO • "
            f"RESPONSABLE: {nombre_completo} • USUARIO: {usuario_logueado} • "
            "CRYSTAL S.A.S • "
        ) * 8
        while formulario_activo:
            try:
                texto = texto[1:] + texto[0]
                marquee.value = texto
                if interfaz_lista:
                    marquee.update()
            except Exception:
                logging.exception(
                    "Se detuvo la animación del encabezado del Formulario 3."
                )
                break
            time.sleep(0.08)

    def actualizar_fecha_hora():
        while formulario_activo:
            try:
                momento = datetime.datetime.now()
                if fecha_fijada is None:
                    campo_fecha.value = momento.date().isoformat()
                if hora_fijada is None:
                    campo_hora.value = momento.strftime("%H:%M:%S")
                txt_reloj.value = momento.strftime("%H:%M:%S")
                if interfaz_lista:
                    txt_reloj.update()
                    if fecha_fijada is None:
                        campo_fecha.update()
                    if hora_fijada is None:
                        campo_hora.update()
            except Exception:
                logging.exception(
                    "Se detuvo la actualización de fecha y hora del Formulario 3."
                )
                break
            time.sleep(1)

    ruta_logo = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "assets", "logo-crystal.png",
    )
    logo = (
        ft.Image(src="logo-crystal.png", width=180, height=60,
                 fit=ft.BoxFit.CONTAIN)
        if os.path.isfile(ruta_logo)
        else ft.Text("CRYSTAL S.A.S.", size=20,
                     weight=ft.FontWeight.BOLD, color=COLOR_PRIMARIO)
    )

    encabezado = ft.Container(
        bgcolor="white", border_radius=15, padding=20,
        content=ft.Column([
            ft.IconButton(
                icon=ft.Icons.ARROW_BACK_ROUNDED, icon_color="white",
                bgcolor=COLOR_PRIMARIO, tooltip="Volver al menú",
                on_click=confirmar_salida,
            ),
            ft.Row([
                logo,
                ft.Container(
                    expand=True, height=70, bgcolor=COLOR_TITULO,
                    border_radius=10, padding=12,
                    alignment=ft.Alignment.CENTER_LEFT, content=marquee,
                ),
            ], spacing=15),
            ft.Divider(),
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                "CONTROL DE PURGAS DE CALDERA",
                                size=24,
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_PRIMARIO,
                            ),
                            ft.Text(
                                f"{nombre_completo} ({usuario_logueado})",
                                color="#64748B",
                                size=12,
                            ),
                        ],
                        spacing=5,
                        expand=True,
                    ),
                    ft.Container(
                        padding=ft.Padding.symmetric(
                            horizontal=16,
                            vertical=11,
                        ),
                        bgcolor="#F8FAFC",
                        border=ft.Border.all(1, "#CBD5E1"),
                        border_radius=10,
                        content=ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.ACCESS_TIME_ROUNDED,
                                    color=COLOR_PRIMARIO,
                                    size=25,
                                ),
                                txt_reloj,
                            ],
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ], spacing=8),
    )

    barra_fecha = ft.Container(
        padding=16, bgcolor="white", border=ft.Border.all(1, COLOR_BORDE),
        border_radius=12,
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.CALENDAR_MONTH_ROUNDED, color=COLOR_TITULO),
                ft.Text("Fecha de operación:", weight=ft.FontWeight.BOLD,
                        color=COLOR_TITULO),
                campo_fecha,
                ft.IconButton(
                    icon=ft.Icons.CALENDAR_TODAY_ROUNDED,
                    icon_color=COLOR_PRIMARIO,
                    tooltip="Seleccionar fecha",
                    on_click=lambda _: mostrar_dialogo(selector_fecha),
                ),
                ft.Text("Hora:", weight=ft.FontWeight.BOLD,
                        color=COLOR_TITULO),
                campo_hora,
                ft.IconButton(
                    icon=ft.Icons.ACCESS_TIME_ROUNDED,
                    icon_color=COLOR_PRIMARIO,
                    tooltip="Seleccionar hora",
                    on_click=lambda _: mostrar_dialogo(selector_hora),
                ),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row(
                [boton_ahora],
                alignment=ft.MainAxisAlignment.END,
            ),
        ], spacing=8),
    )

    introduccion = ft.Container(
        padding=16, bgcolor="#EFF6FF",
        border=ft.Border.all(1, "#BFDBFE"), border_radius=10,
        content=ft.Row([
            ft.Icon(ft.Icons.INFO_OUTLINE_ROUNDED, color=COLOR_PRIMARIO),
            ft.Text(
                "Completa las dos calderas y guarda el registro como borrador. "
                "Después podrás revisarlo, editarlo, eliminarlo o enviarlo a SQL Server.",
                color=COLOR_PRIMARIO, size=13, expand=True,
            ),
        ], spacing=10),
    )

    panel_registro = ft.Container(
        padding=18, bgcolor="white", border=ft.Border.all(1, COLOR_BORDE),
        border_radius=14,
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.ASSIGNMENT_OUTLINED, color=COLOR_PRIMARIO),
                ft.Text("CAPTURA DEL REGISTRO", size=18,
                        weight=ft.FontWeight.BOLD, color=COLOR_PRIMARIO),
            ], spacing=8),
            ft.Row(controls=paneles_caldera, spacing=12),
            ft.Container(
                padding=14,
                bgcolor="#F8FAFC",
                border=ft.Border.all(1, COLOR_BORDE),
                border_radius=10,
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.ADD_COMMENT_OUTLINED,
                                color=COLOR_PRIMARIO),
                        ft.Text("OBSERVACIONES", weight=ft.FontWeight.BOLD,
                                color=COLOR_TITULO),
                    ], spacing=8),
                    campo_observaciones,
                ], spacing=8),
            ),
            estado_edicion,
            ft.Column([
                ft.Text(
                    "El borrador queda disponible para revisión antes del envío.",
                    size=12,
                    color="#64748B",
                ),
                ft.Row(
                    [boton_guardar],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ], spacing=6),
        ], spacing=14),
    )

    panel_borradores = ft.Container(
        padding=18, bgcolor="white", border=ft.Border.all(1, COLOR_BORDE),
        border_radius=14,
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.DRAFTS_OUTLINED, color=COLOR_PRIMARIO, size=22),
                ft.Text("BORRADORES PENDIENTES DE ENVÍO", size=17,
                        weight=ft.FontWeight.BOLD, color=COLOR_PRIMARIO),
            ], spacing=8),
            ft.Text(
                "Cada borrador representa un registro completo de las dos calderas. "
                "Selecciona los que quieras confirmar y enviar.",
                size=13, color="#475569",
            ),
            estado_vacio,
            columna_borradores,
            ft.Row([boton_enviar], alignment=ft.MainAxisAlignment.END),
            mensaje_estado,
        ], spacing=10),
    )

    columna_principal = ft.Column([
        encabezado,
        barra_fecha,
        introduccion,
        panel_registro,
        panel_borradores,
    ], spacing=14, tight=True, scroll=ft.ScrollMode.AUTO)

    page.add(ft.Container(
        expand=True, padding=10, content=columna_principal,
    ))

    interfaz_lista = True
    actualizar_lista_borradores()
    page.update()
    threading.Thread(target=animar_marquee, daemon=True).start()
    threading.Thread(target=actualizar_fecha_hora, daemon=True).start()