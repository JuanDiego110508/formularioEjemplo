# Formularios de Mantenimiento

Aplicación local en Flet. El menú incluye cuatro espacios de formularios; están habilitados el Formulario 1 (FMAN-46, monitoreo de condensados) y el Formulario 2 (FMAN-42, monitoreo de aguas de caldera).

## Requisitos

- Python 3.10 o posterior.
- Microsoft ODBC Driver 17 for SQL Server (en este equipo también está disponible `SQL Server`).
- Acceso a SQL Server, lectura sobre `dbo.Maestro_Permisos_Reportes` y permisos de escritura sobre las tablas de registro de los formularios autorizados.

El proyecto incluye el entorno virtual `.venv` con las dependencias instaladas; `.vscode/settings.json` apunta a él como intérprete predeterminado. Si VS Code conserva otro intérprete seleccionado, elige `.venv\Scripts\python.exe` con **Python: Select Interpreter**. Para ejecutar desde PowerShell, activa el entorno en la terminal integrada y usa ese mismo Python:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Si no quieres activar el entorno, ejecuta directamente su intérprete:

```powershell
.\.venv\Scripts\python.exe app.py
```

En Git Bash, activa el entorno con `source .venv/Scripts/activate`. Si se informa `ModuleNotFoundError: No module named 'flet'`, verifica que el intérprete usado sea `.venv\Scripts\python.exe` y no otro Python instalado en el sistema.

## Configuración de SQL Server

La aplicación usa dos conexiones editables e independientes. Configura los valores al inicio de `conexion.py` para usuarios/permisos y al inicio de `conexionform.py` para registros. En cada archivo puedes cambiar `SERVIDOR`, `BASE_DATOS`, `USUARIO`, `PASSWORD` y `DRIVER`. No hace falta cambiar `app.py`.

La conexión de usuarios apunta por defecto a `Gestion_Humana`; la del formulario, a `Auditoria5S`. Ambas tienen como servidor inicial `10.50.1.24\SQLEXPRESS` y usan el controlador `SQL Server`, que está instalado en este equipo. Sustituye los valores `USUARIO` y `PASSWORD` vacíos por los datos correctos para cada base. Si ambas bases comparten credenciales, copia los mismos valores en los dos archivos.

La app corre en el navegador y solo escucha en esta computadora (`127.0.0.1:8550`). Para cambiar el puerto web, define `export APP_PORT='otro_puerto'` en Bash antes de ejecutar `python app.py`. Mantén `APP_HOST` en `127.0.0.1` para uso local. El driver se define con `DRIVER` y el tiempo de espera con `timeout=15` en cada archivo de conexión.

Los recursos visuales de la aplicación se sirven desde `assets/`. El logo debe estar en `assets/logo-crystal.png`; `app.py` configura esta carpeta como directorio de recursos estáticos de Flet.

No subas las contraseñas reales a Git ni las compartas por el chat.

## Acceso de usuarios

El login consulta `dbo.Maestro_Permisos_Reportes` en `Gestion_Humana`. Para asignar permisos nuevos, usa estos códigos cortos:

- `mante_condensados`: permite abrir el Formulario 1 (FMAN-46).
- `mante_aguas_caldera`: permite abrir el Formulario 2 (FMAN-42).
- `mante_control_caldera`: permite abrir el Formulario 3 (control de purgas de caldera).

El menú comprueba cada permiso por separado. Tener acceso al Formulario 1 no concede acceso al Formulario 2, y viceversa. Un usuario sin ninguno de estos permisos no puede iniciar sesión en esta aplicación. El nombre mostrado proviene de `nombre`; si está vacío se muestra el usuario. Al volver desde un formulario se conservan los permisos que se leyeron al iniciar sesión.

### Asignar permisos de formularios

Los permisos no se asignan desde la pantalla de la aplicación ni en la base de datos de registros `Auditoria5S`. Un administrador de usuarios debe hacerlo en SQL Server, en la base `Gestion_Humana`, tabla `dbo.Maestro_Permisos_Reportes`, o mediante la herramienta interna de administración que mantenga esa tabla. Debe registrar para la cuenta la autorización del reporte con el valor exacto `mante_aguas_caldera`, siguiendo el procedimiento y restricciones existentes de la tabla.

