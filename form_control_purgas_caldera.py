import datetime
import logging
import os
import threading
import time
from decimal import Decimal, InvalidOperation

import flet as ft
import pyodbc

import conexionform


TABLA_REGISTRO = "dbo.Registro_Control_Purgas_Caldera"
TURNOS = (1, 2, 3)
CALDERAS = (1, 2)
COLOR_PRIMARIO = "#1E3A8A"
COLOR_TITULO = "#0F172A"
COLOR_BORDE = "#E2E8F0"
COLOR_TURNO = {1: "#0284C7", 2: "#EA580C", 3: "#7C3AED"}

COLUMNAS_POR_CALDERA = {
    caldera: (
        f"purga_{caldera}_ph",
        f"purga_{caldera}_alcalinidad_m",
        f"purga_{caldera}_color",
        f"purga_{caldera}_soda_g",
    )
    for caldera in CALDERAS
}
COLUMNAS_TURNO = tuple(
    columna
    for caldera in CALDERAS
    for columna in COLUMNAS_POR_CALDERA[caldera]
)
COLUMNAS_REGISTRO = (*COLUMNAS_TURNO, "entrega", "recibe", "usuario_registro")
CAMPOS_NUMERICOS = frozenset(
    columna
    for caldera in CALDERAS
    for columna in (
        f"purga_{caldera}_ph",
        f"purga_{caldera}_alcalinidad_m",
        f"purga_{caldera}_soda_g",
    )
)


def parsear_valor_numerico(texto: str, nombre: str) -> Decimal:
    texto = texto.strip().replace(",", ".")
    if not texto:
        raise ValueError(f"Completa el valor de {nombre}.")
    if any(caracter not in "0123456789." for caracter in texto):
        raise ValueError(f"{nombre} debe ser un número positivo.")

    try:
        valor = Decimal(texto)
    except InvalidOperation as ex:
        raise ValueError(f"{nombre} debe ser un número válido.") from ex

    if not valor.is_finite() or valor < 0:
        raise ValueError(f"{nombre} debe ser un número positivo.")
    if len(texto.split(".")) > 2:
        raise ValueError(f"{nombre} tiene un formato decimal inválido.")
    decimales = len(texto.partition(".")[2])
    if decimales > 2:
        raise ValueError(f"{nombre} admite máximo dos decimales.")
    digitos_enteros = len(texto.partition(".")[0].lstrip("0"))
    if digitos_enteros > 8:
        raise ValueError(f"{nombre} admite máximo ocho dígitos enteros.")
    return valor


def validar_turno(turno: int, campos: dict[str, str]) -> dict[str, object]:
    if turno not in TURNOS:
        raise ValueError("Selecciona un turno válido (1, 2 o 3).")

    valores: dict[str, object] = {}
    for caldera in CALDERAS:
        for campo, etiqueta in (
            (f"purga_{caldera}_ph", f"pH de caldera #{caldera}"),
            (
                f"purga_{caldera}_alcalinidad_m",
                f"Alcalinidad M de caldera #{caldera}",
            ),
            (f"purga_{caldera}_color", f"Color de caldera #{caldera}"),
            (f"purga_{caldera}_soda_g", f"Soda de caldera #{caldera}"),
        ):
            entrada = campos.get(campo, "").strip()
            if campo in CAMPOS_NUMERICOS:
                valores[campo] = parsear_valor_numerico(entrada, etiqueta)
            else:
                if not entrada:
                    raise ValueError(f"Completa el valor de {etiqueta}.")
                if len(entrada) > 50:
                    raise ValueError(f"{etiqueta} admite máximo 50 caracteres.")
                valores[campo] = entrada

    for campo, etiqueta in (("entrega", "Entrega"), ("recibe", "Recibe")):
        nombre = campos.get(campo, "").strip()
        if not nombre:
            raise ValueError(f"Completa el nombre de {etiqueta}.")
        if len(nombre) > 100:
            raise ValueError(f"El nombre de {etiqueta} admite máximo 100 caracteres.")
        valores[campo] = nombre

    return valores


