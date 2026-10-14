CREATE TABLE dbo.Registro_Control_Agua_Soda_22F010
(
    id_registro INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    fecha DATE NOT NULL,
    hora TIME(0) NOT NULL,
    caldera VARCHAR(50) NOT NULL,
    medidor_agua DECIMAL(12,2) NOT NULL,
    ph DECIMAL(4,2) NOT NULL,
    consumo_soda DECIMAL(12,2) NOT NULL,
    responsable VARCHAR(100) NOT NULL,
    usuario_registro VARCHAR(100) NOT NULL,
    observaciones VARCHAR(1000) NULL

    CONSTRAINT PK_Registro_Control_Agua_Soda_22F010
        PRIMARY KEY (id_registro)
);