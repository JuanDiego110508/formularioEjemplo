import os

import flet as ft

import login


COLOR_PRIMARIO = "#1E3A8A"
COLOR_TITULO = "#0F172A"
COLOR_FONDO = "#F1F5F9"
COLOR_TEXTO_SECUNDARIO = "#64748B"
RUTA_LOGO = "logo-crystal.png"


def tiene_permiso_formulario_2(reportes_autorizados: frozenset[str]) -> bool:
    return login.REPORTE_FORMULARIO_20 in reportes_autorizados


def tiene_permiso_formulario_3(reportes_autorizados: frozenset[str]) -> bool:
    return login.REPORTE_FORMULARIO_3 in reportes_autorizados


def crear_menu(
    page: ft.Page,
    usuario: str,
    nombre: str,
    on_logout=None,
    reportes_autorizados: frozenset[str] = frozenset(),
):
    page.controls.clear()
    page.title = "Menú - Formularios de Mantenimiento"
    page.bgcolor = COLOR_FONDO

    def volver_al_menu():
        crear_menu(page, usuario, nombre, on_logout, reportes_autorizados)

    def confirmar_cierre_sesion(_):
        if on_logout is None:
            return

        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text("¿Cerrar sesión?", weight=ft.FontWeight.BOLD),
            content=ft.Text("¿Deseas salir de tu sesión actual?"),
            actions=[
                ft.OutlinedButton(
                    "Cancelar",
                    on_click=lambda _: cerrar_dialogo(dialogo),
                ),
                ft.ElevatedButton(
                    "Cerrar sesión",
                    bgcolor=COLOR_PRIMARIO,
                    color="white",
                    on_click=lambda _: salir_de_sesion(dialogo),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
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

    def salir_de_sesion(dialogo):
        cerrar_dialogo(dialogo)
        on_logout()

    def abrir_formulario_1(_):
        import form_monitoreo_control_aguas_condensado as formulario_19

        formulario_19.abrir_ventana(
            page,
            usuario,
            nombre,
            volver_al_menu,
        )

    def abrir_formulario_2(_):
        if not tiene_permiso_formulario_2(reportes_autorizados):
            page.snack_bar = ft.SnackBar(
                ft.Text("No tienes autorización para abrir el Formulario 2.")
            )
            page.snack_bar.open = True
            page.update()
            return

        import form_monitoreo_control_aguas_caldera as formulario_20

        formulario_20.abrir_ventana(
            page,
            usuario,
            nombre,
            volver_al_menu,
        )

    def abrir_formulario_3(_):
        if not tiene_permiso_formulario_3(reportes_autorizados):
            page.snack_bar = ft.SnackBar(
                ft.Text("No tienes autorización para abrir el Formulario 3.")
            )
            page.snack_bar.open = True
            page.update()
            return

        import form_control_purgas_caldera as formulario_3

        formulario_3.abrir_ventana(
            page,
            usuario,
            nombre,
            volver_al_menu,
        )

    ruta_logo = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", RUTA_LOGO
    )
    if os.path.isfile(ruta_logo):
        logo = ft.Image(
            src=RUTA_LOGO,
            width=176,
            height=64,
            fit=ft.BoxFit.CONTAIN,
            tooltip="Crystal S.A.S.",
        )
    else:
        logo = ft.Text(
            "CRYSTAL S.A.S.",
            size=20,
            weight=ft.FontWeight.BOLD,
            color=COLOR_PRIMARIO,
        )

    formularios = [
        {
            "numero": "1",
            "titulo": "Formulario 1",
            "descripcion": "Monitoreo de condensados · FMAN-46.",
            "icono": ft.Icons.WATER_DROP_OUTLINED,
            "disponible": login.REPORTE_FORMULARIO_19 in reportes_autorizados,
            "implementado": True,
            "on_click": abrir_formulario_1,
        },
        {
            "numero": "2",
            "titulo": "Formulario 2",
            "descripcion": "Monitoreo de aguas de caldera · FMAN-42.",
            "icono": ft.Icons.LOCAL_FIRE_DEPARTMENT_OUTLINED,
            "disponible": tiene_permiso_formulario_2(reportes_autorizados),
            "implementado": True,
            "on_click": abrir_formulario_2,
        },
        {
            "numero": "3",
            "titulo": "Formulario 3",
            "descripcion": "Control de purgas de caldera.",
            "icono": ft.Icons.LOCAL_FIRE_DEPARTMENT_OUTLINED,
            "disponible": tiene_permiso_formulario_3(reportes_autorizados),
            "implementado": True,
            "on_click": abrir_formulario_3,
        },
        {
            "numero": "4",
            "titulo": "Formulario 4",
            "descripcion": "Próximamente disponible.",
            "icono": ft.Icons.PRECISION_MANUFACTURING_OUTLINED,
            "disponible": False,
            "implementado": False,
        },
    ]

    def crear_tarjeta(formulario):
        disponible = formulario["disponible"]
        implementado = formulario["implementado"]
        color_icono = COLOR_PRIMARIO if disponible else "#94A3B8"
        color_estado = (
            "#15803D"
            if disponible
            else COLOR_TEXTO_SECUNDARIO
        )
        texto_estado = (
            "DISPONIBLE"
            if disponible
            else "SIN PERMISO"
            if implementado
            else "EN DESARROLLO"
        )

        return ft.Container(
            width=270,
            height=300,
            padding=22,
            bgcolor="white",
            border=ft.Border.all(
                1.5 if disponible else 1,
                "#BFDBFE" if disponible else "#E2E8F0",
            ),
            border_radius=16,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Text(
                                    formulario["numero"],
                                    size=12,
                                    weight=ft.FontWeight.BOLD,
                                    color=COLOR_PRIMARIO if disponible else "#64748B",
                                ),
                                bgcolor="#EFF6FF" if disponible else "#F1F5F9",
                                border_radius=7,
                                padding=ft.Padding.symmetric(
                                    horizontal=9, vertical=5
                                ),
                            ),
                            ft.Container(expand=True),
                            ft.Icon(
                                ft.Icons.CHECK_CIRCLE_ROUNDED
                                if disponible
                                else ft.Icons.LOCK_OUTLINE_ROUNDED,
                                size=19,
                                color="#16A34A" if disponible else "#94A3B8",
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        width=54,
                        height=54,
                        alignment=ft.Alignment.CENTER,
                        bgcolor="#EFF6FF" if disponible else "#F1F5F9",
                        border_radius=14,
                        content=ft.Icon(
                            formulario["icono"],
                            size=29,
                            color=color_icono,
                        ),
                    ),
                    ft.Text(
                        formulario["titulo"],
                        size=19,
                        weight=ft.FontWeight.BOLD,
                        color=COLOR_TITULO,
                    ),
                    ft.Text(
                        formulario["descripcion"],
                        size=13,
                        color=COLOR_TEXTO_SECUNDARIO,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Row(
                        [
                            ft.Container(
                                width=8,
                                height=8,
                                bgcolor="#22C55E" if disponible else "#94A3B8",
                                border_radius=4,
                            ),
                            ft.Text(
                                texto_estado,
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=color_estado,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.ElevatedButton(
                        "Abrir formulario"
                        if disponible
                        else "Sin permiso"
                        if implementado
                        else "Próximamente",
                        on_click=formulario.get("on_click"),
                        disabled=not disponible,
                        width=float("inf"),
                        bgcolor=COLOR_PRIMARIO if disponible else "#E2E8F0",
                        color="white" if disponible else "#64748B",
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=9),
                            padding=ft.Padding.symmetric(vertical=13),
                        ),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )

    tarjetas = [crear_tarjeta(formulario) for formulario in formularios]
    encabezado = ft.Container(
        padding=ft.Padding.symmetric(horizontal=24, vertical=17),
        bgcolor="white",
        border=ft.Border.all(1, "#E2E8F0"),
        border_radius=16,
        content=ft.Row(
            [
                logo,
                ft.Container(width=1, height=42, bgcolor="#E2E8F0"),
                ft.Column(
                    [
                        ft.Text(
                            "FORMULARIOS DE MANTENIMIENTO",
                            size=17,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_TITULO,
                        ),
                        ft.Text(
                            "Gestión operativa · Crystal S.A.S.",
                            size=12,
                            color=COLOR_TEXTO_SECUNDARIO,
                        ),
                    ],
                    spacing=3,
                    expand=True,
                ),
                ft.Column(
                    [
                        ft.Text(
                            nombre,
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_TITULO,
                            text_align=ft.TextAlign.RIGHT,
                        ),
                        ft.Text(
                            f"Usuario: {usuario}",
                            size=11,
                            color=COLOR_TEXTO_SECUNDARIO,
                            text_align=ft.TextAlign.RIGHT,
                        ),
                    ],
                    spacing=3,
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                ),
                ft.OutlinedButton(
                    "Cerrar sesión",
                    icon=ft.Icons.LOGOUT_ROUNDED,
                    on_click=confirmar_cierre_sesion,
                    disabled=on_logout is None,
                    style=ft.ButtonStyle(
                        color=COLOR_PRIMARIO,
                        side=ft.BorderSide(1, "#CBD5E1"),
                        shape=ft.RoundedRectangleBorder(radius=9),
                        padding=ft.Padding.symmetric(horizontal=15, vertical=12),
                    ),
                ),
            ],
            spacing=18,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    contenido = ft.Container(
        expand=True,
        padding=ft.Padding.symmetric(horizontal=32, vertical=26),
        content=ft.Column(
            [
                encabezado,
                ft.Container(height=12),
                ft.Column(
                    [
                        ft.Text(
                            "CENTRO DE FORMULARIOS",
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_PRIMARIO,
                        ),
                        ft.Text(
                            "Seleccione el formulario de trabajo",
                            size=27,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_TITULO,
                        ),
                        ft.Text(
                            "Acceda a los módulos disponibles para realizar y consultar registros operativos.",
                            size=14,
                            color=COLOR_TEXTO_SECUNDARIO,
                        ),
                    ],
                    spacing=7,
                ),
                ft.Row(
                    controls=tarjetas,
                    spacing=16,
                    run_spacing=16,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.INFO_OUTLINE_ROUNDED,
                            size=16,
                            color=COLOR_TEXTO_SECUNDARIO,
                        ),
                        ft.Text(
                            "Los formularios en desarrollo se habilitarán cuando estén listos para su uso.",
                            size=12,
                            color=COLOR_TEXTO_SECUNDARIO,
                        ),
                    ],
                    spacing=8,
                ),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        ),
    )
    page.add(contenido)
    page.update()