def obtener_desviaciones(valores: dict[str, object]) -> list[str]:
    desviaciones = []
    for caldera in CALDERAS:
        ph = valores[f"purga_{caldera}_ph"]
        alcalinidad = valores[f"purga_{caldera}_alcalinidad_m"]
        if ph < Decimal("10.5") or ph > Decimal("11.5"):
            desviaciones.append(
                f"Caldera #{caldera} · pH {ph} (control 10,5–11,5)"
            )
        if alcalinidad > Decimal("500"):
            desviaciones.append(
                f"Caldera #{caldera} · Alcalinidad M {alcalinidad} "
                "(máximo 500 ppm)"
            )
    return desviaciones


def insertar_borradores_bd(
    fecha: str,
    usuario_registro: str,
    borradores: list[dict[str, object]],
) -> list[int]:
    try:
        fecha_sql = datetime.date.fromisoformat(fecha)
    except ValueError as ex:
        raise ValueError("La fecha no tiene un formato válido.") from ex
    usuario_registro = usuario_registro.strip()
    if not usuario_registro or len(usuario_registro) > 100:
        raise ValueError("El usuario de registro debe tener entre 1 y 100 caracteres.")
    if not borradores:
        raise ValueError("Selecciona al menos un turno para enviar.")

    turnos = [borrador.get("turno") for borrador in borradores]
    if (
        any(turno not in TURNOS for turno in turnos)
        or len(set(turnos)) != len(turnos)
    ):
        raise ValueError("Los borradores deben contener turnos válidos y únicos.")

    valores_borradores = []
    for borrador in borradores:
        if borrador.get("fecha") != fecha_sql.isoformat():
            raise ValueError(
                "Los borradores seleccionados deben corresponder a la fecha "
                "que se va a guardar."
            )
        try:
            hora_sql = datetime.time.fromisoformat(str(borrador.get("hora", "")))
        except ValueError as ex:
            raise ValueError("La hora de operación no tiene un formato válido.") from ex
        valores = borrador.get("valores")
        if not isinstance(valores, dict):
            raise ValueError("El borrador no contiene valores válidos.")
        valores_validados = validar_turno(
            int(borrador["turno"]),
            {campo: str(valor) for campo, valor in valores.items()},
        )
        valores_borradores.append((hora_sql, valores_validados))

    conn = None
    cursor = None
    try:
        conn = conexionform.obtener_conexion_formulario()
        cursor = conn.cursor()
        marcadores = ", ".join("?" for _ in turnos)
        cursor.execute(
            f"""
            SELECT turno
            FROM {TABLA_REGISTRO} WITH (UPDLOCK, HOLDLOCK)
            WHERE fecha = ? AND turno IN ({marcadores})
            """,
            fecha_sql.isoformat(),
            *turnos,
        )
        existentes = {int(fila[0]) for fila in cursor.fetchall()}
        if existentes:
            turnos_existentes = ", ".join(
                str(turno) for turno in sorted(existentes)
            )
            raise ValueError(
                f"Ya existe un registro para el turno {turnos_existentes} "
                f"en la fecha {fecha_sql.isoformat()}."
            )

        columnas = ("fecha", "hora", "turno", *COLUMNAS_REGISTRO)
        columnas_sql = ", ".join(columnas)
        placeholders = ", ".join("?" for _ in columnas)
        ids = []
        for borrador, (hora_sql, valores) in zip(borradores, valores_borradores):
            parametros = (
                fecha_sql.isoformat(),
                hora_sql.strftime("%H:%M:%S"),
                int(borrador["turno"]),
                *(valores[columna] for columna in COLUMNAS_TURNO),
                valores["entrega"],
                valores["recibe"],
                usuario_registro,
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
                    "SQL Server no devolvió el identificador del registro."
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
    page.bgcolor = "#F8FAFC"

    formulario_activo = True
    page.on_disconnect = lambda _: detener_formulario()

    def detener_formulario():
        nonlocal formulario_activo
        formulario_activo = False

    ahora = datetime.datetime.now()
    fecha_seleccionada = ahora.date().isoformat()
    hora_seleccionada = ahora.strftime("%H:%M:%S")
    fecha_fijada = None
    hora_fijada = None
    campo_fecha = ft.TextField(
        value=fecha_seleccionada,
        read_only=True,
        width=160,
        border_radius=8,
        border_color="#CBD5E1",
        text_size=13,
        text_style=ft.TextStyle(weight=ft.FontWeight.W_500),
    )
    campo_hora = ft.TextField(
        value=hora_seleccionada,
        read_only=True,
        width=130,
        border_radius=8,
        border_color="#CBD5E1",
        text_size=13,
        text_style=ft.TextStyle(weight=ft.FontWeight.W_500),
    )
    borradores: dict[tuple[str, int], dict[str, object]] = {}
    selecciones: dict[tuple[str, int], ft.Checkbox] = {}
    borrador_en_edicion: dict[int, tuple[str, int]] = {}
    estados_turno: dict[int, ft.Text] = {}
    campos_turno: dict[int, dict[str, ft.TextField]] = {}
    columna_borradores = ft.Column(spacing=8)
    estado_vacio = ft.Container(
        padding=14,
        bgcolor="#F8FAFC",
        border=ft.Border.all(1, COLOR_BORDE),
        border_radius=9,
        content=ft.Text(
            "Aún no hay borradores. Guarda cada turno para revisarlo y enviarlo.",
            size=13,
            color="#475569",
        ),
    )
    mensaje_estado = ft.Text("", visible=False, size=13)
    boton_enviar = ft.ElevatedButton(
        "Enviar turnos seleccionados",
        icon=ft.Icons.SEND_ROUNDED,
        bgcolor=COLOR_PRIMARIO,
        color="white",
        disabled=True,
    )

    def mostrar_dialogo(dialogo):
        if hasattr(page, "show_dialog"):
            page.show_dialog(dialogo)
        else:
            page.open(dialogo)

    def cerrar_dialogo(dialogo):
        if hasattr(page, "pop_dialog"):
            page.pop_dialog()
        elif hasattr(page, "close"):
            page.close(dialogo)
        elif page.dialog is not None:
            page.dialog.open = False
            page.update()

    def cambiar_fecha(_):
        nonlocal fecha_fijada, fecha_seleccionada
        if selector_fecha.value:
            fecha_fijada = selector_fecha.value.strftime("%Y-%m-%d")
            fecha_seleccionada = fecha_fijada
            campo_fecha.value = fecha_seleccionada
            boton_ahora.visible = True
            page.update()

    def cambiar_hora(_):
        nonlocal hora_fijada, hora_seleccionada
        if selector_hora.value:
            hora_fijada = selector_hora.value.strftime("%H:%M:%S")
            hora_seleccionada = hora_fijada
            campo_hora.value = hora_seleccionada
            boton_ahora.visible = True
            page.update()

    selector_fecha = ft.DatePicker(
        value=datetime.datetime.combine(ahora.date(), datetime.time.min),
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
        nonlocal fecha_fijada, fecha_seleccionada, hora_fijada, hora_seleccionada
        fecha_fijada = None
        hora_fijada = None
        momento = datetime.datetime.now()
        fecha_seleccionada = momento.date().isoformat()
        hora_seleccionada = momento.strftime("%H:%M:%S")
        campo_fecha.value = fecha_seleccionada
        campo_hora.value = hora_seleccionada
        selector_fecha.value = datetime.datetime.combine(
            momento.date(), datetime.time.min
        )
        selector_hora.value = momento.time()
        boton_ahora.visible = False
        page.update()

    def obtener_fecha():
        if fecha_fijada is not None:
            return fecha_fijada
        return datetime.datetime.now().date().isoformat()

    def obtener_hora():
        if hora_fijada is not None:
            return hora_fijada
        return datetime.datetime.now().strftime("%H:%M:%S")

    async def desplazar_a_turno(turno: int):
        await columna_principal.scroll_to(
            scroll_key=f"turno-{turno}",
            duration=500,
        )

    boton_ahora = ft.TextButton(
        "Usar fecha y hora actuales",
        icon=ft.Icons.UPDATE_ROUNDED,
        visible=False,
        on_click=establecer_ahora,
    )

    def actualizar_lista_borradores():
        columna_borradores.controls.clear()
        seleccionados = 0
        for clave in sorted(borradores):
            fecha, turno = clave
            check = selecciones[clave]
            seleccionados += int(bool(check.value))
            color = COLOR_TURNO[turno]
            columna_borradores.controls.append(
                ft.Container(
                    padding=12,
                    bgcolor="white",
                    border=ft.Border.all(1, COLOR_BORDE),
                    border_radius=9,
                    content=ft.Row(
                        [
                            check,
                            ft.Column(
                                [
                                    ft.Text(
                                        f"Turno {turno} · {fecha} · "
                                        f"{borradores[clave]['hora']}",
                                        weight=ft.FontWeight.BOLD,
                                        color=COLOR_TITULO,
                                    ),
                                    ft.Text(
                                        "Dos purgas, entrega y recibe completos.",
                                        size=12,
                                        color="#475569",
                                    ),
                                ],
                                spacing=3,
                                expand=True,
                            ),
                            ft.OutlinedButton(
                                "Cargar / editar",
                                icon=ft.Icons.EDIT_OUTLINED,
                                on_click=lambda _, k=clave: cargar_borrador(k),
                                style=ft.ButtonStyle(
                                    color=color,
                                    side=ft.BorderSide(1, color),
                                ),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                tooltip="Eliminar borrador",
                                icon_color="#B91C1C",
                                on_click=lambda _, k=clave: eliminar_borrador(k),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                )
            )
        estado_vacio.visible = not borradores
        boton_enviar.disabled = seleccionados == 0
        page.update()

    def cargar_borrador(clave: tuple[str, int]):
        nonlocal fecha_fijada, fecha_seleccionada, hora_fijada, hora_seleccionada
        _, turno = clave
        borrador = borradores[clave]
        borrador_en_edicion[turno] = clave
        fecha_fijada = str(borrador["fecha"])
        hora_fijada = str(borrador["hora"])
        fecha_seleccionada = fecha_fijada
        hora_seleccionada = hora_fijada
        campo_fecha.value = fecha_seleccionada
        campo_hora.value = hora_seleccionada
        selector_fecha.value = datetime.datetime.combine(
            datetime.date.fromisoformat(fecha_seleccionada),
            datetime.time.min,
        )
        selector_hora.value = datetime.time.fromisoformat(hora_seleccionada)
        boton_ahora.visible = True
        for campo, valor in borrador["valores"].items():
            campos_turno[turno][campo].value = str(valor)
        estado = estados_turno[turno]
        estado.value = "Borrador cargado. Edita los campos y vuelve a guardarlo."
        estado.color = "#1D4ED8"
        estado.visible = True
        page.update()
        page.run_task(desplazar_a_turno, turno)

    def eliminar_borrador(clave: tuple[str, int]):
        _, turno = clave
        borradores.pop(clave, None)
        selecciones.pop(clave, None)
        if borrador_en_edicion.get(turno) == clave:
            borrador_en_edicion.pop(turno, None)
        estados_turno[turno].value = (
            "Borrador eliminado. Completa el turno y guárdalo de nuevo."
        )
        estados_turno[turno].color = "#475569"
        estados_turno[turno].visible = True
        actualizar_lista_borradores()

    def guardar_borrador(turno: int, _):
        nonlocal fecha_seleccionada, hora_seleccionada
        estado = estados_turno[turno]
        try:
            valores = validar_turno(
                turno,
                {
                    campo: control.value or ""
                    for campo, control in campos_turno[turno].items()
                },
            )
        except ValueError as ex:
            estado.value = str(ex)
            estado.color = "#B91C1C"
            estado.visible = True
            page.update()
            return

        fecha_seleccionada = obtener_fecha()
        hora_seleccionada = obtener_hora()
        clave = (fecha_seleccionada, turno)
        clave_anterior = borrador_en_edicion.pop(turno, None)
        if clave_anterior is not None and clave_anterior != clave:
            borradores.pop(clave_anterior, None)
            selecciones.pop(clave_anterior, None)
        borradores[clave] = {
            "turno": turno,
            "fecha": fecha_seleccionada,
            "hora": hora_seleccionada,
            "valores": valores,
        }
        selecciones[clave] = ft.Checkbox(
            label="Incluir",
            value=True,
            on_change=lambda _: actualizar_lista_borradores(),
        )
        for control in campos_turno[turno].values():
            control.value = ""
        estado.value = (
            "Borrador guardado y campos limpiados. Usa Cargar / editar para "
            "recuperar sus valores."
        )
        estado.color = "#15803D"
        estado.visible = True
        actualizar_lista_borradores()

    def completar_envio(claves_a_enviar: list[tuple[str, int]]):
        boton_enviar.disabled = True
        mensaje_estado.visible = False
        page.update()
        seleccionados = [borradores[clave] for clave in claves_a_enviar]
        fecha = str(seleccionados[0]["fecha"])
        try:
            ids = insertar_borradores_bd(
                fecha,
                usuario_logueado,
                seleccionados,
            )
        except ValueError as ex:
            mensaje_estado.value = str(ex)
            mensaje_estado.color = "#B91C1C"
            mensaje_estado.visible = True
        except pyodbc.Error:
            logging.exception("SQL Server rechazó el envío del Formulario 3.")
            mensaje_estado.value = (
                "No fue posible enviar los turnos. Verifica SQL Server e inténtalo "
                "de nuevo. Si ya existe ese turno para la fecha, actualiza la lista."
            )
            mensaje_estado.color = "#B91C1C"
            mensaje_estado.visible = True
        except RuntimeError:
            logging.exception("SQL Server no confirmó el guardado del Formulario 3.")
            mensaje_estado.value = (
                "SQL Server no confirmó el guardado. Revisa la conexión e "
                "inténtalo de nuevo."
            )
            mensaje_estado.color = "#B91C1C"
            mensaje_estado.visible = True
        else:
            for clave, id_registro in zip(claves_a_enviar, ids):
                _, turno = clave
                borradores.pop(clave, None)
                selecciones.pop(clave, None)
                estados_turno[turno].value = (
                    f"Turno {turno} guardado en SQL Server "
                    f"(registro {id_registro})."
                )
                estados_turno[turno].color = "#15803D"
                estados_turno[turno].visible = True
            mensaje_estado.value = (
                f"Se enviaron {len(ids)} turno(s) para la fecha {fecha}."
            )
            mensaje_estado.color = "#15803D"
            mensaje_estado.visible = True
        finally:
            actualizar_lista_borradores()

    def enviar_borradores(_):
        claves_a_enviar = [
            clave
            for clave in borradores
            if selecciones[clave].value
        ]
        if not claves_a_enviar:
            mensaje_estado.value = "Selecciona al menos un borrador para enviar."
            mensaje_estado.color = "#B91C1C"
            mensaje_estado.visible = True
            page.update()
            return
        fechas = {
            str(borradores[clave]["fecha"])
            for clave in claves_a_enviar
        }
        if len(fechas) != 1:
            mensaje_estado.value = (
                "Envía por separado los borradores que tengan fechas distintas."
            )
            mensaje_estado.color = "#B91C1C"
            mensaje_estado.visible = True
            page.update()
            return

        desviaciones = []
        for clave in claves_a_enviar:
            turno = clave[1]
            desviaciones.extend(
                f"Turno {turno} · {desviacion}"
                for desviacion in obtener_desviaciones(
                    borradores[clave]["valores"]
                )
            )
        if not desviaciones:
            completar_envio(claves_a_enviar)
            return

        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                f"{len(desviaciones)} valor(es) fuera del control",
                color="#991B1B",
                weight=ft.FontWeight.BOLD,
            ),
            content=ft.Container(
                width=520,
                height=280,
                content=ft.Column(
                    [
                        ft.Text(
                            "Revisa las desviaciones. Puedes volver a editar "
                            "o confirmar el envío.",
                            size=13,
                            color="#475569",
                        ),
                        *[
                            ft.Container(
                                padding=9,
                                bgcolor="#FEF2F2",
                                border=ft.Border.all(1, "#FECACA"),
                                border_radius=8,
                                content=ft.Text(item, color="#7F1D1D", size=13),
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
                    on_click=lambda _: cerrar_dialogo(dialogo),
                ),
                ft.ElevatedButton(
                    "Confirmar y enviar",
                    icon=ft.Icons.CHECK_CIRCLE_ROUNDED,
                    bgcolor="#16A34A",
                    color="white",
                    on_click=lambda _: confirmar_envio(dialogo, claves_a_enviar),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        mostrar_dialogo(dialogo)

    def confirmar_envio(dialogo, claves_a_enviar: list[tuple[str, int]]):
        cerrar_dialogo(dialogo)
        completar_envio(claves_a_enviar)

    boton_enviar.on_click = enviar_borradores

    tarjetas_turno = []
    for turno in TURNOS:
        color = COLOR_TURNO[turno]
        campos: dict[str, ft.TextField] = {}
        paneles_caldera = []
        for caldera in CALDERAS:
            fondo = "#EFF6FF" if caldera == 1 else "#FFF7ED"
            color_caldera = "#0284C7" if caldera == 1 else "#EA580C"
            parametros = (
                (f"purga_{caldera}_ph", "pH", "UN", True),
                (
                    f"purga_{caldera}_alcalinidad_m",
                    "Alcalinidad M",
                    "ppm",
                    True,
                ),
                (f"purga_{caldera}_color", "Color", "", False),
                (f"purga_{caldera}_soda_g", "Soda adicionada", "g", True),
            )
            entradas = []
            for clave, nombre, unidad, numerico in parametros:
                etiqueta = f"{nombre} ({unidad})" if unidad else nombre
                campo = ft.TextField(
                    label=etiqueta,
                    hint_text="Hasta 2 decimales" if numerico else "Texto breve",
                    keyboard_type=(
                        ft.KeyboardType.NUMBER if numerico else ft.KeyboardType.TEXT
                    ),
                    max_length=20 if numerico else 50,
                    width=205,
                    color="#334155",
                    label_style=ft.TextStyle(color="#475569"),
                    border_radius=8,
                    border_color="#CBD5E1",
                    focused_border_color=color_caldera,
                )
                campos[clave] = campo
                entradas.append(campo)
            paneles_caldera.append(
                ft.Container(
                    padding=14,
                    bgcolor=fondo,
                    border=ft.Border.all(1, "#BFDBFE" if caldera == 1 else "#FED7AA"),
                    border_radius=11,
                    content=ft.Column(
                        [
                            ft.Text(
                                f"PURGA CALDERA #{caldera}",
                                size=14,
                                weight=ft.FontWeight.BOLD,
                                color=color_caldera,
                            ),
                            ft.Row(controls=entradas, spacing=10, run_spacing=8, wrap=True),
                        ],
                        spacing=10,
                    ),
                )
            )

        for campo, nombre in (("entrega", "Entrega"), ("recibe", "Recibe")):
            campos[campo] = ft.TextField(
                label=nombre,
                max_length=100,
                width=250,
                color="#334155",
                label_style=ft.TextStyle(color="#475569"),
                border_radius=8,
                border_color="#CBD5E1",
                focused_border_color=color,
            )
        campos_turno[turno] = campos
        estados_turno[turno] = ft.Text("", visible=False, size=12)
        boton_borrador = ft.OutlinedButton(
            f"Guardar Turno {turno} como borrador",
            icon=ft.Icons.DRAFTS_OUTLINED,
            on_click=lambda e, t=turno: guardar_borrador(t, e),
            style=ft.ButtonStyle(
                color=color,
                side=ft.BorderSide(1, color),
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            ),
        )
        tarjetas_turno.append(
            ft.Container(
                key=f"turno-{turno}",
                padding=18,
                bgcolor="white",
                border=ft.Border.all(1, COLOR_BORDE),
                border_radius=14,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Container(
                                    width=42,
                                    height=42,
                                    alignment=ft.Alignment.CENTER,
                                    bgcolor="#F1F5F9",
                                    border_radius=11,
                                    content=ft.Icon(
                                        ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED,
                                        color=color,
                                        size=24,
                                    ),
                                ),
                                ft.Text(
                                    f"TURNO {turno}",
                                    size=17,
                                    weight=ft.FontWeight.BOLD,
                                    color=COLOR_TITULO,
                                    expand=True,
                                ),
                            ],
                            spacing=12,
                        ),
                        ft.Row(
                            controls=paneles_caldera,
                            spacing=12,
                            run_spacing=12,
                            wrap=True,
                        ),
                        ft.Text(
                            "Entrega y recibe",
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_TITULO,
                        ),
                        ft.Row(
                            [campos["entrega"], campos["recibe"]],
                            spacing=10,
                            run_spacing=8,
                            wrap=True,
                        ),
                        estados_turno[turno],
                        ft.Row(
                            [boton_borrador],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ],
                    spacing=12,
                ),
            )
        )

    def confirmar_salida(_):
        if on_logout is None:
            return
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
                "Los borradores aún no enviados se perderán al volver al menú.",
                size=13,
                color="#334155",
            ),
            actions=[
                ft.OutlinedButton(
                    "Cancelar",
                    on_click=lambda _: cerrar_dialogo(dialogo),
                ),
                ft.ElevatedButton(
                    "Sí, Continuar y Salir",
                    on_click=lambda _: salir(dialogo),
                    bgcolor="#DC2626",
                    color="white",
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
        "",
        size=16,
        color="#F8FAFC",
        weight=ft.FontWeight.BOLD,
        no_wrap=True,
    )

    def animar_marquee():
        texto = (
            " CONTROL DE PURGAS DE CALDERA • TURNO 1 • TURNO 2 • TURNO 3 • "
            f" RESPONSABLE: {nombre_completo} • USUARIO: {usuario_logueado} • "
            " CRYSTAL S.A.S • "
        ) * 8
        while formulario_activo:
            try:
                texto = texto[1:] + texto[0]
                marquee.value = texto
                marquee.update()
            except Exception:
                logging.exception("Se detuvo la animación del encabezado del Formulario 3.")
                detener_formulario()
                break
            time.sleep(0.08)

    def actualizar_fecha_hora():
        while formulario_activo:
            try:
                momento = datetime.datetime.now()
                if fecha_fijada is None:
                    campo_fecha.value = momento.date().isoformat()
                    campo_fecha.update()
                if hora_fijada is None:
                    campo_hora.value = momento.strftime("%H:%M:%S")
                    campo_hora.update()
            except Exception:
                logging.exception(
                    "Se detuvo la actualización de fecha y hora del Formulario 3."
                )
                detener_formulario()
                break
            time.sleep(1)

    ruta_logo = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
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
        padding=20,
        content=ft.Column(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    icon_color="white",
                    bgcolor=COLOR_PRIMARIO,
                    tooltip="Volver al menú",
                    on_click=confirmar_salida,
                ),
                ft.Row(
                    [
                        logo,
                        ft.Container(
                            expand=True,
                            height=70,
                            bgcolor="#0F172A",
                            border_radius=10,
                            padding=12,
                            alignment=ft.Alignment.CENTER_LEFT,
                            content=marquee,
                        ),
                    ],
                    spacing=15,
                ),
                ft.Divider(),
                ft.Text(
                    "CONTROL DE PURGAS DE CALDERA",
                    size=24,
                    weight=ft.FontWeight.BOLD,
                    color=COLOR_PRIMARIO,
                ),
                ft.Text(
                    f"{nombre_completo} ({usuario_logueado})",
                    color="#475569",
                    size=12,
                ),
            ],
            spacing=8,
        ),
    )
    barra_fecha = ft.Container(
        padding=16,
        bgcolor="white",
        border=ft.Border.all(1, COLOR_BORDE),
        border_radius=12,
        content=ft.Row(
            [
                ft.Icon(ft.Icons.CALENDAR_MONTH_ROUNDED, color=COLOR_TITULO),
                ft.Text(
                    "Fecha de operación:",
                    weight=ft.FontWeight.BOLD,
                    color=COLOR_TITULO,
                ),
                campo_fecha,
                ft.IconButton(
                    icon=ft.Icons.CALENDAR_TODAY_ROUNDED,
                    icon_color=COLOR_PRIMARIO,
                    tooltip="Seleccionar fecha",
                    on_click=lambda _: mostrar_dialogo(selector_fecha),
                ),
                ft.Text(
                    "Hora:",
                    weight=ft.FontWeight.BOLD,
                    color=COLOR_TITULO,
                ),
                campo_hora,
                ft.IconButton(
                    icon=ft.Icons.ACCESS_TIME_ROUNDED,
                    icon_color=COLOR_PRIMARIO,
                    tooltip="Seleccionar hora",
                    on_click=lambda _: mostrar_dialogo(selector_hora),
                ),
                boton_ahora,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
        ),
    )
    introduccion = ft.Container(
        padding=16,
        bgcolor="#EFF6FF",
        border=ft.Border.all(1, "#BFDBFE"),
        border_radius=10,
        content=ft.Row(
            [
                ft.Icon(ft.Icons.INFO_OUTLINE_ROUNDED, color=COLOR_PRIMARIO),
                ft.Text(
                    "Registra una vez cada turno por fecha. pH: 10,5–11,5; "
                    "Alcalinidad M: máximo 500 ppm. Las desviaciones requieren "
                    "confirmación antes del envío.",
                    color="#1E3A8A",
                    size=13,
                    expand=True,
                ),
            ],
            spacing=10,
        ),
    )
    panel_borradores = ft.Container(
        padding=18,
        bgcolor="white",
        border=ft.Border.all(1, COLOR_BORDE),
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
                    "Los borradores se conservan mientras el formulario esté "
                    "abierto. Puedes cargarlos para editarlos, eliminarlos o "
                    "enviar los turnos seleccionados.",
                    size=13,
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
        [
            encabezado,
            barra_fecha,
            introduccion,
            *tarjetas_turno,
            panel_borradores,
        ],
        spacing=14,
        tight=True,
        scroll=ft.ScrollMode.AUTO,
    )
    contenido = ft.Container(
        expand=True,
        padding=10,
        content=columna_principal,
    )
    page.add(contenido)
    page.update()
    threading.Thread(target=animar_marquee, daemon=True).start()
    threading.Thread(target=actualizar_fecha_hora, daemon=True).start()
