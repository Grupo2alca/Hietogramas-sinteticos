import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import pyreadstat
import io
import tempfile

st.set_page_config(page_title="Análisis de Eventos de Lluvia", layout="wide")

st.title("Aplicación de Análisis de Lluvia")

uploaded_file = st.file_uploader("Sube tu archivo .sav de precipitaciones", type=["sav"])

if uploaded_file:
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_file_path = tmp_file.name

    df, meta = pyreadstat.read_sav(tmp_file_path)
    df = df.rename(columns={'valor': 'Precipitacion', 'fecha': 'Fecha'})

    if 'Precipitacion' not in df.columns:
        st.error("La columna 'Precipitacion' no existe en el archivo. Verifica el archivo subido.")
        st.stop()

    fecha_inicio = pd.to_datetime('2000-01-01 00:00:00')
    df['Fecha_Correcta'] = fecha_inicio + pd.to_timedelta(np.arange(len(df)) * 5, unit='min')

    st.subheader("Datos cargados")
    st.dataframe(df[['Fecha_Correcta', 'Precipitacion']])

    threshold = 0
    intervalo = 5

    eventos = []
    evento_actual = []

    for i in range(len(df)):
        if df.loc[i, 'Precipitacion'] > threshold:
            evento_actual.append(df.loc[i])
        else:
            if evento_actual:
                eventos.append(pd.DataFrame(evento_actual))
                evento_actual = []

    if evento_actual:
        eventos.append(pd.DataFrame(evento_actual))

    tabla_eventos = []

    for evento in eventos:
        inicio = evento['Fecha_Correcta'].iloc[0]
        fin = evento['Fecha_Correcta'].iloc[-1]
        duracion_min = len(evento) * intervalo
        ptotal = evento['Precipitacion'].sum()
        idx_max = evento['Precipitacion'].idxmax()
        fecha_max = evento.loc[idx_max, 'Fecha_Correcta']
        p_max = evento.loc[idx_max, 'Precipitacion']

        if duracion_min < 30:
            categoria = '<30 min'
        elif 30 < duracion_min <= 60:
            categoria = '30-60 min'
        elif 60 < duracion_min <= 120:
            categoria = '60-120 min'
        elif 120 < duracion_min <= 180:
            categoria = '120-180 min'
        else:
            categoria = '>180 min'

        tabla_eventos.append({
            'Categoria': categoria,
            'Inicio': inicio,
            'Fin': fin,
            'Duracion (min)': duracion_min,
            'Precipitacion Total': ptotal,
            'Fecha Maxima Precipitacion': fecha_max,
            'Precipitacion Maxima': p_max
        })

    df_eventos = pd.DataFrame(tabla_eventos)

    st.subheader("Tabla de Eventos Detectados")
    st.dataframe(df_eventos)

    conteo_categorias = df_eventos['Categoria'].value_counts().reset_index()
    conteo_categorias.columns = ['Categoria', 'Cantidad de Eventos']

    st.subheader("Conteo de Eventos por Categoría")
    st.dataframe(conteo_categorias)

    categorias = ['<30 min', '30-60 min', '60-120 min', '120-180 min']

    colores_categorias = {
        '<30 min': 'blue',
        '30-60 min': 'green',
        '60-120 min': 'orange',
        '120-180 min': 'red'
    }

    def calcular_hietograma_sintetico(eventos, categoria, intervalo=5):
        eventos_categoria = []
        for evento in eventos:
            duracion = len(evento) * intervalo
            if (categoria == '<30 min' and duracion < 30) or \
               (categoria == '30-60 min' and 30 <= duracion <= 60) or \
               (categoria == '60-120 min' and 60 <= duracion <= 120) or \
               (categoria == '120-180 min' and 120 <= duracion <= 180):
                eventos_categoria.append(evento)

        # Para cada evento en la categoría, se normalizan las precipitaciones
        eventos_normalizados = []
        for evento in eventos_categoria:
            ptotal = evento['Precipitacion'].sum()
            tiempo_norm = np.linspace(0, 1, len(evento))
            lluvia_norm = evento['Precipitacion'].cumsum()/ptotal
            eventos_normalizados.append((tiempo_norm, lluvia_norm))

        curvas_categoria = [curva[1] for curva in eventos_normalizados]

        # Filtrar curvas vacías y con valores NaN
        curvas_categoria = [curva for curva in curvas_categoria if not np.isnan(curva).all()]
        
        # Verificar que no esté vacía antes de promediar
        if len(curvas_categoria) > 0:
            # Eliminar NaN en las curvas antes de calcular el promedio
            curvas_categoria = [np.nan_to_num(curva) for curva in curvas_categoria]
            promedio_categoria = np.nanmean(curvas_categoria, axis=0)
        else:
            promedio_categoria = np.zeros_like(curvas_categoria[0])  # Asignar ceros si está vacío

        return promedio_categoria, eventos_normalizados

    hietogramas_sinteticos = {}

    for cat in categorias:
        promedio_categoria, eventos_normalizados = calcular_hietograma_sintetico(eventos, cat)
        t_norm = np.linspace(0, 1, len(promedio_categoria))
        coef_cat = np.polyfit(t_norm, promedio_categoria, 2)
        polinomio_cat = np.poly1d(coef_cat)
        
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(t_norm, promedio_categoria, label="Promedio Normalizado", color='gray')
        ax.plot(t_norm, polinomio_cat(t_norm), label="Ajuste Polinomial", color='red')
        ax.set_xlabel('Tiempo Normalizado')
        ax.set_ylabel('Precipitación Normalizada')
        ax.grid()
        ax.legend()
        st.pyplot(fig)

        st.subheader(f"Ecuación del Patrón Sintético para {cat}")
        st.latex(f"P^*(t) = {coef_cat[0]:.4f} t^2 + {coef_cat[1]:.4f} t + {coef_cat[2]:.4f}")

        hietogramas_sinteticos[cat] = {
            'promedio': promedio_categoria,
            'ajuste': polinomio_cat
        }

    # Exportación a Excel (sin modificar el formato actual)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_eventos.to_excel(writer, sheet_name='Eventos', index=False)
        for categoria, df_categoria in df_eventos.groupby('Categoria'):
            df_categoria.to_excel(writer, sheet_name=categoria.replace(' ', '_')[:31], index=False)
    
        # Agregar las pestañas de hietogramas sintéticos
        for cat, datos in hietogramas_sinteticos.items():
            df_sintetico = pd.DataFrame({
                'Tiempo Normalizado': np.linspace(0, 1, len(datos['promedio'])),
                'Precipitación Normalizada': datos['promedio'],
                'Ajuste Polinomial': datos['ajuste'](np.linspace(0, 1, len(datos['promedio'])))
            })
            df_sintetico.to_excel(writer, sheet_name=f'Hietograma_{cat.replace(" ", "_")}', index=False)

    output.seek(0)

    st.download_button(
        label="Descargar Eventos y Hietogramas Sintéticos en Excel",
        data=output,
        file_name='eventos_y_hietogramas_sinteticos.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

