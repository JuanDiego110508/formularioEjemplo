import pyodbc


# Configuracion de la base que almacena los registros del formulario.
SERVIDOR = "10.50.1.24\\SQLEXPRESS"
BASE_DATOS = "Auditoria5S"
USUARIO = "plc"
PASSWORD = "plc"
DRIVER = "SQL Server"


def _valor_odbc(valor: str) -> str:
    return "{" + valor.replace("}", "}}") + "}"


def obtener_conexion_formulario(base_datos: str | None = None):
    base = base_datos or BASE_DATOS
    cadena_conexion = (
        f"DRIVER={_valor_odbc(DRIVER)};"
        f"SERVER={_valor_odbc(SERVIDOR)};"
        f"DATABASE={_valor_odbc(base)};"
        f"UID={_valor_odbc(USUARIO)};"
        f"PWD={_valor_odbc(PASSWORD)};"
    )
    return pyodbc.connect(cadena_conexion, timeout=15)


def obtener_conexion(base_datos: str | None = None):
    return obtener_conexion_formulario(base_datos)


def conectar_bd():
    return obtener_conexion_formulario()
