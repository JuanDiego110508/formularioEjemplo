import datetime
import logging
import threading
import time
from decimal import Decimal, InvalidOperation
from typing import Mapping

import flet as ft
import pyodbc

import conexionform


TABLA_REGISTRO = "dbo.Registro_Monitoreo_Aguas_Caldera_FMAN42"

COLOR_PRIMARIO = "#1E3A8A"
COLOR_TITULO = "#0F172A"
COLOR_FONDO = "#F8FAFC"
COLOR_BORDE = "#E2E8F0"


SECCIONES = (
    {
        "id": "ALIMENTACION_CALDERA",
        "titulo": "Alimentación caldera",
        "subtitulo": "Agua de alimentación",
        "color": "#0284C7",
        "color_suave": "#E0F2FE",
        "icono": ft.Icons.WATER_DROP_ROUNDED,
        "parametros": (
            {
                "id": "ph",
                "nombre": "pH",
                "unidad": "UN",
                "control": "8,0 – 10,0",
                "regla": {"tipo": "rango", "min": "8.0", "max": "10.0"},
            },
            {
                "id": "std",
                "nombre": "STD",
                "unidad": "ppm",
                "control": "< 120",
                "regla": {"tipo": "menor", "max": "120"},
            },
            {
                "id": "conductividad",
                "nombre": "Conductividad",
                "unidad": "µS/cm",
                "control": "Sin límite indicado",
                "regla": None,
            },
            {
                "id": "dureza",
                "nombre": "Dureza",
                "unidad": "ppm",
                "control": "= 0",
                "regla": {"tipo": "igual", "valor": "0"},
            },
            {
                "id": "temperatura",
                "nombre": "Temperatura",
                "unidad": "°C",
                "control": "> 60",
                "regla": {"tipo": "mayor", "min": "60"},
            },
            {
                "id": "alcalinidad_m",
                "nombre": "Alc. M",
                "unidad": "ppm",
                "control": "Referencia: 120",
                "regla": None,
            },
        ),
    },
    {
        "id": "PURGA_CALDERA_1",
        "titulo": "Purga caldera #1",
        "subtitulo": "Agua de purga",
        "color": "#EA580C",
        "color_suave": "#FFEDD5",
        "icono": ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED,
        "parametros": (
            {
                "id": "ph",
                "nombre": "pH",
                "unidad": "UN",
                "control": "10,5 – 11,5",
                "regla": {"tipo": "rango", "min": "10.5", "max": "11.5"},
            },
            {
                "id": "std",
                "nombre": "STD",
                "unidad": "ppm",
                "control": "< 2500",
                "regla": {"tipo": "menor", "max": "2500"},
            },
            {
                "id": "conductividad",
                "nombre": "Conductividad",
                "unidad": "µS/cm",
                "control": "< 3500",
                "regla": {"tipo": "menor", "max": "3500"},
            },
            {
                "id": "dureza",
                "nombre": "Dureza",
                "unidad": "ppm",
                "control": "= 0",
                "regla": {"tipo": "igual", "valor": "0"},
            },
            {
                "id": "hierro",
                "nombre": "Fe",
                "unidad": "ppm",
                "control": "< 10",
                "regla": {"tipo": "menor", "max": "10"},
            },
            {
                "id": "silice",
                "nombre": "Sílice",
                "unidad": "ppm",
                "control": "< 80",
                "regla": {"tipo": "menor", "max": "80"},
            },
            {
                "id": "sulfitos",
                "nombre": "Sulfitos",
                "unidad": "ppm",
                "control": "30 – 60",
                "regla": {"tipo": "rango", "min": "30", "max": "60"},
            },
            {
                "id": "alcalinidad_m",
                "nombre": "Alc. M",
                "unidad": "ppm",
                "control": "< 500",
                "regla": {"tipo": "menor", "max": "500"},
            },
            {
                "id": "alcalinidad_p",
                "nombre": "Alc. P",
                "unidad": "ppm",
                "control": "< 500",
                "regla": {"tipo": "menor", "max": "500"},
            },
            {
                "id": "alcalinidad_oh",
                "nombre": "Alc. OH-",
                "unidad": "ppm",
                "control": "> 100",
                "regla": {"tipo": "mayor", "min": "100"},
            },
        ),
    },
    {
        "id": "PURGA_CALDERA_2",
        "titulo": "Purga caldera #2",
        "subtitulo": "Agua de purga",
        "color": "#7C3AED",
        "color_suave": "#EDE9FE",
        "icono": ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED,
        "parametros": (
            {
                "id": "ph",
                "nombre": "pH",
                "unidad": "UN",
                "control": "10,5 – 11,5",
                "regla": {"tipo": "rango", "min": "10.5", "max": "11.5"},
            },
            {
                "id": "std",
                "nombre": "STD",
                "unidad": "ppm",
                "control": "< 2500",
                "regla": {"tipo": "menor", "max": "2500"},
            },
            {
                "id": "conductividad",
                "nombre": "Conductividad",
                "unidad": "µS/cm",
                "control": "< 3500",
                "regla": {"tipo": "menor", "max": "3500"},
            },
            {
                "id": "dureza",
                "nombre": "Dureza",
                "unidad": "ppm",
                "control": "= 0",
                "regla": {"tipo": "igual", "valor": "0"},
            },
            {
                "id": "hierro",
                "nombre": "Fe",
                "unidad": "ppm",
                "control": "< 10",
                "regla": {"tipo": "menor", "max": "10"},
            },
            {
                "id": "silice",
                "nombre": "Sílice",
                "unidad": "ppm",
                "control": "< 80",
                "regla": {"tipo": "menor", "max": "80"},
            },
            {
                "id": "sulfitos",
                "nombre": "Sulfitos",
                "unidad": "ppm",
                "control": "30 – 60",
                "regla": {"tipo": "rango", "min": "30", "max": "60"},
            },
            {
                "id": "alcalinidad_m",
                "nombre": "Alc. M",
                "unidad": "ppm",
                "control": "< 500",
                "regla": {"tipo": "menor", "max": "500"},
            },
            {
                "id": "alcalinidad_p",
                "nombre": "Alc. P",
                "unidad": "ppm",
                "control": "< 500",
                "regla": {"tipo": "menor", "max": "500"},
            },
            {
                "id": "alcalinidad_oh",
                "nombre": "Alc. OH-",
                "unidad": "ppm",
                "control": "> 100",
                "regla": {"tipo": "mayor", "min": "100"},
            },
        ),
    },
    {
        "id": "PURGA_CALDERA_3",
        "titulo": "Purga caldera #3",
        "subtitulo": "Agua de purga",
        "color": "#15803D",
        "color_suave": "#DCFCE7",
        "icono": ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED,
        "parametros": (
            {
                "id": "ph",
                "nombre": "pH",
                "unidad": "UN",
                "control": "10,5 – 11,5",
                "regla": {"tipo": "rango", "min": "10.5", "max": "11.5"},
            },
            {
                "id": "std",
                "nombre": "STD",
                "unidad": "ppm",
                "control": "< 2500",
                "regla": {"tipo": "menor", "max": "2500"},
            },
            {
                "id": "conductividad",
                "nombre": "Conductividad",
                "unidad": "µS/cm",
                "control": "< 3500",
                "regla": {"tipo": "menor", "max": "3500"},
            },
            {
                "id": "dureza",
                "nombre": "Dureza",
                "unidad": "ppm",
                "control": "= 0",
                "regla": {"tipo": "igual", "valor": "0"},
            },
            {
                "id": "hierro",
                "nombre": "Fe",
                "unidad": "ppm",
                "control": "< 10",
                "regla": {"tipo": "menor", "max": "10"},
            },
            {
                "id": "silice",
                "nombre": "Sílice",
                "unidad": "ppm",
                "control": "< 80",
                "regla": {"tipo": "menor", "max": "80"},
            },
            {
                "id": "sulfitos",
                "nombre": "Sulfitos",
                "unidad": "ppm",
                "control": "30 – 60",
                "regla": {"tipo": "rango", "min": "30", "max": "60"},
            },
            {
                "id": "alcalinidad_m",
                "nombre": "Alc. M",
                "unidad": "ppm",
                "control": "< 500",
                "regla": {"tipo": "menor", "max": "500"},
            },
            {
                "id": "alcalinidad_p",
                "nombre": "Alc. P",
                "unidad": "ppm",
                "control": "< 500",
                "regla": {"tipo": "menor", "max": "500"},
            },
            {
                "id": "alcalinidad_oh",
                "nombre": "Alc. OH-",
                "unidad": "ppm",
                "control": "> 100",
                "regla": {"tipo": "mayor", "min": "100"},
            },
        ),
    },
)

