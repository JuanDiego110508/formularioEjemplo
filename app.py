import os

import flet as ft

import login
import menu


HOST_WEB = os.getenv("APP_HOST", "127.0.0.1")
PUERTO_WEB = int(os.getenv("APP_PORT", "8550"))
DIRECTORIO_RECURSOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def main(page: ft.Page):
    def mostrar_menu(usuario: str, nombre: str, reportes: frozenset[str]):
        menu.crear_menu(page, usuario, nombre, mostrar_login, reportes)

    def mostrar_login(_=None):
        login.crear_login(page, mostrar_menu)

    mostrar_login()


if __name__ == "__main__":
    ft.app(
        target=main,
        view=ft.AppView.WEB_BROWSER,
        host=HOST_WEB,
        port=PUERTO_WEB,
        assets_dir=DIRECTORIO_RECURSOS,
    )
