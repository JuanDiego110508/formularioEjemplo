USE [Auditoria5S];
GO

IF OBJECT_ID(N'dbo.Registro_Control_Purgas_Caldera', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Registro_Control_Purgas_Caldera (
        id_registro INT IDENTITY(1,1) NOT NULL,
        fecha DATE NOT NULL,
        hora TIME(0) NOT NULL,
        turno TINYINT NOT NULL,
        purga_1_ph DECIMAL(10,2) NOT NULL,
        purga_1_alcalinidad_m DECIMAL(10,2) NOT NULL,
        purga_1_color NVARCHAR(50) NOT NULL,
        purga_1_soda_g DECIMAL(10,2) NOT NULL,
        purga_2_ph DECIMAL(10,2) NOT NULL,
        purga_2_alcalinidad_m DECIMAL(10,2) NOT NULL,
        purga_2_color NVARCHAR(50) NOT NULL,
        purga_2_soda_g DECIMAL(10,2) NOT NULL,
        entrega NVARCHAR(100) NOT NULL,
        recibe NVARCHAR(100) NOT NULL,
        usuario_registro NVARCHAR(100) NOT NULL,
        CONSTRAINT PK_Registro_Control_Purgas_Caldera
            PRIMARY KEY CLUSTERED (id_registro),
        CONSTRAINT UQ_Registro_Control_Purgas_Caldera_Fecha_Turno
            UNIQUE (fecha, turno),
        CONSTRAINT CK_Registro_Control_Purgas_Caldera_Turno
            CHECK (turno IN (1, 2, 3))
    );
END;
GO