En la tabla, cada fila con un valor de `reporte` representa una autorización para la cuenta identificada por `usuario` y `[contraseña]`. Por eso, normalmente el administrador agrega una fila por cada formulario autorizado. Para dar acceso al Formulario 3, debe registrar el código exacto `mante_control_caldera` para la cuenta y conservar los otros permisos que ya tenga; no debe reemplazarlos. No ejecutes un `INSERT` improvisado: el administrador debe revisar primero las columnas obligatorias, restricciones y procedimiento de altas para evitar duplicar o alterar cuentas.

Para confirmar que el permiso quedó registrado, un administrador puede consultar:

```sql
SELECT id_maestro, usuario, nombre, reporte
FROM dbo.Maestro_Permisos_Reportes
WHERE usuario = 'usuario_de_la_app'
  AND reporte IN (
      'mante_condensados',
      'mante_aguas_caldera',
      'mante_control_caldera'
  )
ORDER BY id_maestro;
```

Reemplaza `usuario_de_la_app` por el usuario con el que la persona inicia sesión en la aplicación. Después de asignarlo, el usuario debe cerrar sesión e iniciar sesión otra vez para que el menú vuelva a cargar sus permisos. No compartas contraseñas por chat ni las incluyas en consultas o scripts guardados.

Por decisión del proyecto, el login usa la columna actual `contraseña varchar(20)` sin migración ni hash. Esto no es adecuado para exponer la aplicación en red o desplegarla fuera del entorno local. Los errores del login no registran la contraseña.

Los registros del Formulario 1 (FMAN-46) se guardan en `Registro_Monitoreo_Condensados_FMAN46`, conservando el nombre de tabla existente.

## Formulario 2 · FMAN-42

El segundo formulario captura hasta 36 lecturas diarias: seis de alimentación de caldera y diez para cada una de las purgas 1, 2 y 3. Cada sección se puede guardar primero como borrador temporal; antes del envío se eligen las secciones que irán a SQL Server. Los borradores viven en memoria mientras el formulario permanezca abierto. La base admite envíos parciales de secciones para la misma fecha, pero no permite volver a enviar una sección ya almacenada ese día. Los criterios de control se basan en la fila «Parámetro de control» del Excel adjunto. Las celdas sin comparador explícito (conductividad de alimentación y Alc. M de alimentación) se muestran como referencia y no se califican como aprobadas o desaprobadas. Las lecturas con criterio usan límites inclusivos para rangos y operadores estrictos para `<`, `>` e igualdad exacta para `= 0`.

El esquema SQL Server se encuentra en `sql/formulario_2_fman42.sql`. Ejecútalo una vez en `Auditoria5S` antes de guardar registros. Usa una sola fila por fecha con las lecturas de las cuatro secciones; los envíos parciales completan esa fila y no permiten reenviar una sección ya guardada ese día. Las lecturas admiten hasta ocho dígitos enteros y dos decimales (`DECIMAL(10,2)`). La fecha ya contiene mes y año; no se guardan duplicados de esos datos. Los campos de verificación y firma que aparecen al pie de la hoja Excel corresponden al cierre mensual y no se solicitan en cada captura diaria.

## Formulario 3 · Control de purgas de caldera

El tercer formulario captura una vez cada turno (1, 2 y 3) por fecha y hora de operación. Cada turno incluye pH, Alcalinidad M, Color y Soda adicionada para las purgas de las calderas 1 y 2, además de los nombres de Entrega y Recibe. La fecha y la hora pueden elegirse; de forma predeterminada se actualizan con la hora actual. El Color se captura como texto breve; Soda acepta hasta dos decimales. pH se controla entre 10,5 y 11,5 y Alcalinidad M tiene un máximo de 500 ppm. Las desviaciones se muestran para revisión y requieren confirmación antes de enviar.

Los turnos pueden guardarse como borradores temporales, cargarse para edición y enviarse por separado o juntos si corresponden a la misma fecha. Cada turno se almacena en una fila de `dbo.Registro_Control_Purgas_Caldera`; la combinación de fecha y turno es única y cada fila conserva su hora. Ejecuta `sql/formulario_3_control_caldera.sql` en `Auditoria5S` antes del primer envío. El borrador solo permanece en memoria mientras el formulario esté abierto.
