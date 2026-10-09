USE [Auditoria5S];
GO

IF OBJECT_ID(N'dbo.Registro_Monitoreo_Aguas_Caldera_FMAN42', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Registro_Monitoreo_Aguas_Caldera_FMAN42 (
        id_registro INT IDENTITY(1,1) NOT NULL,
        fecha DATE NOT NULL,
        hora TIME(0) NOT NULL,
        analizo NVARCHAR(100) NOT NULL,
        usuario_registro NVARCHAR(100) NOT NULL,
        observaciones NVARCHAR(1000) NULL,
        alimentacion_caldera_ph DECIMAL(10,2) NULL,
        alimentacion_caldera_std DECIMAL(10,2) NULL,
        alimentacion_caldera_conductividad DECIMAL(10,2) NULL,
        alimentacion_caldera_dureza DECIMAL(10,2) NULL,
        alimentacion_caldera_temperatura DECIMAL(10,2) NULL,
        alimentacion_caldera_alcalinidad_m DECIMAL(10,2) NULL,
        purga_caldera_1_ph DECIMAL(10,2) NULL,
        purga_caldera_1_std DECIMAL(10,2) NULL,
        purga_caldera_1_conductividad DECIMAL(10,2) NULL,
        purga_caldera_1_dureza DECIMAL(10,2) NULL,
        purga_caldera_1_hierro DECIMAL(10,2) NULL,
        purga_caldera_1_silice DECIMAL(10,2) NULL,
        purga_caldera_1_sulfitos DECIMAL(10,2) NULL,
        purga_caldera_1_alcalinidad_m DECIMAL(10,2) NULL,
        purga_caldera_1_alcalinidad_p DECIMAL(10,2) NULL,
        purga_caldera_1_alcalinidad_oh DECIMAL(10,2) NULL,
        purga_caldera_2_ph DECIMAL(10,2) NULL,
        purga_caldera_2_std DECIMAL(10,2) NULL,
        purga_caldera_2_conductividad DECIMAL(10,2) NULL,
        purga_caldera_2_dureza DECIMAL(10,2) NULL,
        purga_caldera_2_hierro DECIMAL(10,2) NULL,
        purga_caldera_2_silice DECIMAL(10,2) NULL,
        purga_caldera_2_sulfitos DECIMAL(10,2) NULL,
        purga_caldera_2_alcalinidad_m DECIMAL(10,2) NULL,
        purga_caldera_2_alcalinidad_p DECIMAL(10,2) NULL,
        purga_caldera_2_alcalinidad_oh DECIMAL(10,2) NULL,
        purga_caldera_3_ph DECIMAL(10,2) NULL,
        purga_caldera_3_std DECIMAL(10,2) NULL,
        purga_caldera_3_conductividad DECIMAL(10,2) NULL,
        purga_caldera_3_dureza DECIMAL(10,2) NULL,
        purga_caldera_3_hierro DECIMAL(10,2) NULL,
        purga_caldera_3_silice DECIMAL(10,2) NULL,
        purga_caldera_3_sulfitos DECIMAL(10,2) NULL,
        purga_caldera_3_alcalinidad_m DECIMAL(10,2) NULL,
        purga_caldera_3_alcalinidad_p DECIMAL(10,2) NULL,
        purga_caldera_3_alcalinidad_oh DECIMAL(10,2) NULL,
        CONSTRAINT PK_Registro_Aguas_Caldera_FMAN42
            PRIMARY KEY CLUSTERED (id_registro),
        CONSTRAINT UQ_Registro_Aguas_Caldera_FMAN42_Fecha
            UNIQUE (fecha)
    );
END;
GO
