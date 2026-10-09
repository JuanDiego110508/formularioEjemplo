import pyodbc


# Configuracion de la base de usuarios y permisos.
SERVIDOR = "10.50.1.24\\SQLEXPRESS"
BASE_DATOS = "Gestion_Humana"
USUARIO = "plc"
PASSWORD = "plc"
DRIVER = "SQL Server"


def _valor_odbc(valor: str) -> str:
    return "{" + valor.replace("}", "}}") + "}"


def obtener_conexion_usuarios():
    cadena_conexion = (
        f"DRIVER={_valor_odbc(DRIVER)};"
        f"SERVER={_valor_odbc(SERVIDOR)};"
        f"DATABASE={_valor_odbc(BASE_DATOS)};"
        f"UID={_valor_odbc(USUARIO)};"
        f"PWD={_valor_odbc(PASSWORD)};"
    )
    return pyodbc.connect(cadena_conexion, timeout=15)


def conectar_bd():
    return obtener_conexion_usuarios()