PARAMETROS_REGISTRO = {
    seccion["id"]: tuple(
        f"{seccion['id'].lower()}_{parametro['id']}"
        for parametro in seccion["parametros"]
    )
    for seccion in SECCIONES
}
COLUMNAS_REGISTRO = tuple(
    columna
    for columnas in PARAMETROS_REGISTRO.values()
    for columna in columnas
)


def parsear_valor(texto: str) -> Decimal:
    valor_texto = texto.strip().replace(",", ".")
    if not valor_texto:
        raise ValueError("La lectura es obligatoria.")
    try:
        valor = Decimal(valor_texto)
    except InvalidOperation as ex:
        raise ValueError(f"Lectura numérica no válida: {texto!r}") from ex
    if not valor.is_finite():
        raise ValueError(f"La lectura debe ser un número finito: {texto!r}")
    if max(0, -valor.normalize().as_tuple().exponent) > 2:
        raise ValueError("Cada lectura admite máximo dos decimales.")
    if valor and valor.adjusted() >= 8:
        raise ValueError("La lectura admite máximo ocho dígitos enteros.")
    return valor


def evaluar_criterio(valor: Decimal, regla: dict | None) -> bool | None:
    if regla is None:
        return None
    if regla["tipo"] == "rango":
        return Decimal(regla["min"]) <= valor <= Decimal(regla["max"])
    if regla["tipo"] == "menor":
        return valor < Decimal(regla["max"])
    if regla["tipo"] == "mayor":
        return valor > Decimal(regla["min"])
    if regla["tipo"] == "igual":
        return valor == Decimal(regla["valor"])
    raise ValueError(f"Tipo de criterio desconocido: {regla['tipo']!r}")


def validar_lecturas(
    campos: Mapping[tuple[str, str], str | None],
) -> list[tuple[str, str, Decimal]]:
    lecturas = []
    faltantes = []
    for seccion in SECCIONES:
        for parametro in seccion["parametros"]:
            clave = (seccion["id"], parametro["id"])
            texto = campos.get(clave) or ""
            try:
                valor = parsear_valor(texto)
            except ValueError:
                faltantes.append(f"{seccion['titulo']}: {parametro['nombre']}")
                continue
            lecturas.append((clave[0], clave[1], valor))
    if faltantes:
        raise ValueError(
            "Completa todas las lecturas con números válidos. "
            "Pendientes: " + ", ".join(faltantes[:5])
            + ("…" if len(faltantes) > 5 else "")
        )
    return lecturas


def validar_lecturas_seccion(
    seccion_id: str,
    campos: Mapping[tuple[str, str], str | None],
) -> list[tuple[str, str, Decimal]]:
    seccion = next(
        (item for item in SECCIONES if item["id"] == seccion_id),
        None,
    )
    if seccion is None:
        raise ValueError(f"Sección de caldera desconocida: {seccion_id!r}")

    lecturas = []
    faltantes = []
    for parametro in seccion["parametros"]:
        clave = (seccion_id, parametro["id"])
        try:
            valor = parsear_valor(campos.get(clave) or "")
        except ValueError:
            faltantes.append(parametro["nombre"])
            continue
        lecturas.append((seccion_id, parametro["id"], valor))

    if faltantes:
        raise ValueError(
            f"Completa las lecturas de {seccion['titulo']}: "
            + ", ".join(faltantes)
            + "."
        )
    return lecturas


def obtener_desviaciones(
    lecturas: list[tuple[str, str, Decimal]],
) -> list[dict[str, str]]:
    parametros = {
        (seccion["id"], parametro["id"]): (seccion, parametro)
        for seccion in SECCIONES
        for parametro in seccion["parametros"]
    }
    desviaciones = []
    for seccion_id, parametro_id, valor in lecturas:
        seccion, parametro = parametros[(seccion_id, parametro_id)]
        if evaluar_criterio(valor, parametro["regla"]) is False:
            desviaciones.append(
                {
                    "seccion": seccion["titulo"],
                    "parametro": parametro["nombre"],
                    "valor": str(valor),
                    "unidad": parametro["unidad"],
                    "control": parametro["control"],
                }
            )
    return desviaciones


def validar_lecturas_seleccionadas(
    lecturas: list[tuple[str, str, Decimal]],
    secciones_seleccionadas: set[str],
) -> list[tuple[str, str, Decimal]]:
    secciones_validas = {seccion["id"] for seccion in SECCIONES}
    if not secciones_seleccionadas or not secciones_seleccionadas <= secciones_validas:
        raise ValueError("Selecciona al menos una sección válida para enviar.")

    esperadas = {
        (seccion["id"], parametro["id"])
        for seccion in SECCIONES
        if seccion["id"] in secciones_seleccionadas
        for parametro in seccion["parametros"]
    }
    claves = [(seccion, parametro) for seccion, parametro, _ in lecturas]
    if len(claves) != len(esperadas) or set(claves) != esperadas:
        raise ValueError(
            "Las lecturas seleccionadas no corresponden a los borradores "
            "completos de esas secciones."
        )
    if any(not valor.is_finite() for _, _, valor in lecturas):
        raise ValueError("Todas las lecturas deben ser valores numéricos finitos.")
    return lecturas


