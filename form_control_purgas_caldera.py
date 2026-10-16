# ============================================================
# IMPORTACIONES
# ============================================================

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

COLOR_CALDERA_1 = "#0284C7"
COLOR_CALDERA_2 = "#EA580C"

FONDO_CALDERA_1 = "#EFF6FF"
FONDO_CALDERA_2 = "#FFF7ED"

BORDE_CALDERA_1 = "#BFDBFE"
BORDE_CALDERA_2 = "#FED7AA"


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

# Se conserva exactamente el flujo actual de la base de datos.
# Fecha + hora + 8 mediciones + usuario.
COLUMNAS_REGISTRO = (
    "fecha",
    "hora",
    *COLUMNAS_MEDICION,
    "usuario_registro",
    "observaciones",
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
        raise ValueError(
            f"{nombre} tiene un formato decimal inválido."
        )

    if any(
        caracter not in "0123456789."
        for caracter in texto_normalizado
    ):
        raise ValueError(
            f"{nombre} debe ser un número positivo."
        )

    try:
        valor = Decimal(texto_normalizado)
    except InvalidOperation as ex:
        raise ValueError(
            f"{nombre} debe ser un número válido."
        ) from ex

    if not valor.is_finite() or valor < 0:
        raise ValueError(
            f"{nombre} debe ser un número positivo."
        )

    parte_entera, _, parte_decimal = texto_normalizado.partition(".")

    if len(parte_decimal) > 2:
        raise ValueError(
            f"{nombre} admite máximo dos decimales."
        )

    if len(parte_entera.lstrip("0")) > 8:
        raise ValueError(
            f"{nombre} admite máximo ocho dígitos enteros."
        )

    return valor


def validar_registro(
    campos: dict[str, str],
) -> dict[str, object]:
    valores: dict[str, object] = {}

    for caldera in CALDERAS:
        definiciones = (
            (
                f"purga_{caldera}_ph",
                f"pH de caldera #{caldera}",
            ),
            (
                f"purga_{caldera}_alcalinidad_m",
                f"Alcalinidad M de caldera #{caldera}",
            ),
            (
                f"purga_{caldera}_color",
                f"Color de caldera #{caldera}",
            ),
            (
                f"purga_{caldera}_soda_g",
                f"Soda de caldera #{caldera}",
            ),
        )

        for campo, etiqueta in definiciones:
            entrada = (campos.get(campo) or "").strip()

            if campo in CAMPOS_NUMERICOS:
                valores[campo] = parsear_valor_numerico(
                    entrada,
                    etiqueta,
                )
            else:
                if not entrada:
                    raise ValueError(
                        f"Completa el valor de {etiqueta}."
                    )

                if len(entrada) > 50:
                    raise ValueError(
                        f"{etiqueta} admite máximo "
                        "50 caracteres."
                    )

                valores[campo] = entrada

    return valores


def obtener_desviaciones(
    valores: dict[str, object],
) -> list[str]:
    desviaciones: list[str] = []

    for caldera in CALDERAS:
        ph = valores[f"purga_{caldera}_ph"]
        alcalinidad = valores[
            f"purga_{caldera}_alcalinidad_m"
        ]

        if not isinstance(ph, Decimal):
            raise ValueError(
                "Los valores numéricos del registro "
                "no son válidos."
            )

        if not isinstance(alcalinidad, Decimal):
            raise ValueError(
                "Los valores numéricos del registro "
                "no son válidos."
            )

        if ph < Decimal("10.5") or ph > Decimal("11.5"):
            desviaciones.append(
                f"Caldera #{caldera}: pH {ph} "
                "(control 10,5 a 11,5)."
            )

        if alcalinidad > Decimal("500"):
            desviaciones.append(
                f"Caldera #{caldera}: Alcalinidad M "
                f"{alcalinidad} (máximo 500 ppm)."
            )

    return desviaciones


def validar_borrador_para_bd(
    borrador: BorradorRegistro,
) -> tuple[
    datetime.date,
    datetime.time,
    dict[str, object],
    str,
]:
    try:
        fecha_sql = datetime.date.fromisoformat(
            borrador.fecha
        )
        hora_sql = datetime.time.fromisoformat(
            borrador.hora
        )
    except ValueError as ex:
        raise ValueError(
            "La fecha o la hora del borrador "
            "no son válidas."
        ) from ex

    usuario_limpio = (
        borrador.usuario_registro or ""
    ).strip()

    if not usuario_limpio or len(usuario_limpio) > 100:
        raise ValueError(
            "El usuario de registro debe tener "
            "entre 1 y 100 caracteres."
        )

    valores_validados = validar_registro(
        {
            campo: str(
                borrador.valores.get(campo, "")
            )
            for campo in COLUMNAS_MEDICION
        }
    )

    return (
        fecha_sql,
        hora_sql,
        valores_validados,
        usuario_limpio,
    )


def insertar_borradores_bd(
    borradores: list[BorradorRegistro],
) -> list[int]:
    if not borradores:
        raise ValueError(
            "No hay borradores seleccionados para enviar."
        )

    ids_temporales = [
        borrador.id_temporal
        for borrador in borradores
    ]

    if len(ids_temporales) != len(set(ids_temporales)):
        raise ValueError(
            "La selección contiene borradores duplicados."
        )

    registros_validados = [
        validar_borrador_para_bd(borrador)
        for borrador in borradores
    ]

    columnas_sql = ", ".join(COLUMNAS_REGISTRO)
    placeholders = ", ".join(
        "?" for _ in COLUMNAS_REGISTRO
    )

    conn = None
    cursor = None
    ids: list[int] = []

    try:
        conn = conexionform.obtener_conexion_formulario()
        cursor = conn.cursor()

        for borrador, (
            fecha_sql,
            hora_sql,
            valores,
            usuario,
        ) in zip(borradores, registros_validados):
            parametros = (
                fecha_sql.isoformat(),
                hora_sql.strftime("%H:%M:%S"),
                *(
                    valores[columna]
                    for columna in COLUMNAS_MEDICION
                ),
                usuario,
                borrador.observaciones.strip() or None,
            )

            cursor.execute(
                f"""
                INSERT INTO {TABLA_REGISTRO}
                (
                    {columnas_sql}
                )
                OUTPUT INSERTED.id_registro
                VALUES
                (
                    {placeholders}
                )
                """,
                *parametros,
            )

            fila = cursor.fetchone()

            if fila is None:
                raise RuntimeError(
                    "SQL Server no devolvió el "
                    "identificador de un registro."
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
    page.title = (
        "Formulario 3 - Control de purgas de caldera"
    )
    page.bgcolor = COLOR_FONDO

    formulario_activo = True
    interfaz_lista = False

    fecha_fijada: str | None = None
    hora_fijada: str | None = None
    id_borrador_en_edicion: str | None = None

    borradores: list[BorradorRegistro] = []
    selecciones: dict[str, ft.Checkbox] = {}

    # ========================================================
    # FUNCIONES GENERALES
    # ========================================================

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

    # ========================================================
    # FECHA, HORA Y RELOJ
    # ========================================================

    ahora = datetime.datetime.now()

    campo_fecha = ft.TextField(
        value=ahora.date().isoformat(),
        read_only=True,
        width=150,
        height=42,
        border_radius=8,
        border_color="#CBD5E1",
        text_size=12,
        bgcolor="white",
        content_padding=ft.Padding.symmetric(
            horizontal=11,
            vertical=7,
        ),
    )

    campo_hora = ft.TextField(
        value=ahora.strftime("%H:%M:%S"),
        read_only=True,
        width=120,
        height=42,
        border_radius=8,
        border_color="#CBD5E1",
        text_size=12,
        bgcolor="white",
        content_padding=ft.Padding.symmetric(
            horizontal=11,
            vertical=7,
        ),
    )

    txt_reloj = ft.Text(
        ahora.strftime("%H:%M:%S"),
        size=13,
        weight=ft.FontWeight.BOLD,
        color=COLOR_PRIMARIO,
    )

    reloj_operacion = ft.Container(
        padding=ft.Padding.symmetric(
            horizontal=10,
            vertical=7,
        ),
        bgcolor="#EFF6FF",
        border=ft.Border.all(
            1,
            "#BFDBFE",
        ),
        border_radius=8,
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.SCHEDULE_ROUNDED,
                    color=COLOR_PRIMARIO,
                    size=17,
                ),
                txt_reloj,
            ],
            spacing=6,
            vertical_alignment=(
                ft.CrossAxisAlignment.CENTER
            ),
        ),
    )

    def obtener_fecha() -> str:
        return (
            fecha_fijada
            or datetime.datetime.now().date().isoformat()
        )

    def obtener_hora() -> str:
        return (
            hora_fijada
            or datetime.datetime.now().strftime("%H:%M:%S")
        )

    def cambiar_fecha(_):
        nonlocal fecha_fijada

        if selector_fecha.value:
            fecha_fijada = selector_fecha.value.strftime(
                "%Y-%m-%d"
            )
            campo_fecha.value = fecha_fijada
            boton_ahora.visible = True
            page.update()

    def cambiar_hora(_):
        nonlocal hora_fijada

        if selector_hora.value:
            hora_fijada = selector_hora.value.strftime(
                "%H:%M:%S"
            )
            campo_hora.value = hora_fijada
            boton_ahora.visible = True
            page.update()

    selector_fecha = ft.DatePicker(
        value=datetime.datetime.combine(
            ahora.date(),
            datetime.time.min,
        ),
        first_date=datetime.datetime(2000, 1, 1),
        last_date=ahora,
        current_date=ahora,
        on_change=cambiar_fecha,
    )

    selector_hora = ft.TimePicker(
        value=ahora.time(),
        on_change=cambiar_hora,
    )

    def establecer_ahora(_):
        nonlocal fecha_fijada
        nonlocal hora_fijada

        fecha_fijada = None
        hora_fijada = None

        momento = datetime.datetime.now()

        campo_fecha.value = momento.date().isoformat()
        campo_hora.value = momento.strftime("%H:%M:%S")

        selector_fecha.value = datetime.datetime.combine(
            momento.date(),
            datetime.time.min,
        )
        selector_hora.value = momento.time()

        boton_ahora.visible = False
        page.update()

    boton_ahora = ft.TextButton(
        "Usar fecha y hora actuales",
        icon=ft.Icons.UPDATE_ROUNDED,
        visible=False,
        on_click=establecer_ahora,
        style=ft.ButtonStyle(
            color=COLOR_PRIMARIO,
            padding=ft.Padding.symmetric(
                horizontal=8,
                vertical=5,
            ),
        ),
    )

    barra_fecha = ft.Container(
        padding=12,
        bgcolor="white",
        border=ft.Border.all(
            1,
            COLOR_BORDE,
        ),
        border_radius=10,
        content=ft.Column(
            controls=[
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(
                            col={
                                "xs": 12,
                                "sm": 12,
                                "md": 5,
                                "lg": 5,
                            },
                            content=ft.Row(
                                controls=[
                                    ft.Icon(
                                        ft.Icons.CALENDAR_MONTH_ROUNDED,
                                        color=COLOR_PRIMARIO,
                                        size=19,
                                    ),
                                    ft.Text(
                                        "Fecha de medición:",
                                        size=12,
                                        weight=ft.FontWeight.BOLD,
                                        color=COLOR_TITULO,
                                    ),
                                    campo_fecha,
                                    ft.IconButton(
                                        icon=(
                                            ft.Icons
                                            .CALENDAR_TODAY_ROUNDED
                                        ),
                                        icon_color=COLOR_PRIMARIO,
                                        icon_size=19,
                                        tooltip="Seleccionar fecha",
                                        on_click=lambda _: mostrar_dialogo(
                                            selector_fecha
                                        ),
                                    ),
                                ],
                                spacing=6,
                                vertical_alignment=(
                                    ft.CrossAxisAlignment.CENTER
                                ),
                            ),
                        ),
                        ft.Container(
                            col={
                                "xs": 12,
                                "sm": 12,
                                "md": 5,
                                "lg": 5,
                            },
                            content=ft.Row(
                                controls=[
                                    ft.Icon(
                                        ft.Icons.ACCESS_TIME_ROUNDED,
                                        color=COLOR_PRIMARIO,
                                        size=18,
                                    ),
                                    ft.Text(
                                        "Hora de medición:",
                                        size=12,
                                        weight=ft.FontWeight.BOLD,
                                        color=COLOR_TITULO,
                                    ),
                                    campo_hora,
                                    ft.IconButton(
                                        icon=ft.Icons.MORE_TIME_ROUNDED,
                                        icon_color=COLOR_PRIMARIO,
                                        icon_size=19,
                                        tooltip="Seleccionar hora",
                                        on_click=lambda _: mostrar_dialogo(
                                            selector_hora
                                        ),
                                    ),
                                ],
                                spacing=6,
                                vertical_alignment=(
                                    ft.CrossAxisAlignment.CENTER
                                ),
                            ),
                        ),
                        ft.Container(
                            col={
                                "xs": 12,
                                "sm": 12,
                                "md": 2,
                                "lg": 2,
                            },
                            alignment=ft.Alignment.CENTER_RIGHT,
                            content=reloj_operacion,
                        ),
                    ],
                    spacing=8,
                    run_spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    controls=[boton_ahora],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            spacing=2,
            tight=True,
        ),
    )
    # ========================================================
    # CAMPOS DE MEDICIÓN
    # ========================================================

    campos: dict[str, ft.TextField] = {}

    paneles_caldera: dict[int, ft.Container] = {}
    contenidos_caldera: dict[int, ft.Container] = {}
    botones_expansion_caldera: dict[int, ft.IconButton] = {}
    textos_resumen_caldera: dict[int, ft.Text] = {}

    secciones_expandidas: dict[int, bool] = {
        caldera: False
        for caldera in CALDERAS
    }


    def obtener_resumen_caldera(caldera: int) -> str:
        valores_completos = sum(
            1
            for columna in COLUMNAS_POR_CALDERA[caldera]
            if (campos[columna].value or "").strip()
        )

        total_campos = len(
            COLUMNAS_POR_CALDERA[caldera]
        )

        if valores_completos == 0:
            return "Sin diligenciar"

        if valores_completos == total_campos:
            return "Sección completa"

        return (
            f"{valores_completos} de "
            f"{total_campos} campos diligenciados"
        )

    def actualizar_tarjeta_caldera(caldera: int, actualizar_pagina: bool = True,):
        if caldera not in contenidos_caldera:
            logging.error(
                "No se encontró el contenido de la caldera %s.",
                caldera,
            )
            return
        
        esta_expandida = secciones_expandidas[caldera]

        contenido_campos = contenidos_caldera[caldera]
        boton_expandir = botones_expansion_caldera[caldera]
        texto_resumen = textos_resumen_caldera[caldera]

        contenido_campos.visible = esta_expandida

        boton_expandir.icon = (
            ft.Icons.EXPAND_LESS_ROUNDED
            if esta_expandida
            else ft.Icons.EXPAND_MORE_ROUNDED
        )

        texto_resumen.value = obtener_resumen_caldera(
            caldera
        )

        if actualizar_pagina and interfaz_lista:
            page.update()


    def alternar_seccion_caldera(caldera: int):
        if caldera not in secciones_expandidas:
            logging.warning(
                "Se intento desplegar una caldera inexistente: %s.",
                caldera,
            )
            return

        secciones_expandidas[caldera] = not (
            secciones_expandidas[caldera]
        )

        actualizar_tarjeta_caldera(caldera)

    for caldera in CALDERAS:
        fondo = (
            FONDO_CALDERA_1
            if caldera == 1
            else FONDO_CALDERA_2
        )
        color_caldera = (
            COLOR_CALDERA_1
            if caldera == 1
            else COLOR_CALDERA_2
        )
        color_borde = (
            BORDE_CALDERA_1
            if caldera == 1
            else BORDE_CALDERA_2
        )

        parametros = (
            (
                f"purga_{caldera}_ph",
                "pH",
                "UN",
                True,
            ),
            (
                f"purga_{caldera}_alcalinidad_m",
                "Alcalinidad M",
                "ppm",
                True,
            ),
            (
                f"purga_{caldera}_color",
                "Color",
                "",
                False,
            ),
            (
                f"purga_{caldera}_soda_g",
                "Soda adicionada",
                "g",
                True,
            ),
        )

        entradas: list[ft.TextField] = []

        for clave, nombre, unidad, numerico in parametros:
            etiqueta = (
                f"{nombre} ({unidad})"
                if unidad
                else nombre
            )

            control = ft.TextField(
                label=etiqueta,
                hint_text=(
                    "Hasta 2 decimales"
                    if numerico
                    else "Texto breve"
                ),
                keyboard_type=(
                    ft.KeyboardType.NUMBER
                    if numerico
                    else ft.KeyboardType.TEXT
                ),
                max_length=20 if numerico else 50,
                height=62,
                color="#334155",
                text_size=13,
                label_style=ft.TextStyle(
                    color="#475569",
                    size=12,
                ),
                border_radius=8,
                border_color="#CBD5E1",
                focused_border_color=color_caldera,
                focused_border_width=2,
                bgcolor="white",
                content_padding=ft.Padding.symmetric(
                    horizontal=12,
                    vertical=9,
                ),
            )

            campos[clave] = control
            entradas.append(control)

        texto_resumen = ft.Text(
            "Sin diligenciar",
            size=11,
            color="#64748B",
        )

        contenido_campos = ft.Container(
            visible=False,
            padding=ft.Padding.only(
                left=12,
                right=12,
                bottom=12,
            ),
            content=ft.ResponsiveRow(
                controls=[
                    ft.Container(
                        content=entrada,
                        col={
                            "xs": 12,
                            "sm": 6,
                            "md": 6,
                            "lg": 3,
                            "xl": 3,
                        },
                    )
                    for entrada in entradas
                ],
                spacing=10,
                run_spacing=8,
            ),
        )

        boton_expandir = ft.IconButton(
            icon=ft.Icons.EXPAND_MORE_ROUNDED,
            icon_color=color_caldera,
            tooltip="Expandir o contraer sección",
            on_click=(
                lambda _, numero=caldera: 
                alternar_seccion_caldera(numero)
            ),
        )

        contenidos_caldera[caldera] = contenido_campos
        botones_expansion_caldera[caldera] = boton_expandir
        textos_resumen_caldera[caldera] = texto_resumen

        encabezado_tarjeta = ft.Row(
            controls=[
                ft.Container(
                    width=38,
                    height=38,
                    alignment=ft.Alignment.CENTER,
                    bgcolor="white",
                    border_radius=9,
                    border=ft.Border.all(
                        1,
                        color_borde,
                    ),
                    content=ft.Icon(
                        ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED,
                        color=color_caldera,
                        size=21,
                    ),
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            f"PURGA CALDERA #{caldera}",
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=color_caldera,
                        ),
                        texto_resumen,
                    ],
                    spacing=1,
                    expand=True,
                ),
                ft.Container(
                    padding=ft.Padding.symmetric(
                        horizontal=9,
                        vertical=4,
                    ),
                    bgcolor="white",
                    border_radius=12,
                    content=ft.Text(
                        f"{len(parametros)} campos",
                        size=10,
                        color=color_caldera,
                        weight=ft.FontWeight.BOLD,
                    ),
                ),
                boton_expandir,
            ],
            spacing=9,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        encabezado_interactivo = ft.Container(
            padding=10,
            ink=True,
            border_radius=11,
            on_click=(
                lambda _, numero=caldera: 
                alternar_seccion_caldera(numero)
            ),
            content=encabezado_tarjeta,
        )

        tarjeta = ft.Container(
            bgcolor=fondo,
            border=ft.Border.all(
                1,
                color_borde,
            ),
            border_radius=11,
            content=ft.Column(
                controls=[
                    encabezado_interactivo,
                    contenido_campos,
                ],
                spacing=0,
                tight=True,
            ),
        )

        paneles_caldera[caldera] = tarjeta

    calderas_construidas = set(paneles_caldera.keys())
    calderas_esperadas = set(CALDERAS)

    if calderas_construidas != calderas_esperadas:
        faltantes = sorted(
            calderas_esperadas - calderas_construidas
        )

        raise RuntimeError(
            "No fue posible construir las tarjetas de las "
            f"siguientes calderas: {faltantes}."
        )

    # ========================================================
    # OBSERVACIONES MEDIANTE BOTÓN Y DIÁLOGO
    # ========================================================

    # Estado independiente del TextField. Esta es la fuente de verdad.
    estado_observacion = {"valor": ""}

    campo_observaciones = ft.TextField(
        label="Observaciones del registro",
        hint_text="Novedades, desviaciones o acciones realizadas...",
        multiline=True,
        min_lines=5,
        max_lines=8,
        max_length=1000,
        width=620,
        border_radius=10,
        border_color="#CBD5E1",
        focused_border_color=COLOR_PRIMARIO,
        focused_border_width=2,
        bgcolor="white",
        color="#334155",
        text_size=13,
        label_style=ft.TextStyle(color="#475569"),
        content_padding=ft.Padding.all(14),
    )

    texto_estado_observaciones = ft.Text(
        "Sin observaciones",
        size=11,
        color="#64748B",
    )

    icono_estado_observaciones = ft.Icon(
        ft.Icons.NOTES_ROUNDED,
        color=COLOR_PRIMARIO,
        size=18,
    )

    def actualizar_estado_observaciones():
        observacion = estado_observacion["valor"].strip()

        if observacion:
            texto_estado_observaciones.value = (
                f"Observación guardada · {len(observacion)} caracteres"
            )
            texto_estado_observaciones.color = COLOR_EXITO
            icono_estado_observaciones.name = ft.Icons.CHECK_CIRCLE_ROUNDED
            icono_estado_observaciones.color = COLOR_EXITO
        else:
            texto_estado_observaciones.value = "Sin observaciones"
            texto_estado_observaciones.color = "#64748B"
            icono_estado_observaciones.name = ft.Icons.NOTES_ROUNDED
            icono_estado_observaciones.color = COLOR_PRIMARIO

    def cancelar_observacion(dialogo):
        campo_observaciones.value = estado_observacion["valor"]
        cerrar_dialogo(dialogo)

    def guardar_observacion(dialogo):
        observacion = (campo_observaciones.value or "").strip()

        if len(observacion) > 1000:
            mostrar_mensaje(
                "Las observaciones admiten máximo 1000 caracteres.",
                COLOR_ERROR,
            )
            return

        estado_observacion["valor"] = observacion
        campo_observaciones.value = observacion
        actualizar_estado_observaciones()

        # BorradorRegistro es inmutable, por eso se reemplaza cada objeto
        # conservando su identificador y sus valores.
        for indice, borrador_existente in enumerate(borradores):
            borradores[indice] = BorradorRegistro(
                id_temporal=borrador_existente.id_temporal,
                fecha=borrador_existente.fecha,
                hora=borrador_existente.hora,
                usuario_registro=borrador_existente.usuario_registro,
                valores=dict(borrador_existente.valores),
                observaciones=observacion,
            )

        cerrar_dialogo(dialogo)
        actualizar_lista_borradores()
        page.update()

    def abrir_observaciones(_):
        campo_observaciones.value = estado_observacion["valor"]

        dialogo_observaciones = ft.AlertDialog(
            modal=True,
            bgcolor="white",
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.NOTES_ROUNDED, color=COLOR_PRIMARIO),
                    ft.Text(
                        "Observaciones",
                        weight=ft.FontWeight.BOLD,
                        color=COLOR_TITULO,
                    ),
                ],
                spacing=8,
            ),
            content=ft.Container(
                width=620,
                bgcolor="white",
                content=campo_observaciones,
            ),
            actions=[
                ft.OutlinedButton(
                    "Cancelar",
                    on_click=lambda _: cancelar_observacion(
                        dialogo_observaciones
                    ),
                ),
                ft.ElevatedButton(
                    "Guardar observación",
                    icon=ft.Icons.SAVE_OUTLINED,
                    bgcolor=COLOR_PRIMARIO,
                    color="white",
                    on_click=lambda _: guardar_observacion(
                        dialogo_observaciones
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        mostrar_dialogo(dialogo_observaciones)

    boton_observaciones = ft.OutlinedButton(
        "Observaciones",
        icon=ft.Icons.ADD_COMMENT_OUTLINED,
        on_click=abrir_observaciones,
        style=ft.ButtonStyle(
            color={
                ft.ControlState.DEFAULT: COLOR_PRIMARIO,
                ft.ControlState.HOVERED: COLOR_PRIMARIO,
                ft.ControlState.PRESSED: COLOR_PRIMARIO,
            },
            bgcolor={
                ft.ControlState.DEFAULT: "white",
                ft.ControlState.HOVERED: "#EFF6FF",
                ft.ControlState.PRESSED: "#DBEAFE",
            },
            side={
                ft.ControlState.DEFAULT: ft.BorderSide(1, "#CBD5E1"),
                ft.ControlState.HOVERED: ft.BorderSide(1, "#93C5FD"),
                ft.ControlState.PRESSED: ft.BorderSide(1, COLOR_PRIMARIO),
            },
            padding=ft.Padding.symmetric(horizontal=13, vertical=9),
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
    )

    tarjeta_observaciones = ft.Container(
        padding=10,
        bgcolor="#F8FAFC",
        border=ft.Border.all(
            1,
            COLOR_BORDE,
        ),
        border_radius=10,
        content=ft.Column(
            controls=[
                boton_observaciones,
                ft.Row(
                    controls=[
                        icono_estado_observaciones,
                        texto_estado_observaciones,
                    ],
                    spacing=5,
                    vertical_alignment=(
                        ft.CrossAxisAlignment.CENTER
                    ),
                ),
            ],
            spacing=8,
            tight=True,
            horizontal_alignment=(
                ft.CrossAxisAlignment.START
            ),
        ),
    )

    # ========================================================
    # ESTADO Y BOTONES GENERALES
    # ========================================================

    mensaje_estado = ft.Text(
        "",
        visible=False,
        size=13,
    )

    estado_edicion = ft.Container(
        visible=False,
        padding=10,
        bgcolor="#EFF6FF",
        border=ft.Border.all(
            1,
            "#BFDBFE",
        ),
        border_radius=8,
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.EDIT_NOTE_ROUNDED,
                    color="#1D4ED8",
                    size=19,
                ),
                ft.Text(
                    "",
                    size=12,
                    color="#1D4ED8",
                    weight=ft.FontWeight.BOLD,
                ),
            ],
            spacing=7,
        ),
    )

    columna_borradores = ft.Column(
        spacing=8,
    )

    estado_vacio = ft.Container(
        padding=18,
        bgcolor="#F8FAFC",
        border=ft.Border.all(
            1,
            COLOR_BORDE,
        ),
        border_radius=9,
        content=ft.Text(
            "Aún no hay borradores. Completa las dos "
            "calderas y guarda el registro.",
            size=13,
            color="#475569",
        ),
    )

    boton_enviar = ft.ElevatedButton(
        "Enviar borradores seleccionados",
        icon=ft.Icons.SEND_ROUNDED,
        bgcolor=COLOR_PRIMARIO,
        color="white",
        disabled=True,
    )

    # ========================================================
    # LIMPIEZA Y BÚSQUEDA
    # ==================================

    def limpiar_captura():
        nonlocal id_borrador_en_edicion

        for control in campos.values():
            control.value = ""

        campo_observaciones.value = ""
        estado_observacion["valor"] = ""
        id_borrador_en_edicion = None

        actualizar_estado_observaciones()

        if isinstance(estado_edicion.content, ft.Row):
            estado_edicion.content.controls[1].value = ""

        estado_edicion.visible = False

        boton_guardar.text = (
            "Guardar registro como borrador"
        )
        boton_guardar.icon = ft.Icons.DRAFTS_OUTLINED

        for caldera in CALDERAS:
            secciones_expandidas[caldera] = False

            contenidos_caldera[caldera].visible = False

            botones_expansion_caldera[caldera].icon = (
                ft.Icons.EXPAND_MORE_ROUNDED
            )

            textos_resumen_caldera[caldera].value = (
                "Sin diligenciar"
            )

    def buscar_borrador(
        id_temporal: str,
    ) -> BorradorRegistro | None:
        return next(
            (
                borrador
                for borrador in borradores
                if borrador.id_temporal == id_temporal
            ),
            None,
        )

    def ver_borrador(id_temporal: str):
        borrador = buscar_borrador(id_temporal)

        if borrador is None:
            mostrar_mensaje(
                "El borrador ya no esta disponible.",
                COLOR_ERROR,
            )
            return

        desviaciones = obtener_desviaciones(
            borrador.valores
        )

        def crear_fila_detalle(
                etiqueta: str,
                valor: object,
                unidad: str = "",
            ) -> ft.Container:
            texto_valor = str(valor)

            if unidad:
                texto_valor = f"{texto_valor} {unidad}"

            return ft.Container(
                padding=ft.Padding.symmetric(
                    horizontal=12,
                    vertical=9,
                ),
                bgcolor="white",
                border=ft.Border.all(
                    1,
                    COLOR_BORDE,
                ),
                border_radius=8,
                content=ft.Row(
                    controls=[
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
                    alignment=(
                        ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    vertical_alignment=(
                        ft.CrossAxisAlignment.CENTER
                    ),
                ),
            )
        tarjetas_detalle: list[ft.Container] = []

        for caldera in CALDERAS:
            color_caldera = (
                COLOR_CALDERA_1
                if caldera == 1
                else COLOR_CALDERA_2
            )

            fondo_caldera = (
                FONDO_CALDERA_1
                if caldera == 1
                else FONDO_CALDERA_2
            )

            borde_caldera = (
                BORDE_CALDERA_1
                if caldera == 1
                else BORDE_CALDERA_2
            )

            tarjeta_caldera = ft.Container(
                padding=14,
                bgcolor=fondo_caldera,
                border=ft.Border.all(
                    1,
                    borde_caldera,
                ),
                border_radius=12,
                col={
                    "xs": 12,
                    "sm": 12,
                    "md": 6,
                    "lg": 6,
                },
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Container(
                                    width=38,
                                    height=38,
                                    alignment=ft.Alignment.CENTER,
                                    bgcolor="white",
                                    border=ft.Border.all(
                                        1,
                                        borde_caldera,
                                    ),
                                    border_radius=9,
                                    content=ft.Icon(
                                        (
                                            ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED
                                        ),
                                        color=color_caldera,
                                        size=22,
                                    ),
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            (
                                                f"PURGA CALDERA "
                                                f"#{caldera}"
                                            ),
                                            size=14,
                                            weight=(
                                                ft.FontWeight.BOLD
                                            ),
                                            color=color_caldera,
                                        ),
                                        ft.Text(
                                            "Informacion registrada",
                                            size=11,
                                            color="#64748B",
                                        ),
                                    ],
                                    spacing=1,
                                ),
                            ],
                            spacing=9,
                            vertical_alignment=(
                                ft.CrossAxisAlignment.CENTER
                            ),
                        ),
                        crear_fila_detalle(
                            "pH",
                            borrador.valores[
                                f"purga_{caldera}_ph"
                            ],
                            "UN",
                        ),
                        crear_fila_detalle(
                            "Alcalinidad M",
                            borrador.valores[
                                (
                                    f"purga_{caldera}"
                                    "_alcalinidad_m"
                                )
                            ],
                            "ppm",
                        ),
                        crear_fila_detalle(
                            "Color",
                            borrador.valores[
                                f"purga_{caldera}_color"
                            ],
                        ),
                        crear_fila_detalle(
                            "Soda adicionada",
                            borrador.valores[
                                f"purga_{caldera}_soda_g"
                            ],
                            "g",
                        ),
                    ],
                    spacing=8,
                    tight=True,
                ),
            )

            tarjetas_detalle.append(tarjeta_caldera)

        if desviaciones:
            bloque_control = ft.Container(
                padding=12,
                bgcolor="#FFF7ED",
                border=ft.Border.all(
                    1,
                    "#FED7AA",
                ),
                border_radius=10,
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.WARNING_AMBER_ROUNDED,
                                    color=COLOR_ALERTA,
                                    size=20,
                                ),
                                ft.Text(
                                    "DESVIACIONES DETECTADAS",
                                    size=12,
                                    color=COLOR_ALERTA,
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ],
                            spacing=7,
                        ),
                        *[
                            ft.Text(
                                f"• {desviacion}",
                                size=12,
                                color="#9A3412",
                            )
                            for desviacion in desviaciones
                        ],
                    ],
                    spacing=6,
                    tight=True,
                ),
            )
        else:
            bloque_control = ft.Container(
                padding=12,
                bgcolor="#F0FDF4",
                border=ft.Border.all(
                    1,
                    "#BBF7D0",
                ),
                border_radius=10,
                content=ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE_ROUNDED,
                            color=COLOR_EXITO,
                            size=20,
                        ),
                        ft.Text(
                            (
                                "Valores dentro de los "
                                "controles definidos."
                            ),
                            size=12,
                            color=COLOR_EXITO,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=7,
                ),
            )

        observacion_mostrada = (
            borrador.observaciones
            or "Sin observaciones."
        )

        dialogo_vista = ft.AlertDialog(
            modal=True,
            bgcolor="white",
            title=ft.Container(
                padding=ft.Padding.only(
                    bottom=5,
                ),
                content=ft.Row(
                    controls=[
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
                            controls=[
                                ft.Text(
                                    "Vista previa del borrador",
                                    size=18,
                                    color=COLOR_PRIMARIO,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(
                                    (
                                        "Revisa la informacion "
                                        "antes de enviarla."
                                    ),
                                    size=12,
                                    color="#64748B",
                                ),
                            ],
                            spacing=1,
                        ),
                    ],
                    spacing=10,
                ),
            ),
            content=ft.Container(
                width=760,
                height=540,
                bgcolor="white",
                content=ft.Column(
                    controls=[
                        ft.Container(
                            padding=12,
                            bgcolor="#F8FAFC",
                            border=ft.Border.all(
                                1,
                                COLOR_BORDE,
                            ),
                            border_radius=10,
                            content=ft.ResponsiveRow(
                                controls=[
                                    ft.Container(
                                        col={
                                            "xs": 12,
                                            "sm": 6,
                                            "md": 4,
                                        },
                                        content=ft.Row(
                                            controls=[
                                                ft.Icon(
                                                    (
                                                        ft.Icons.CALENDAR_MONTH_ROUNDED
                                                    ),
                                                    color=COLOR_PRIMARIO,
                                                    size=18,
                                                ),
                                                ft.Column(
                                                    controls=[
                                                        ft.Text(
                                                            "FECHA",
                                                            size=10,
                                                            color="#64748B",
                                                        ),
                                                        ft.Text(
                                                            borrador.fecha,
                                                            size=12,
                                                            color=COLOR_TITULO,
                                                            weight=(
                                                                ft.FontWeight.BOLD
                                                            ),
                                                        ),
                                                    ],
                                                    spacing=0,
                                                ),
                                            ],
                                            spacing=7,
                                        ),
                                    ),
                                    ft.Container(
                                        col={
                                            "xs": 12,
                                            "sm": 6,
                                            "md": 4,
                                        },
                                        content=ft.Row(
                                            controls=[
                                                ft.Icon(
                                                    (
                                                        ft.Icons.ACCESS_TIME_ROUNDED
                                                    ),
                                                    color=COLOR_PRIMARIO,
                                                    size=18,
                                                ),
                                                ft.Column(
                                                    controls=[
                                                        ft.Text(
                                                            "HORA",
                                                            size=10,
                                                            color="#64748B",
                                                        ),
                                                        ft.Text(
                                                            borrador.hora,
                                                            size=12,
                                                            color=COLOR_TITULO,
                                                            weight=(
                                                                ft.FontWeight.BOLD
                                                            ),
                                                        ),
                                                    ],
                                                    spacing=0,
                                                ),
                                            ],
                                            spacing=7,
                                        ),
                                    ),
                                    ft.Container(
                                        col={
                                            "xs": 12,
                                            "sm": 12,
                                            "md": 4,
                                        },
                                        content=ft.Row(
                                            controls=[
                                                ft.Icon(
                                                    (
                                                        ft.Icons.PERSON_OUTLINE_ROUNDED
                                                    ),
                                                    color=COLOR_PRIMARIO,
                                                    size=18,
                                                ),
                                                ft.Column(
                                                    controls=[
                                                        ft.Text(
                                                            "USUARIO",
                                                            size=10,
                                                            color="#64748B",
                                                        ),
                                                        ft.Text(
                                                            (
                                                                borrador.usuario_registro
                                                            ),
                                                            size=12,
                                                            color=COLOR_TITULO,
                                                            weight=(
                                                                ft.FontWeight.BOLD
                                                            ),
                                                        ),
                                                    ],
                                                    spacing=0,
                                                ),
                                            ],
                                            spacing=7,
                                        ),
                                    ),
                                ],
                                spacing=8,
                                run_spacing=8,
                            ),
                        ),
                        ft.ResponsiveRow(
                            controls=tarjetas_detalle,
                            spacing=12,
                            run_spacing=12,
                        ),
                        ft.Container(
                            padding=12,
                            bgcolor="#F8FAFC",
                            border=ft.Border.all(
                                1,
                                COLOR_BORDE,
                            ),
                            border_radius=10,
                            content=ft.Column(
                                controls=[
                                    ft.Row(
                                        controls=[
                                            ft.Icon(
                                                (
                                                    ft.Icons.COMMENT_OUTLINED
                                                ),
                                                color=COLOR_PRIMARIO,
                                                size=19,
                                            ),
                                            ft.Text(
                                                "OBSERVACIONES",
                                                size=12,
                                                color=COLOR_TITULO,
                                                weight=(
                                                    ft.FontWeight.BOLD
                                                ),
                                            ),
                                        ],
                                        spacing=7,
                                    ),
                                    ft.Text(
                                        observacion_mostrada,
                                        size=12,
                                        color="#475569",
                                    ),
                                ],
                                spacing=7,
                                tight=True,
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
                        cerrar_dialogo(dialogo_vista),
                        cargar_borrador(id_temporal),
                    ),
                    style=ft.ButtonStyle(
                        color=COLOR_PRIMARIO,
                        side=ft.BorderSide(
                            1,
                            COLOR_PRIMARIO,
                        ),
                    ),
                ),
                ft.ElevatedButton(
                    "Cerrar",
                    icon=ft.Icons.CLOSE_ROUNDED,
                    bgcolor=COLOR_PRIMARIO,
                    color="white",
                    on_click=lambda _: cerrar_dialogo(
                        dialogo_vista
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        mostrar_dialogo(dialogo_vista)
    

    
    
    # ========================================================
    # GUARDADO Y EDICIÓN DE BORRADORES
    # ========================================================

    def actualizar_lista_borradores():
        columna_borradores.controls.clear()
        seleccionados = 0

        borradores_ordenados = sorted(
            borradores,
            key=lambda item: (
                item.fecha,
                item.hora,
            ),
        )

        for borrador in borradores_ordenados:
            checkbox = selecciones[borrador.id_temporal]

            seleccionados += int(bool(checkbox.value))

            desviaciones = obtener_desviaciones(
                borrador.valores
            )

            detalle = (
                f"{len(desviaciones)} desviación(es) detectada(s)."
                if desviaciones
                else "Valores dentro de los controles."
            )

            color_detalle = (
                COLOR_ALERTA
                if desviaciones
                else COLOR_EXITO
            )

            observacion_mostrada = (
                borrador.observaciones
                or "Sin observaciones"
            )

            columna_borradores.controls.append(
                ft.Container(
                    padding=12,
                    bgcolor="white",
                    border=ft.Border.all(
                        1,
                        COLOR_BORDE,
                    ),
                    border_radius=9,
                    content=ft.Row(
                        [
                            checkbox,
                            ft.Column(
                                [
                                    ft.Text(
                                        f"Registro del "
                                        f"{borrador.fecha} "
                                        f"a las {borrador.hora}",
                                        weight=ft.FontWeight.BOLD,
                                        color=COLOR_TITULO,
                                    ),
                                    ft.Text(
                                        f"Usuario: "
                                        f"{borrador.usuario_registro} "
                                        f"| {detalle}",
                                        size=12,
                                        color=color_detalle,
                                    ),
                                    ft.Text(
                                        f"Observaciones: "
                                        f"{observacion_mostrada}",
                                        size=11,
                                        color="#64748B",
                                        max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ],
                                spacing=3,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.VISIBILITY_ROUNDED,
                                tooltip="Ver borrador",
                                icon_color=COLOR_PRIMARIO,
                                on_click=(
                                    lambda _,
                                    rid=borrador.id_temporal:
                                    ver_borrador(rid)
                                ),
                                style=ft.ButtonStyle(
                                    bgcolor={
                                        ft.ControlState.DEFAULT: (
                                            "#EFF6FF"
                                        ),
                                        ft.ControlState.HOVERED: (
                                            "#DBEAFE"
                                        ),
                                    },
                                    shape=ft.CircleBorder(),
                                ),
                            ),
                            ft.OutlinedButton(
                                "Editar",
                                icon=ft.Icons.EDIT_OUTLINED,
                                on_click=(
                                    lambda _,
                                    rid=borrador.id_temporal:
                                    cargar_borrador(rid)
                                ),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                tooltip="Eliminar borrador",
                                icon_color=COLOR_ERROR,
                                on_click=(
                                    lambda _,
                                    rid=borrador.id_temporal:
                                    eliminar_borrador(rid)
                                ),
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=(
                            ft.CrossAxisAlignment.CENTER
                        ),
                    ),
                )
            )

        estado_vacio.visible = not borradores
        boton_enviar.disabled = seleccionados == 0
        page.update()

    def cargar_borrador(id_temporal: str):
        nonlocal id_borrador_en_edicion
        nonlocal fecha_fijada
        nonlocal hora_fijada

        borrador = buscar_borrador(id_temporal)

        if borrador is None:
            mostrar_mensaje(
                "El borrador ya no está disponible.",
                COLOR_ERROR,
            )
            return

        id_borrador_en_edicion = id_temporal

        fecha_fijada = borrador.fecha
        campo_fecha.value = borrador.fecha

        selector_fecha.value = datetime.datetime.combine(
            datetime.date.fromisoformat(
                borrador.fecha
            ),
            datetime.time.min,
        )

        hora_fijada = None

        momento_actual = datetime.datetime.now()
        campo_hora.value = momento_actual.strftime(
            "%H:%M:%S"
        )
        selector_hora.value = momento_actual.time()

        boton_ahora.visible = True

        for nombre, valor in borrador.valores.items():
            if nombre in campos:
                campos[nombre].value = str(valor)

        estado_observacion["valor"] = (
            borrador.observaciones or ""
        ).strip()
        campo_observaciones.value = estado_observacion["valor"]
        actualizar_estado_observaciones()

        boton_guardar.text = "Actualizar borrador"
        boton_guardar.icon = ft.Icons.SAVE_AS_OUTLINED

        if isinstance(estado_edicion.content, ft.Row):
            estado_edicion.content.controls[1].value = (
                "Estás editando un borrador existente."
            )

        estado_edicion.visible = True
        mensaje_estado.visible = False

        for caldera in CALDERAS:
            secciones_expandidas[caldera] = True
            actualizar_tarjeta_caldera(
                caldera,
                actualizar_pagina=False,
            )
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

        mostrar_mensaje(
            "Borrador eliminado.",
            COLOR_ERROR,
        )

    def guardar_o_actualizar_borrador(
        fecha: str,
        hora: str,
        valores: dict[str, object],
    ):
        nonlocal id_borrador_en_edicion

        observaciones = estado_observacion["valor"].strip()

        if id_borrador_en_edicion is None:
            id_temporal = uuid4().hex

            borrador = BorradorRegistro(
                id_temporal=id_temporal,
                fecha=fecha,
                hora=hora,
                usuario_registro=(
                    usuario_logueado.strip()
                ),
                valores=dict(valores),
                observaciones=observaciones,
            )

            borradores.append(borrador)

            selecciones[id_temporal] = ft.Checkbox(
                label="Incluir",
                value=True,
                on_change=lambda _: (
                    actualizar_lista_borradores()
                ),
            )

            mensaje = (
                "Registro guardado como borrador "
                "para revisión."
            )
        else:
            anterior = buscar_borrador(
                id_borrador_en_edicion
            )

            if anterior is None:
                id_borrador_en_edicion = None

                mostrar_mensaje(
                    "No fue posible actualizar "
                    "el borrador.",
                    COLOR_ERROR,
                )
                return

            indice = borradores.index(anterior)

            borradores[indice] = BorradorRegistro(
                id_temporal=anterior.id_temporal,
                fecha=fecha,
                hora=hora,
                usuario_registro=(
                    usuario_logueado.strip()
                ),
                valores=dict(valores),
                observaciones=observaciones,
            )

            mensaje = (
                "Borrador actualizado correctamente."
            )

        limpiar_captura()
        actualizar_lista_borradores()
        mostrar_mensaje(mensaje, COLOR_EXITO)

    def guardar_borrador_confirmado(
        dialogo,
        fecha: str,
        hora: str,
        valores: dict[str, object],
    ):
        cerrar_dialogo(dialogo)

        guardar_o_actualizar_borrador(
            fecha,
            hora,
            valores,
        )

    def guardar_borrador(_):
        mensaje_estado.visible = False

        try:
            valores = validar_registro(
                {
                    nombre: control.value or ""
                    for nombre, control in campos.items()
                }
            )
        except ValueError as ex:
            mostrar_mensaje(
                str(ex),
                COLOR_ERROR,
            )
            return

        fecha = obtener_fecha()
        hora = obtener_hora()
        desviaciones = obtener_desviaciones(valores)

        if not desviaciones:
            guardar_o_actualizar_borrador(
                fecha,
                hora,
                valores,
            )
            return

        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                f"{len(desviaciones)} valor(es) "
                "fuera del control",
                color="#991B1B",
                weight=ft.FontWeight.BOLD,
            ),
            content=ft.Container(
                width=520,
                height=280,
                content=ft.Column(
                    [
                        ft.Text(
                            "Puedes corregir los valores "
                            "o conservarlos en el borrador.",
                            size=13,
                            color="#475569",
                        ),
                        *[
                            ft.Container(
                                padding=9,
                                bgcolor="#FEF2F2",
                                border=ft.Border.all(
                                    1,
                                    "#FECACA",
                                ),
                                border_radius=8,
                                content=ft.Text(
                                    item,
                                    color="#7F1D1D",
                                    size=13,
                                ),
                            )
                            for item in desviaciones
                        ],
                    ],
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                ),
            ),
            actions=[
                ft.OutlinedButton(
                    "Volver a revisar",
                    on_click=lambda _: (
                        cerrar_dialogo(dialogo)
                    ),
                ),
                ft.ElevatedButton(
                    "Conservar como borrador",
                    icon=ft.Icons.DRAFTS_OUTLINED,
                    bgcolor=COLOR_ALERTA,
                    color="white",
                    on_click=lambda _: (
                        guardar_borrador_confirmado(
                            dialogo,
                            fecha,
                            hora,
                            valores,
                        )
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        mostrar_dialogo(dialogo)

    boton_guardar = ft.ElevatedButton(
        "Guardar registro como borrador",
        icon=ft.Icons.DRAFTS_OUTLINED,
        bgcolor=COLOR_PRIMARIO,
        color="white",
        on_click=guardar_borrador,
        style=ft.ButtonStyle(
            padding=ft.Padding.symmetric(
                horizontal=16,
                vertical=11,
            ),
            shape=ft.RoundedRectangleBorder(
                radius=8,
            ),
        ),
    )

    # ========================================================
    # ENVÍO A SQL SERVER
    # ========================================================

    def completar_envio(
        ids_seleccionados: list[str],
    ):
        seleccionados = [
            borrador
            for borrador in borradores
            if borrador.id_temporal
            in ids_seleccionados
        ]

        boton_enviar.disabled = True
        page.update()

        try:
            ids_bd = insertar_borradores_bd(
                seleccionados
            )
        except ValueError as ex:
            mostrar_mensaje(
                str(ex),
                COLOR_ERROR,
            )
        except pyodbc.Error:
            logging.exception(
                "SQL Server rechazó el envío "
                "del Formulario 3."
            )
            mostrar_mensaje(
                "No fue posible enviar los registros. "
                "Verifica la conexión, la tabla y sus "
                "columnas en SQL Server.",
                COLOR_ERROR,
            )
        except RuntimeError as ex:
            logging.exception(
                "SQL Server no confirmó "
                "el Formulario 3."
            )
            mostrar_mensaje(
                str(ex),
                COLOR_ERROR,
            )
        else:
            borradores[:] = [
                borrador
                for borrador in borradores
                if borrador.id_temporal
                not in ids_seleccionados
            ]

            for id_temporal in ids_seleccionados:
                selecciones.pop(
                    id_temporal,
                    None,
                )

            actualizar_lista_borradores()

            mostrar_mensaje(
                f"Se enviaron {len(ids_bd)} "
                "registro(s) a SQL Server. "
                "Identificadores: "
                f"{', '.join(map(str, ids_bd))}.",
                COLOR_EXITO,
            )
        finally:
            actualizar_lista_borradores()

    def confirmar_envio(
        dialogo,
        ids_seleccionados: list[str],
    ):
        cerrar_dialogo(dialogo)
        completar_envio(ids_seleccionados)

    def enviar_borradores(_):
        ids_seleccionados = [
            borrador.id_temporal
            for borrador in borradores
            if selecciones[
                borrador.id_temporal
            ].value
        ]

        if not ids_seleccionados:
            mostrar_mensaje(
                "Selecciona al menos un borrador "
                "para enviar.",
                COLOR_ERROR,
            )
            return

        seleccionados = [
            borrador
            for borrador in borradores
            if borrador.id_temporal
            in ids_seleccionados
        ]

        desviaciones = sum(
            len(
                obtener_desviaciones(
                    borrador.valores
                )
            )
            for borrador in seleccionados
        )

        resumen = ft.Column(
            controls=[
                ft.Container(
                    padding=9,
                    bgcolor="#F8FAFC",
                    border_radius=8,
                    content=ft.Text(
                        (
                            f"{borrador.fecha} "
                            f"{borrador.hora} | "
                            f"Usuario: "
                            f"{borrador.usuario_registro} | "
                            f"pH C1: "
                            f"{borrador.valores['purga_1_ph']} | "
                            f"pH C2: "
                            f"{borrador.valores['purga_2_ph']} | "
                            f"Observaciones: "
                            f"{borrador.observaciones}"
                        )
                        if borrador.observaciones
                        else (
                            f"{borrador.fecha} "
                            f"{borrador.hora} | "
                            f"Usuario: "
                            f"{borrador.usuario_registro} | "
                            f"pH C1: "
                            f"{borrador.valores['purga_1_ph']} | "
                            f"pH C2: "
                            f"{borrador.valores['purga_2_ph']} | "
                            "Observaciones: Sin observaciones"
                        ),
                        size=12,
                    ),
                )
                for borrador in seleccionados
            ],
            spacing=6,
            scroll=ft.ScrollMode.AUTO,
        )

        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Confirmar envío a SQL Server",
                color=COLOR_PRIMARIO,
                weight=ft.FontWeight.BOLD,
            ),
            content=ft.Container(
                width=620,
                height=min(
                    410,
                    150 + len(seleccionados) * 55,
                ),
                content=ft.Column(
                    [
                        ft.Text(
                            f"Se enviarán "
                            f"{len(seleccionados)} "
                            "registro(s). "
                            "Desviaciones encontradas: "
                            f"{desviaciones}.",
                            color="#475569",
                        ),
                        resumen,
                        ft.Text(
                            "Después de confirmar, los "
                            "registros quedarán guardados "
                            "definitivamente en la base "
                            "de datos.",
                            size=12,
                            color="#64748B",
                        ),
                    ],
                    spacing=10,
                ),
            ),
            actions=[
                ft.OutlinedButton(
                    "Cancelar",
                    on_click=lambda _: (
                        cerrar_dialogo(dialogo)
                    ),
                ),
                ft.ElevatedButton(
                    "Confirmar y enviar",
                    icon=ft.Icons.CLOUD_UPLOAD_ROUNDED,
                    bgcolor=COLOR_EXITO,
                    color="white",
                    on_click=lambda _: confirmar_envio(
                        dialogo,
                        ids_seleccionados,
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        mostrar_dialogo(dialogo)

    boton_enviar.on_click = enviar_borradores

    # ========================================================
    # SALIDA
    # ========================================================

    def salir(dialogo):
        detener_formulario()
        cerrar_dialogo(dialogo)

        if on_logout is not None:
            on_logout()

    def confirmar_salida(_):
        if on_logout is None:
            return

        mensaje = (
            f"Hay {len(borradores)} borrador(es) "
            "sin enviar. Se perderán al salir."
            if borradores
            else "Volverás al menú principal."
        )

        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.WARNING_AMBER_ROUNDED,
                        color="#DC2626",
                        size=28,
                    ),
                    ft.Text(
                        "¿Seguro que deseas salir?",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color="#DC2626",
                    ),
                ],
                spacing=8,
            ),
            content=ft.Text(
                mensaje,
                size=13,
                color="#334155",
            ),
            actions=[
                ft.OutlinedButton(
                    "Cancelar",
                    on_click=lambda _: (
                        cerrar_dialogo(dialogo)
                    ),
                ),
                ft.ElevatedButton(
                    "Sí, continuar y salir",
                    on_click=lambda _: salir(dialogo),
                    bgcolor="#DC2626",
                    color="white",
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        mostrar_dialogo(dialogo)

    # ========================================================
    # ENCABEZADO Y ACTUALIZACIÓN DEL RELOJ
    # ========================================================

    marquee = ft.Text(
        "",
        size=16,
        color="#F8FAFC",
        weight=ft.FontWeight.BOLD,
        no_wrap=True,
    )

    def animar_marquee():
        texto = (
            " CONTROL DE PURGAS DE CALDERA • "
            "BORRADORES DE REGISTRO • "
            f"RESPONSABLE: {nombre_completo} • "
            f"USUARIO: {usuario_logueado} • "
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
                    "Se detuvo la animación del "
                    "encabezado del Formulario 3."
                )
                break

            time.sleep(0.08)

    def actualizar_fecha_hora():
        while formulario_activo:
            try:
                momento = datetime.datetime.now()

                if fecha_fijada is None:
                    campo_fecha.value = (
                        momento.date().isoformat()
                    )

                if hora_fijada is None:
                    campo_hora.value = momento.strftime(
                        "%H:%M:%S"
                    )

                txt_reloj.value = momento.strftime(
                    "%H:%M:%S"
                )

                if interfaz_lista:
                    txt_reloj.update()

                    if fecha_fijada is None:
                        campo_fecha.update()

                    if hora_fijada is None:
                        campo_hora.update()

            except Exception:
                logging.exception(
                    "Se detuvo la actualización de "
                    "fecha y hora del Formulario 3."
                )
                break

            time.sleep(1)

    ruta_logo = os.path.join(
        os.path.dirname(
            os.path.abspath(__file__)
        ),
        "assets",
        "logo-crystal.png",
    )

    logo = (
        ft.Image(
            src="logo-crystal.png",
            width=180,
            height=60,
            fit=ft.BoxFit.CONTAIN,
        )
        if os.path.isfile(ruta_logo)
        else ft.Text(
            "CRYSTAL S.A.S.",
            size=20,
            weight=ft.FontWeight.BOLD,
            color=COLOR_PRIMARIO,
        )
    )

    encabezado = ft.Container(
        bgcolor="white",
        border_radius=15,
        padding=16,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK_ROUNDED,
                            icon_color="white",
                            bgcolor=COLOR_PRIMARIO,
                            tooltip="Volver al menú",
                            on_click=confirmar_salida,
                        ),
                        logo,
                        ft.Container(
                            expand=True,
                            height=62,
                            bgcolor=COLOR_TITULO,
                            border_radius=10,
                            padding=12,
                            alignment=ft.Alignment.CENTER_LEFT,
                            content=marquee,
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=(
                        ft.CrossAxisAlignment.CENTER
                    ),
                ),
                ft.Divider(),
                ft.Column(
                    [
                        ft.Text(
                            "CONTROL DE PURGAS DE CALDERA",
                            size=22,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_PRIMARIO,
                        ),
                        ft.Text(
                            f"{nombre_completo} "
                            f"({usuario_logueado})",
                            color="#64748B",
                            size=12,
                        ),
                    ],
                    spacing=4,
                ),
            ],
            spacing=8,
        ),
    )

    # ========================================================
    # DISEÑO PRINCIPAL
    # ========================================================

    introduccion = ft.Container(
        padding=12,
        bgcolor="#EFF6FF",
        border=ft.Border.all(
            1,
            "#BFDBFE",
        ),
        border_radius=10,
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.INFO_OUTLINE_ROUNDED,
                    color=COLOR_PRIMARIO,
                    size=20,
                ),
                ft.Text(
                    "Selecciona una sección para desplegar "
                    "sus campos. Los valores permanecen "
                    "guardados al contraer cada tarjeta.",
                    color=COLOR_PRIMARIO,
                    size=12,
                    expand=True,
                ),
            ],
            spacing=9,
        ),
    )

    panel_registro = ft.Container(
        padding=16,
        bgcolor="white",
        border=ft.Border.all(
            1,
            COLOR_BORDE,
        ),
        border_radius=14,
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.GRID_VIEW_ROUNDED,
                            color=COLOR_PRIMARIO,
                            size=21,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "SECCIONES DEL REGISTRO",
                                    size=17,
                                    weight=ft.FontWeight.BOLD,
                                    color=COLOR_PRIMARIO,
                                ),
                                ft.Text(
                                    "Presiona una tarjeta para "
                                    "expandir o contraer sus campos.",
                                    size=11,
                                    color="#64748B",
                                ),
                            ],
                            spacing=1,
                            tight=True,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=(
                        ft.CrossAxisAlignment.CENTER
                    ),
                ),
                ft.Column(
                    controls=[
                        paneles_caldera[1],
                        paneles_caldera[2],
                    ],
                    spacing=10,
                    tight=True,
                    horizontal_alignment=(
                        ft.CrossAxisAlignment.STRETCH
                    ),
                ),
                tarjeta_observaciones,
                estado_edicion,
                ft.Column(
                    controls=[
                        ft.Text(
                            "El borrador queda disponible "
                            "para revisión antes del envío.",
                            size=11,
                            color="#64748B",
                        ),
                        ft.Row(
                            controls=[boton_guardar],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ],
                    spacing=7,
                    tight=True,
                    horizontal_alignment=(
                        ft.CrossAxisAlignment.STRETCH
                    ),
                ),
            ],
            spacing=12,
            tight=True,
            horizontal_alignment=(
                ft.CrossAxisAlignment.STRETCH
            ),
        ),
    )

    panel_borradores = ft.Container(
        padding=16,
        bgcolor="white",
        border=ft.Border.all(
            1,
            COLOR_BORDE,
        ),
        border_radius=14,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.DRAFTS_OUTLINED,
                            color=COLOR_PRIMARIO,
                            size=22,
                        ),
                        ft.Text(
                            "BORRADORES PENDIENTES DE ENVÍO",
                            size=17,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_PRIMARIO,
                        ),
                    ],
                    spacing=8,
                ),
                ft.Text(
                    "Cada borrador representa un registro "
                    "completo de las dos calderas.",
                    size=12,
                    color="#475569",
                ),
                estado_vacio,
                columna_borradores,
                ft.Row(
                    [boton_enviar],
                    alignment=ft.MainAxisAlignment.END,
                ),
                mensaje_estado,
            ],
            spacing=10,
        ),
    )

    columna_principal = ft.Column(
        controls=[
            encabezado,
            barra_fecha,
            introduccion,
            panel_registro,
            panel_borradores,
        ],
        spacing=12,
        tight=True,
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=(ft.CrossAxisAlignment.STRETCH
        ),
    )

    contenedor_principal = ft.Container(
        expand=True,
        padding=10,
        bgcolor=COLOR_FONDO,
        alignment=ft.Alignment.TOP_CENTER,
        content=columna_principal,
    )

    page.add(contenedor_principal)

    interfaz_lista = True
    actualizar_estado_observaciones()
    actualizar_lista_borradores()
    page.update()

    async def posicionar_formulario_al_inicio():
        try:
            await columna_principal.scroll_to(
                offset=0,
                duration=0,
            )
        except Exception:
            logging.exception(
                "No fue posible posicionar el "
                "Formulario 3 al inicio."
            )

    page.run_task(
        posicionar_formulario_al_inicio
    )

    threading.Thread(
        target=animar_marquee,
        daemon=True,
    ).start()

    threading.Thread(
        target=actualizar_fecha_hora,
        daemon=True,
    ).start()