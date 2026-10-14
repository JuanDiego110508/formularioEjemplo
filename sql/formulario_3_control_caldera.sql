CREATE TABLE dbo.Registro_Control_Purgas_Caldera

(
    id_registro INT IDENTITY(1,1) PRIMARY KEY,

    fecha DATE NOT NULL,
    hora TIME NOT NULL,

    purga_1_ph DECIMAL(10,2),
    purga_1_alcalinidad_m DECIMAL(10,2),
    purga_1_color VARCHAR(50),
    purga_1_soda_g DECIMAL(10,2),

    purga_2_ph DECIMAL(10,2),
    purga_2_alcalinidad_m DECIMAL(10,2),
    purga_2_color VARCHAR(50),
    purga_2_soda_g DECIMAL(10,2),

    usuario_registro VARCHAR(100) NOT NULL
);