def insertar_registro_bd(
    fecha: str,
    hora: str,
    analizo: str,
    usuario_registro: str,
    observaciones: str,
    lecturas: list[tuple[str, str, Decimal]],
    secciones_seleccionadas: set[str] | None = None,
) -> int:
    if secciones_seleccionadas is None:
        secciones_seleccionadas = {seccion["id"] for seccion in SECCIONES}
    validar_lecturas_seleccionadas(lecturas, secciones_seleccionadas)

    try:
        fecha_sql = datetime.date.fromisoformat(fecha)
        hora_sql = datetime.time.fromisoformat(hora)
    except ValueError as ex:
        raise ValueError("La fecha o la hora no tienen un formato válido.") from ex

    analizo = analizo.strip()
    usuario_registro = usuario_registro.strip()
    observaciones = observaciones.strip()
    if not analizo or not usuario_registro:
        raise ValueError("Completa el nombre de quien analizó y el usuario.")
    if len(analizo) > 100 or len(usuario_registro) > 100:
        raise ValueError("El nombre y el usuario admiten máximo 100 caracteres.")
    if len(observaciones) > 1000:
        raise ValueError("Las observaciones admiten máximo 1000 caracteres.")

    conn = None
    cursor = None
    try:
        conn = conexionform.obtener_conexion_formulario()
        cursor = conn.cursor()
        columnas_seleccionadas = tuple(
            columna
            for seccion_id in sorted(secciones_seleccionadas)
            for columna in PARAMETROS_REGISTRO[seccion_id]
        )
        columnas_sql = ", ".join(columnas_seleccionadas)
        cursor.execute(
            f"""
            SELECT id_registro, {columnas_sql}
            FROM {TABLA_REGISTRO} WITH (UPDLOCK, HOLDLOCK)
            WHERE fecha = ?
            """,
            fecha_sql.isoformat(),
        )
        fila = cursor.fetchone()
        if fila is not None:
            columnas_existentes = dict(zip(columnas_seleccionadas, fila[1:]))
            secciones_existentes = {
                seccion_id
                for seccion_id in secciones_seleccionadas
                if any(
                    columnas_existentes[columna] is not None
                    for columna in PARAMETROS_REGISTRO[seccion_id]
                )
            }
        else:
            secciones_existentes = set()
        if secciones_existentes:
            nombres_existentes = [
                seccion["titulo"]
                for seccion in SECCIONES
                if seccion["id"] in secciones_existentes
            ]
            raise ValueError(
                "Ya se habían enviado estas secciones para la fecha "
                f"{fecha_sql.isoformat()}: {', '.join(nombres_existentes)}."
            )

        valores_por_columna = {
            f"{seccion_id.lower()}_{parametro_id}": valor
            for seccion_id, parametro_id, valor in lecturas
        }
        if fila is None:
            columnas = (
                "fecha",
                "hora",
                "analizo",
                "usuario_registro",
                "observaciones",
                *COLUMNAS_REGISTRO,
            )
            valores = (
                fecha_sql.isoformat(),
                hora_sql.strftime("%H:%M:%S"),
                analizo,
                usuario_registro,
                observaciones or None,
                *(
                    valores_por_columna.get(columna)
                    for columna in COLUMNAS_REGISTRO
                ),
            )
            cursor.execute(
                f"""
                INSERT INTO {TABLA_REGISTRO} ({", ".join(columnas)})
                OUTPUT INSERTED.id_registro
                VALUES ({", ".join("?" for _ in columnas)})
                """,
                *valores,
            )
            fila_insertada = cursor.fetchone()
            if fila_insertada is None:
                raise RuntimeError(
                    "SQL Server no devolvió el identificador del registro."
                )
            id_registro = int(fila_insertada[0])
        else:
            asignaciones_mediciones = ", ".join(
                f"{columna} = ?" for columna in columnas_seleccionadas
            )
            cursor.execute(
                f"""
                UPDATE {TABLA_REGISTRO}
                SET 
                    {asignaciones_mediciones},
                    hora = ?,
                    analizo = ?,
                    usuario_registro = ?,
                    observaciones = ?
                WHERE id_registro = ?
                """,
                *(
                    valores_por_columna[columna]
                    for columna in columnas_seleccionadas
                ),
                hora_sql.strftime("%H:%M:%S"),
                analizo,
                usuario_registro,
                observaciones or None,
                int(fila[0]),
            )
            id_registro = int(fila[0])

        conn.commit()
        return id_registro
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
    page.title = "Formulario 2 - Aguas de caldera (FMAN-42)"
    page.bgcolor = COLOR_FONDO

    formulario_activo = True
    page.on_disconnect = lambda _: detener_formulario()

    def detener_formulario():
        nonlocal formulario_activo
        formulario_activo = False

    ahora = datetime.datetime.now()
    fecha_fijada = None
    hora_fijada = None
    txt_fecha = ft.TextField(
        value=ahora.strftime("%Y-%m-%d"),
        read_only=True,
        width=150,
        height=40,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=8,
        border_color="#CBD5E1",
        text_size=13,
        text_style=ft.TextStyle(weight=ft.FontWeight.W_500),
    )
    txt_hora = ft.TextField(
        value=ahora.strftime("%H:%M:%S"),
        read_only=True,
        width=130,
        height=40,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=8,
        border_color="#CBD5E1",
        text_size=13,
        text_style=ft.TextStyle(weight=ft.FontWeight.W_500),
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
        value=ahora,
        first_date=ahora - datetime.timedelta(days=4),
        last_date=ahora,
        current_date=ahora,
        on_change=on_date_change,
    )
    time_picker = ft.TimePicker(value=ahora.time(), on_change=on_time_change)

    def abrir_selector(selector):
        if hasattr(page, "show_dialog"):
            page.show_dialog(selector)
        elif hasattr(page, "open"):
            page.open(selector)
        else:
            page.dialog = selector
            selector.open = True
            page.update()

    def poner_ahora(_):
        nonlocal fecha_fijada, hora_fijada
        fecha_fijada = None
        hora_fijada = None
        momento = datetime.datetime.now()
        txt_fecha.value = momento.strftime("%Y-%m-%d")
        txt_hora.value = momento.strftime("%H:%M:%S")
        btn_actualizar_ahora.visible = False
        page.update()

    btn_actualizar_ahora = ft.TextButton(
        "Usar fecha y hora actuales",
        icon=ft.Icons.UPDATE_ROUNDED,
        visible=False,
        on_click=poner_ahora,
    )

    def obtener_fecha():
        return fecha_fijada or datetime.datetime.now().strftime("%Y-%m-%d")

    def obtener_hora():
        return hora_fijada or datetime.datetime.now().strftime("%H:%M:%S")

    entradas: dict[tuple[str, str], ft.TextField] = {}
    estados_lectura: dict[tuple[str, str], ft.Text] = {}
    borradores: dict[str, dict] = {}
    seleccion_borradores: dict[str, ft.Checkbox] = {}
    estados_borrador: dict[str, ft.Text] = {}
    botones_borrador: dict[str, ft.OutlinedButton] = {}
    columna_borradores = ft.Column(spacing=8)
    estado_vacio_borradores = ft.Container(
        padding=14,
        bgcolor="#F8FAFC",
        border=ft.Border.all(1, COLOR_BORDE),
        border_radius=9,
        content=ft.Text(
            "Todavía no hay borradores. Guarda una sección para "
            "revisarla aquí antes de enviarla.",
            size=13,
            color="#475569",
        ),
    )
    boton_enviar_borradores = ft.ElevatedButton(
        "Enviar borradores seleccionados",
        icon=ft.Icons.SEND_ROUNDED,
        bgcolor=COLOR_PRIMARIO,
        color="white",
        disabled=True,
    )

    def actualizar_lista_borradores():
        columna_borradores.controls.clear()
        seleccionados = 0
        for seccion in SECCIONES:
            seccion_id = seccion["id"]
            borrador = borradores.get(seccion_id)
            if borrador is None:
                continue
            checkbox = seleccion_borradores[seccion_id]
            incluir = bool(checkbox.value)
            if incluir:
                seleccionados += 1
            lecturas = borrador["lecturas"]
            contador = f"{len(lecturas)}/{len(seccion['parametros'])} lecturas"
            resumen = ft.Text(
                f"{borrador['fecha']} · {borrador['hora']} · "
                f"{borrador['analizo']} · {contador}",
                size=12,
                color="#475569",
            )
            columna_borradores.controls.append(
                ft.Container(
                    padding=12,
                    bgcolor="white",
                    border=ft.Border.all(1, COLOR_BORDE),
                    border_radius=9,
                    content=ft.Row(
                        [
                            checkbox,
                            ft.Row(
                                [
                                    ft.Text(
                                        seccion["titulo"],
                                        size=14,
                                        weight=ft.FontWeight.BOLD,
                                        color=COLOR_TITULO,
                                    ),
                                    resumen,
                                ],
                                spacing=3,
                                expand=True,
                            ),
                            ft.Row(
                                [
                                    ft.IconButton(
                                        icon=ft.Icons.VISIBILITY_OUTLINED,
                                        icon_color=COLOR_PRIMARIO,
                                        tooltip="Visualizar borrador",
                                        on_click=lambda _, sid=seccion_id: visualizar_borrador(
                                            sid
                                        ),
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.EDIT_OUTLINED,
                                        icon_color="#D97706",
                                        tooltip="Editar borrador",
                                        on_click=lambda _, sid=seccion_id: editar_borrador(
                                            sid
                                        ),
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                        icon_color="#B91C1C",
                                        tooltip="Descartar borrador",
                                        on_click=lambda _, sid=seccion_id: descartar_borrador(
                                            sid
                                        ),
                                    ),
                                ],
                                spacing=0,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                )
            )
        estado_vacio_borradores.visible = not borradores
        boton_enviar_borradores.disabled = seleccionados == 0
        if page.controls:
            page.update()

    def al_cambiar_seleccion(_):
        actualizar_lista_borradores()

    def descartar_borrador(seccion_id):
        borradores.pop(seccion_id, None)
        seleccion_borradores.pop(seccion_id, None)
        estado = estados_borrador[seccion_id]
        estado.value = "Borrador descartado. Puedes volver a guardarlo."
        estado.color = "#475569"
        actualizar_lista_borradores()
        seccion = next(item for item in SECCIONES if item["id"] == seccion_id)
        page.snack_bar = ft.SnackBar(
            ft.Text(f"Borrador de {seccion['titulo']} descartado."),
            bgcolor="#475569",
        )
        page.snack_bar.open = True
        page.update()

    def actualizar_estado_lectura(seccion, parametro, campo):
        control = estados_lectura[(seccion["id"], parametro["id"])]
        texto = campo.value or ""
        if not texto.strip():
            control.value = "Requerido"
            control.color = "#64748B"
        else:
            try:
                valor = parsear_valor(texto)
                cumple = evaluar_criterio(valor, parametro["regla"])
            except ValueError:
                control.value = "Número no válido"
                control.color = "#B91C1C"
            else:
                if cumple is None:
                    control.value = "Sin criterio de control"
                    control.color = "#475569"
                elif cumple:
                    control.value = "Dentro del control"
                    control.color = "#15803D"
                else:
                    control.value = "Fuera del control"
                    control.color = "#B91C1C"
        page.update()

    # Secciones plegables. Se evita combinar wrap=True con expand=True.
    tarjetas_seccion: list[ft.Container] = []
    contenidos_seccion: dict[str, ft.Container] = {}
    botones_expansion: dict[str, ft.IconButton] = {}
    resumenes_seccion: dict[str, ft.Text] = {}
    secciones_expandidas: dict[str, bool] = {
        seccion["id"]: seccion["id"] == "ALIMENTACION_CALDERA"
        for seccion in SECCIONES
    }

    def actualizar_resumen_seccion(seccion_id: str):
        seccion = next(item for item in SECCIONES if item["id"] == seccion_id)
        diligenciados = sum(
            1
            for parametro in seccion["parametros"]
            if (entradas[(seccion_id, parametro["id"])].value or "").strip()
        )
        total = len(seccion["parametros"])
        resumenes_seccion[seccion_id].value = (
            "Sin diligenciar"
            if diligenciados == 0
            else "Sección completa"
            if diligenciados == total
            else f"{diligenciados} de {total} campos diligenciados"
        )

    def alternar_seccion(seccion_id: str):
        expandida = not secciones_expandidas[seccion_id]
        secciones_expandidas[seccion_id] = expandida
        contenidos_seccion[seccion_id].visible = expandida
        botones_expansion[seccion_id].icon = (
            ft.Icons.KEYBOARD_ARROW_UP_ROUNDED
            if expandida
            else ft.Icons.KEYBOARD_ARROW_DOWN_ROUNDED
        )
        botones_expansion[seccion_id].tooltip = (
            "Contraer sección" if expandida else "Expandir sección"
        )
        page.update()

    for seccion in SECCIONES:
        seccion_id = seccion["id"]
        tarjetas_parametros = []
        for parametro in seccion["parametros"]:
            clave = (seccion_id, parametro["id"])
            estado = ft.Text("Requerido", size=11, color="#64748B")
            campo = ft.TextField(
                label=f"Lectura ({parametro['unidad']})",
                width=200,
                keyboard_type=ft.KeyboardType.NUMBER,
                max_length=20,
                border_radius=8,
                border_color="#CBD5E1",
                focused_border_color=seccion["color"],
                on_change=lambda e, s=seccion, p=parametro: actualizar_estado_lectura(
                    s, p, e.control
                ),
            )
            entradas[clave] = campo
            estados_lectura[clave] = estado
            tarjetas_parametros.append(
                ft.Container(
                    width=225,
                    padding=12,
                    bgcolor="white",
                    border=ft.Border.all(1, COLOR_BORDE),
                    border_radius=10,
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        parametro["nombre"],
                                        weight=ft.FontWeight.BOLD,
                                        color=COLOR_TITULO,
                                        expand=True,
                                    ),
                                    ft.Text(
                                        parametro["unidad"],
                                        size=11,
                                        color="#475569",
                                    ),
                                ],
                                spacing=5,
                            ),
                            ft.Text(
                                f"Control: {parametro['control']}",
                                size=11,
                                color="#475569",
                            ),
                            campo,
                            estado,
                        ],
                        spacing=5,
                    ),
                )
            )

        estado_seccion = ft.Text(
            "Completa esta sección y guárdala como borrador antes de enviarla.",
            size=12,
            color="#475569",
        )
        estados_borrador[seccion_id] = estado_seccion
        boton_borrador = ft.OutlinedButton(
            "Guardar sección como borrador",
            icon=ft.Icons.DRAFTS_OUTLINED,
            style=ft.ButtonStyle(
                color=seccion["color"],
                side=ft.BorderSide(1, seccion["color"]),
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            ),
        )
        botones_borrador[seccion_id] = boton_borrador

        resumen = ft.Text(
            "Sin diligenciar",
            size=12,
            color="#64748B",
            weight=ft.FontWeight.W_500,
        )
        resumenes_seccion[seccion_id] = resumen
        boton_expandir = ft.IconButton(
            icon=(
                ft.Icons.KEYBOARD_ARROW_UP_ROUNDED
                if secciones_expandidas[seccion_id]
                else ft.Icons.KEYBOARD_ARROW_DOWN_ROUNDED
            ),
            icon_color=seccion["color"],
            tooltip=(
                "Contraer sección"
                if secciones_expandidas[seccion_id]
                else "Expandir sección"
            ),
            on_click=lambda _, sid=seccion_id: alternar_seccion(sid),
        )
        botones_expansion[seccion_id] = boton_expandir

        contenido = ft.Container(
            visible=secciones_expandidas[seccion_id],
            padding=ft.Padding.only(top=12),
            content=ft.Column(
                [
                    ft.Row(
                        controls=tarjetas_parametros,
                        spacing=10,
                        run_spacing=10,
                        wrap=True,
                    ),
                    estado_seccion,
                    ft.Row(
                        [boton_borrador],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=10,
                tight=True,
            ),
        )
        contenidos_seccion[seccion_id] = contenido

        encabezado_seccion = ft.Container(
            padding=ft.Padding.symmetric(horizontal=4, vertical=2),
            on_click=lambda _, sid=seccion_id: alternar_seccion(sid),
            content=ft.Row(
                [
                    ft.Container(
                        width=42,
                        height=42,
                        alignment=ft.Alignment.CENTER,
                        bgcolor=seccion["color_suave"],
                        border_radius=11,
                        content=ft.Icon(
                            seccion["icono"],
                            color=seccion["color"],
                            size=24,
                        ),
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                seccion["titulo"],
                                size=17,
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TITULO,
                            ),
                            ft.Row(
                                [
                                    ft.Text(
                                        seccion["subtitulo"],
                                        size=12,
                                        color="#475569",
                                    ),
                                    ft.Text("·", size=12, color="#94A3B8"),
                                    resumen,
                                ],
                                spacing=6,
                                wrap=True,
                            ),
                        ],
                        spacing=3,
                        expand=True,
                    ),
                    ft.Text(
                        f"{len(seccion['parametros'])} parámetros",
                        size=12,
                        color=seccion["color"],
                        weight=ft.FontWeight.BOLD,
                    ),
                    boton_expandir,
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        tarjetas_seccion.append(
            ft.Container(
                padding=18,
                bgcolor="white",
                border=ft.Border.all(1, COLOR_BORDE),
                border_radius=14,
                content=ft.Column(
                    [encabezado_seccion, contenido],
                    spacing=0,
                    tight=True,
                ),
            )
        )

    # "Analizó" se toma automáticamente del usuario autenticado.
    analizo_automatico = (nombre_completo or usuario_logueado or "").strip()

    # Campo interno: se edita mediante el diálogo de Observaciones.
    campo_observaciones = ft.TextField(
        label="Observaciones",
        hint_text="Escribe las observaciones de la medición diaria",
        multiline=True,
        min_lines=5,
        max_lines=8,
        max_length=1000,
        color="#334155",
        bgcolor="white",
        border_color="#CBD5E1",
        focused_border_color=COLOR_PRIMARIO,
        cursor_color=COLOR_PRIMARIO,
        label_style=ft.TextStyle(color="#475569"),
        hint_style=ft.TextStyle(color="#94A3B8"),
        border_radius=10,
    )
    texto_estado_observacion = ft.Text(
        "Sin observaciones guardadas",
        size=12,
        color="#64748B",
    )
    mensaje_estado = ft.Text("", visible=False, size=13)
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

    def visualizar_borrador(seccion_id: str):
        borrador = borradores.get(seccion_id)
        seccion = next(
            (item for item in SECCIONES if item["id"] == seccion_id),
            None,
        )
        if borrador is None or seccion is None:
            page.snack_bar = ft.SnackBar(
                ft.Text("El borrador ya no está disponible."),
                bgcolor="#B91C1C",
            )
            page.snack_bar.open = True
            page.update()
            return

        parametros = {
            parametro["id"]: parametro
            for parametro in seccion["parametros"]
        }
        filas_lecturas = []
        for _, parametro_id, valor in borrador["lecturas"]:
            parametro = parametros[parametro_id]
            cumple = evaluar_criterio(valor, parametro["regla"])
            color_estado = (
                "#15803D" if cumple is True
                else "#B91C1C" if cumple is False
                else "#475569"
            )
            texto_estado = (
                "Dentro del control" if cumple is True
                else "Fuera del control" if cumple is False
                else "Sin criterio"
            )
            filas_lecturas.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=9),
                    bgcolor="white",
                    border=ft.Border.all(1, COLOR_BORDE),
                    border_radius=8,
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        parametro["nombre"],
                                        weight=ft.FontWeight.BOLD,
                                        color=COLOR_TITULO,
                                    ),
                                    ft.Text(
                                        f"Control: {parametro['control']}",
                                        size=11,
                                        color="#64748B",
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Text(
                                f"{valor} {parametro['unidad']}",
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TITULO,
                            ),
                            ft.Text(
                                texto_estado,
                                size=11,
                                color=color_estado,
                                weight=ft.FontWeight.W_500,
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )

        observacion = borrador.get("observaciones") or "Sin observaciones"
        dialogo = ft.AlertDialog(
            modal=True,
            bgcolor="white",
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.VISIBILITY_OUTLINED, color=seccion["color"]),
                    ft.Text(
                        f"Vista previa · {seccion['titulo']}",
                        weight=ft.FontWeight.BOLD,
                        color=COLOR_TITULO,
                    ),
                ],
                spacing=8,
            ),
            content=ft.Container(
                width=680,
                height=520,
                bgcolor="white",
                content=ft.Column(
                    [
                        ft.Container(
                            padding=12,
                            bgcolor=seccion["color_suave"],
                            border_radius=9,
                            content=ft.Column(
                                [
                                    ft.Text(
                                        f"Fecha: {borrador['fecha']}   ·   Hora: {borrador['hora']}",
                                        weight=ft.FontWeight.BOLD,
                                        color=COLOR_TITULO,
                                    ),
                                    ft.Text(
                                        f"Responsable: {borrador['analizo']}",
                                        size=12,
                                        color="#475569",
                                    ),
                                ],
                                spacing=3,
                            ),
                        ),
                        *filas_lecturas,
                        ft.Container(
                            padding=12,
                            bgcolor="#F8FAFC",
                            border=ft.Border.all(1, COLOR_BORDE),
                            border_radius=8,
                            content=ft.Column(
                                [
                                    ft.Text(
                                        "Observaciones",
                                        weight=ft.FontWeight.BOLD,
                                        color=COLOR_TITULO,
                                    ),
                                    ft.Text(observacion, color="#475569"),
                                ],
                                spacing=4,
                            ),
                        ),
                    ],
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                ),
            ),
            actions=[
                ft.OutlinedButton(
                    "Cerrar",
                    on_click=lambda _: cerrar_dialogo(dialogo),
                ),
                ft.ElevatedButton(
                    "Editar borrador",
                    icon=ft.Icons.EDIT_OUTLINED,
                    bgcolor=COLOR_PRIMARIO,
                    color="white",
                    on_click=lambda _: editar_desde_vista(dialogo, seccion_id),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        mostrar_dialogo(dialogo)

    def editar_desde_vista(dialogo, seccion_id: str):
        cerrar_dialogo(dialogo)
        editar_borrador(seccion_id)

    def editar_borrador(seccion_id: str):
        nonlocal fecha_fijada, hora_fijada
        borrador = borradores.get(seccion_id)
        seccion = next(
            (item for item in SECCIONES if item["id"] == seccion_id),
            None,
        )
        if borrador is None or seccion is None:
            page.snack_bar = ft.SnackBar(
                ft.Text("El borrador ya no está disponible."),
                bgcolor="#B91C1C",
            )
            page.snack_bar.open = True
            page.update()
            return

        valores = {
            parametro_id: valor
            for _, parametro_id, valor in borrador["lecturas"]
        }
        for parametro in seccion["parametros"]:
            campo = entradas[(seccion_id, parametro["id"])]
            valor = valores.get(parametro["id"])
            campo.value = "" if valor is None else str(valor)
            actualizar_estado_lectura(seccion, parametro, campo)

        # Conserva la fecha original del borrador, pero la hora vuelve
        # automáticamente al momento actual para evitar guardar una hora antigua.
        fecha_fijada = borrador["fecha"]
        hora_fijada = None
        momento_actual = datetime.datetime.now()
        txt_fecha.value = fecha_fijada
        txt_hora.value = momento_actual.strftime("%H:%M:%S")
        btn_actualizar_ahora.visible = True

        campo_observaciones.value = borrador.get("observaciones") or ""
        if campo_observaciones.value:
            texto_estado_observacion.value = (
                f"Observación guardada · {len(campo_observaciones.value)} caracteres"
            )
            texto_estado_observacion.color = "#15803D"
        else:
            texto_estado_observacion.value = "Sin observaciones guardadas"
            texto_estado_observacion.color = "#64748B"

        if not secciones_expandidas[seccion_id]:
            secciones_expandidas[seccion_id] = True
            contenidos_seccion[seccion_id].visible = True
            botones_expansion[seccion_id].icon = ft.Icons.KEYBOARD_ARROW_UP_ROUNDED
            botones_expansion[seccion_id].tooltip = "Contraer sección"

        actualizar_resumen_seccion(seccion_id)
        estado = estados_borrador[seccion_id]
        estado.value = (
            "Borrador cargado para edición. Se conservó la fecha y la hora "
            "volvió automáticamente a la actual. Modifica los valores y "
            "guarda la sección para actualizarlo."
        )
        estado.color = "#D97706"
        page.snack_bar = ft.SnackBar(
            ft.Text(
                f"Borrador de {seccion['titulo']} cargado para edición."
            ),
            bgcolor="#D97706",
        )
        page.snack_bar.open = True
        page.update()

    def abrir_observaciones(_):
        campo_observaciones.value = campo_observaciones.value or ""
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
                content=campo_observaciones,
            ),
            actions=[
                ft.OutlinedButton(
                    "Cancelar",
                    on_click=lambda _: cerrar_dialogo(dialogo_observaciones),
                ),
                ft.ElevatedButton(
                    "Guardar observación",
                    icon=ft.Icons.SAVE_OUTLINED,
                    bgcolor=COLOR_PRIMARIO,
                    color="white",
                    on_click=lambda _: guardar_observacion(dialogo_observaciones),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        mostrar_dialogo(dialogo_observaciones)

    def guardar_observacion(dialogo):
        observacion = (campo_observaciones.value or "").strip()
        campo_observaciones.value = observacion
        if observacion:
            texto_estado_observacion.value = (
                f"Observación guardada · {len(observacion)} caracteres"
            )
            texto_estado_observacion.color = "#15803D"
        else:
            texto_estado_observacion.value = "Sin observaciones guardadas"
            texto_estado_observacion.color = "#64748B"

        for borrador in borradores.values():
            borrador["observaciones"] = observacion

        cerrar_dialogo(dialogo)
        actualizar_lista_borradores()
        page.update()

    boton_observaciones = ft.OutlinedButton(
        "Observaciones",
        icon=ft.Icons.NOTES_ROUNDED,
        on_click=abrir_observaciones,
        style=ft.ButtonStyle(
            color=COLOR_PRIMARIO,
            side=ft.BorderSide(1, COLOR_PRIMARIO),
            shape=ft.RoundedRectangleBorder(radius=9),
            padding=ft.Padding.symmetric(horizontal=18, vertical=14),
        ),
    )

    def guardar_borrador_confirmado(seccion, lecturas):
        seccion_id = seccion["id"]
        analizo = analizo_automatico
        if not analizo:
            estado = estados_borrador[seccion_id]
            estado.value = "Ingresa el nombre de quien analizó."
            estado.color = "#B91C1C"
            page.update()
            return

        borradores[seccion_id] = {
            "fecha": obtener_fecha(),
            "hora": obtener_hora(),
            "analizo": analizo,
            "usuario_registro": usuario_logueado,
            "observaciones": (campo_observaciones.value or "").strip(),
            "lecturas": lecturas.copy(),
        }
        checkbox = seleccion_borradores.get(seccion_id)
        if checkbox is None:
            seleccion_borradores[seccion_id] = ft.Checkbox(
                label="Incluir",
                value=True,
                on_change=al_cambiar_seleccion,
            )
        else:
            checkbox.value = True

        estado = estados_borrador[seccion_id]
        estado.value = (
            f"Borrador listo · {len(lecturas)}/{len(seccion['parametros'])} "
            "lecturas. Aún no se ha enviado a la base de datos."
        )
        estado.color = "#475569"
        botones_borrador[seccion_id].disabled = False
        actualizar_lista_borradores()
        page.snack_bar = ft.SnackBar(
            ft.Text(
                f"Borrador de {seccion['titulo']} guardado. "
                "Todavía no se ha enviado a la base de datos."
            ),
            bgcolor="#D97706",
        )
        page.snack_bar.open = True
        page.update()

    def guardar_borrador_seccion(seccion, _):
        seccion_id = seccion["id"]
        try:
            lecturas = validar_lecturas_seccion(
                seccion_id,
                {clave: campo.value for clave, campo in entradas.items()},
            )
        except ValueError as ex:
            estado = estados_borrador[seccion_id]
            estado.value = str(ex)
            estado.color = "#B91C1C"
            page.update()
            return

        desviaciones = obtener_desviaciones(lecturas)
        if not desviaciones:
            guardar_borrador_confirmado(seccion, lecturas)
            return

        filas_desviacion = [
            ft.Container(
                padding=10,
                bgcolor="#FEF2F2",
                border=ft.Border.all(1, "#FECACA"),
                border_radius=8,
                content=ft.Text(
                    f"{item['parametro']}: {item['valor']} {item['unidad']} "
                    f"(control {item['control']})",
                    color="#7F1D1D",
                    size=13,
                ),
            )
            for item in desviaciones
        ]
        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                f"{seccion['titulo']}: lecturas fuera del control",
                color="#991B1B",
                weight=ft.FontWeight.BOLD,
            ),
            content=ft.Container(
                width=500,
                height=min(300, 90 + 50 * len(filas_desviacion)),
                content=ft.Column(
                    [
                        ft.Text(
                            "Revisa estos valores. Puedes corregirlos o "
                            "confirmar el borrador.",
                            color="#475569",
                        ),
                        *filas_desviacion,
                    ],
                    spacing=8,
                ),
            ),
            actions=[
                ft.OutlinedButton(
                    "Volver a revisar",
                    on_click=lambda _: cerrar_dialogo(dialogo),
                ),
                ft.ElevatedButton(
                    "Confirmar borrador",
                    icon=ft.Icons.CHECK_ROUNDED,
                    bgcolor="#D97706",
                    color="white",
                    on_click=lambda _: confirmar_borrador_con_desviaciones(
                        dialogo, seccion, lecturas
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        mostrar_dialogo(dialogo)

    def confirmar_borrador_con_desviaciones(dialogo, seccion, lecturas):
        cerrar_dialogo(dialogo)
        guardar_borrador_confirmado(seccion, lecturas)

    for seccion in SECCIONES:
        botones_borrador[seccion["id"]].on_click = (
            lambda e, item=seccion: guardar_borrador_seccion(item, e)
        )

    def persistir_borradores(secciones_a_enviar):
        secciones_ordenadas = [
            seccion["id"]
            for seccion in SECCIONES
            if seccion["id"] in secciones_a_enviar
        ]
        secciones_a_enviar = set(secciones_ordenadas)
        boton_enviar_borradores.disabled = True
        mensaje_estado.visible = False
        page.update()
        try:
            borradores_a_enviar = [
                borradores[seccion_id] for seccion_id in secciones_a_enviar
            ]
            fechas = {borrador["fecha"] for borrador in borradores_a_enviar}
            if len(fechas) != 1:
                raise ValueError(
                    "Envía por separado los borradores que tengan distintas fechas."
                )
            lecturas = [
                lectura
                for borrador in borradores_a_enviar
                for lectura in borrador["lecturas"]
            ]
            validar_lecturas_seleccionadas(lecturas, secciones_a_enviar)
            primer_borrador = borradores_a_enviar[0]

            observaciones_registro = (
                campo_observaciones.value or ""
            ).strip()

            if not observaciones_registro:
                for borrador in borradores_a_enviar:
                    observacion_borrador = (
                        borrador.get("observaciones") or ""
                    ).strip()

                    if observacion_borrador:
                        observaciones_registro = observacion_borrador
                        break
            

            id_registro = insertar_registro_bd(
                primer_borrador["fecha"],
                primer_borrador["hora"],
                primer_borrador["analizo"],
                usuario_logueado,
                observaciones_registro,
                lecturas,
                secciones_a_enviar,
            )
        except ValueError as ex:
            mensaje_estado.value = str(ex)
            mensaje_estado.color = "#B91C1C"
            mensaje_estado.visible = True
        except pyodbc.IntegrityError:
            logging.exception("SQL Server rechazó el envío de borradores FMAN-42.")
            mensaje_estado.value = (
                "No se pudo guardar porque ya existe un registro para esa fecha. "
                "Actualiza la aplicación y vuelve a cargar los borradores."
            )
            mensaje_estado.color = "#B91C1C"
            mensaje_estado.visible = True
        except pyodbc.Error:
            logging.exception("Error de SQL Server al guardar el Formulario 2.")
            mensaje_estado.value = (
                "No fue posible guardar los borradores. Verifica la conexión y "
                "que el esquema FMAN-42 ya esté instalado en SQL Server."
            )
            mensaje_estado.color = "#B91C1C"
            mensaje_estado.visible = True
        except RuntimeError:
            logging.exception("No fue posible completar el guardado FMAN-42.")
            mensaje_estado.value = (
                "SQL Server no confirmó el registro. Revisa la configuración "
                "y vuelve a intentarlo."
            )
            mensaje_estado.color = "#B91C1C"
            mensaje_estado.visible = True
        else:
            mensaje_estado.value = (
                f"Borrador(es) enviado(s) correctamente (registro {id_registro})."
            )
            mensaje_estado.color = "#15803D"
            mensaje_estado.visible = True
            for seccion_id in secciones_a_enviar:
                borradores.pop(seccion_id)
                seleccion_borradores.pop(seccion_id)
                estado = estados_borrador[seccion_id]
                estado.value = "Enviado a la base de datos."
                estado.color = "#15803D"
                boton = botones_borrador[seccion_id]
                boton.disabled = True
            actualizar_lista_borradores()
            page.snack_bar = ft.SnackBar(
                ft.Text(
                    f"{len(secciones_a_enviar)} sección(es) enviada(s) "
                    "correctamente a SQL Server."
                ),
                bgcolor="#15803D",
            )
            page.snack_bar.open = True
        finally:
            boton_enviar_borradores.disabled = not any(
                checkbox.value for checkbox in seleccion_borradores.values()
            )
            page.update()

    def enviar_borradores(_):
        secciones_a_enviar = {
            seccion["id"]
            for seccion in SECCIONES
            if seccion["id"] in seleccion_borradores
            and seleccion_borradores[seccion["id"]].value
        }
        if not secciones_a_enviar:
            mensaje_estado.value = "Selecciona al menos un borrador para enviar."
            mensaje_estado.color = "#B91C1C"
            mensaje_estado.visible = True
            page.update()
            return

        borradores_seleccionados = [
            borradores[seccion_id] for seccion_id in secciones_a_enviar
        ]
        if len({borrador["fecha"] for borrador in borradores_seleccionados}) != 1:
            mensaje_estado.value = (
                "Envía por separado los borradores que tengan distintas fechas."
            )
            mensaje_estado.color = "#B91C1C"
            mensaje_estado.visible = True
            page.update()
            return

        lecturas = [
            lectura
            for borrador in borradores_seleccionados
            for lectura in borrador["lecturas"]
        ]
        desviaciones = obtener_desviaciones(lecturas)
        if not desviaciones:
            persistir_borradores(secciones_a_enviar)
            return

        filas_desviacion = [
            ft.Container(
                padding=10,
                bgcolor="#FEF2F2",
                border=ft.Border.all(1, "#FECACA"),
                border_radius=8,
                content=ft.Text(
                    f"{item['seccion']} · {item['parametro']}: {item['valor']} "
                    f"{item['unidad']} (control {item['control']})",
                    color="#7F1D1D",
                    size=13,
                ),
            )
            for item in desviaciones
        ]
        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                f"{len(desviaciones)} lectura(s) fuera del control",
                color="#991B1B",
                weight=ft.FontWeight.BOLD,
            ),
            content=ft.Container(
                width=560,
                height=320,
                content=ft.Column(
                    [
                        ft.Text(
                            "Revisa las desviaciones. Puedes regresar a corregir "
                            "o confirmar el envío a la base de datos.",
                            size=13,
                            color="#475569",
                        ),
                        *filas_desviacion,
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
                    on_click=lambda _: confirmar_envio_con_desviaciones(
                        dialogo, secciones_a_enviar
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        mostrar_dialogo(dialogo)

    def confirmar_envio_con_desviaciones(dialogo, secciones_a_enviar):
        cerrar_dialogo(dialogo)
        persistir_borradores(secciones_a_enviar)

    boton_enviar_borradores.on_click = enviar_borradores

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
            content=ft.Container(
                width=450,
                content=ft.Text(
                    "Los borradores y cambios que no hayas enviado a la base "
                    "de datos se perderán al volver al menú.",
                    size=13,
                    color="#334155",
                ),
            ),
            actions=[
                ft.OutlinedButton(
                    "Cancelar",
                    on_click=lambda _: cerrar_dialogo(dialogo),
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=8)
                    ),
                ),
                ft.ElevatedButton(
                    "Sí, Continuar y Salir",
                    on_click=lambda _: salir(dialogo),
                    bgcolor="#DC2626",
                    color="white",
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=8)
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=12),
        )
        mostrar_dialogo(dialogo)

    def salir(dialogo):
        detener_formulario()
        cerrar_dialogo(dialogo)
        on_logout()

    txt_marquee = ft.Text(
        "",
        size=16,
        color="#F8FAFC",
        weight=ft.FontWeight.BOLD,
        no_wrap=True,
    )

    def animar_marquee():
        texto = (
            f" FMAN-42 MONITOREO DE AGUAS DE CALDERA • "
            f"          ✦                    "
            f" ALIMENTACIÓN CALDERA • "
            f"          ✦                    "
            f" PURGA CALDERA #1 • "
            f"          ✦                    "
            f" PURGA CALDERA #2 • "
            f"          ✦                    "
            f" PURGA CALDERA #3 • "
            f"          ✦                    "
            f" RESPONSABLE: {nombre_completo} • "
            f"          ✦                    "
            f" USUARIO: {usuario_logueado} • "
            f"          ✦                    "
            f" CRYSTAL S.A.S • "
            f"          ✦                    "
        ) * 8

        while formulario_activo:
            try:
                texto = texto[1:] + texto[0]
                txt_marquee.value = texto
                txt_marquee.update()
            except Exception:
                logging.exception("Se detuvo la animación del encabezado.")
                detener_formulario()
                break
            time.sleep(0.08)

    txt_reloj_encabezado = ft.Text(
        ahora.strftime("%H:%M:%S"),
        size=17,
        color=COLOR_PRIMARIO,
        weight=ft.FontWeight.BOLD,
    )

    def actualizar_fecha_hora():
        while formulario_activo:
            try:
                momento = datetime.datetime.now()
                txt_reloj_encabezado.value = momento.strftime("%H:%M:%S")
                txt_reloj_encabezado.update()
                if not fecha_fijada:
                    txt_fecha.value = momento.strftime("%Y-%m-%d")
                    txt_fecha.update()
                if not hora_fijada:
                    txt_hora.value = momento.strftime("%H:%M:%S")
                    txt_hora.update()
            except Exception:
                logging.exception("Se detuvo la actualización de fecha y hora.")
                detener_formulario()
                break
            time.sleep(1)

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
                    tooltip="Volver al inicio",
                    on_click=confirmar_salida,
                ),
                ft.Row(
                    [
                        ft.Image(
                            src="logo-crystal.png",
                            width=180,
                            height=60,
                            fit=ft.BoxFit.CONTAIN,
                        ),
                        ft.Container(
                            expand=True,
                            height=70,
                            bgcolor="#0F172A",
                            border_radius=10,
                            padding=12,
                            alignment=ft.Alignment.CENTER_LEFT,
                            content=txt_marquee,
                        ),
                    ],
                    spacing=15,
                ),
                ft.Divider(),
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(
                                    "MONITOREO DE AGUAS DE CALDERA",
                                    size=24,
                                    weight=ft.FontWeight.BOLD,
                                    color=COLOR_PRIMARIO,
                                ),
                                ft.Text(
                                    "Monitoreo y control de aguas de caldera",
                                    color="#475569",
                                ),
                                ft.Text(
                                    f"{nombre_completo} ({usuario_logueado})",
                                    color="#475569",
                                    size=12,
                                ),
                            ],
                            spacing=4,
                            expand=True,
                        ),
                        ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.ACCESS_TIME_ROUNDED,
                                            color=COLOR_PRIMARIO,
                                            size=24,
                                        ),
                                        txt_reloj_encabezado,
                                    ],
                                    spacing=7,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                ),
                                ft.Container(
                                    padding=ft.Padding.symmetric(
                                        horizontal=14, vertical=7
                                    ),
                                    border=ft.Border.all(1.5, COLOR_PRIMARIO),
                                    border_radius=9,
                                    alignment=ft.Alignment.CENTER,
                                    content=ft.Text(
                                        "FMAN-42",
                                        size=15,
                                        weight=ft.FontWeight.BOLD,
                                        color=COLOR_PRIMARIO,
                                    ),
                                ),
                            ],
                            spacing=6,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=8,
        ),
    )

    barra_fecha_hora = ft.Container(
        bgcolor="white",
        border_radius=12,
        padding=18,
        border=ft.Border.all(1, COLOR_BORDE),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.CALENDAR_MONTH_ROUNDED,
                                            size=16,
                                            color=COLOR_TITULO,
                                        ),
                                        ft.Text(
                                            "Fecha de Medición (Operación):",
                                            size=13,
                                            weight=ft.FontWeight.BOLD,
                                            color=COLOR_TITULO,
                                        ),
                                    ],
                                    spacing=6,
                                ),
                                ft.Row(
                                    [
                                        txt_fecha,
                                        ft.IconButton(
                                            icon=ft.Icons.CALENDAR_TODAY_ROUNDED,
                                            icon_color=COLOR_PRIMARIO,
                                            tooltip="Seleccionar fecha (máximo 4 días atrás)",
                                            on_click=lambda _: abrir_selector(
                                                date_picker
                                            ),
                                        ),
                                    ],
                                    spacing=2,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                            ],
                            spacing=6,
                            expand=True,
                        ),
                        ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.ACCESS_TIME_ROUNDED,
                                            size=16,
                                            color=COLOR_TITULO,
                                        ),
                                        ft.Text(
                                            "Hora de Medición (Operación):",
                                            size=13,
                                            weight=ft.FontWeight.BOLD,
                                            color=COLOR_TITULO,
                                        ),
                                    ],
                                    spacing=6,
                                ),
                                ft.Row(
                                    [
                                        txt_hora,
                                        ft.IconButton(
                                            icon=ft.Icons.ACCESS_TIME_ROUNDED,
                                            icon_color=COLOR_PRIMARIO,
                                            tooltip="Seleccionar hora",
                                            on_click=lambda _: abrir_selector(
                                                time_picker
                                            ),
                                        ),
                                    ],
                                    spacing=2,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                            ],
                            spacing=6,
                            expand=True,
                        ),
                    ],
                    spacing=18,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [btn_actualizar_ahora],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            spacing=8,
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
                    "El formato indica una medición diaria. Registra los 36 "
                    "parámetros; los criterios se evalúan al ingresar cada valor.",
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
                    "Guarda cada sección como borrador y selecciona cuáles "
                    "enviar. Los borradores se conservan mientras el formulario "
                    "permanezca abierto.",
                    size=13,
                    color="#475569",
                ),
                estado_vacio_borradores,
                columna_borradores,
                ft.Row(
                    [boton_enviar_borradores],
                    alignment=ft.MainAxisAlignment.END,
                ),
                mensaje_estado,
            ],
            spacing=10,
        ),
    )

    pagina = ft.Container(
        expand=True,
        padding=10,
        content=ft.Column(
            controls=[
                encabezado,
                barra_fecha_hora,
                introduccion,
                *tarjetas_seccion,
                panel_borradores,
                ft.Container(
                    padding=18,
                    bgcolor="white",
                    border=ft.Border.all(1, COLOR_BORDE),
                    border_radius=14,
                    content=ft.Column(
                        [
                            ft.Text(
                                "Observaciones de la medición",
                                size=17,
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TITULO,
                            ),
                            ft.Row(
                                [boton_observaciones, texto_estado_observacion],
                                spacing=12,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                wrap=True,
                            ),
                            ft.Text(
                                "La frecuencia de verificación y los campos de "
                                "firma del Excel pertenecen al cierre mensual.",
                                size=12,
                                color="#475569",
                            ),
                        ],
                        spacing=12,
                    ),
                ),
            ],
            tight=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=14,
        ),
    )
    page.add(pagina)
    page.update()
    threading.Thread(target=animar_marquee, daemon=True).start()
    threading.Thread(target=actualizar_fecha_hora, daemon=True).start()