import streamlit as st
import pandas as pd
from fpdf import FPDF
import datetime
from io import BytesIO

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Dashboard de Retrabajo", layout="wide")
st.title("Generador de Reportes de Retrabajo")

# --- CARGA DE DATOS ---
# Convertimos tu URL de "edit" a una URL de exportación CSV para que Pandas lo pueda leer
SHEET_URL = "https://docs.google.com/spreadsheets/d/1l6a6ab82p_Nm0g0RdprVR7AWSvMgYjRp-16M1210hMU/export?format=csv&gid=1779842834"

@st.cache_data(ttl=600)  # Actualiza los datos cada 10 minutos
def load_data(url):
    df = pd.read_csv(url)
    
    # Asegurarnos de que las columnas críticas sean numéricas y de fecha
    df['Fecha'] = pd.to_datetime(df['Fecha'], format='%d/%m/%Y', errors='coerce')
    df['Cantidad de Piezas OK'] = pd.to_numeric(df['Cantidad de Piezas OK'], errors='coerce').fillna(0)
    df['Cantidad de Pieza Scrap'] = pd.to_numeric(df['Cantidad de Pieza Scrap'], errors='coerce').fillna(0)
    
    return df

try:
    df = load_data(SHEET_URL)
except Exception as e:
    st.error(f"Error al leer el Google Sheet. Asegúrate de que el documento esté compartido como 'Cualquier usuario con el enlace puede leer'. \nDetalles: {e}")
    st.stop()

# --- FILTROS DE FECHA ---
st.subheader("Filtro por Rango de Fechas")
col1, col2 = st.columns(2)

# Determinar fechas min y max para los selectores
min_date = df['Fecha'].min().date() if pd.notnull(df['Fecha'].min()) else datetime.date.today()
max_date = df['Fecha'].max().date() if pd.notnull(df['Fecha'].max()) else datetime.date.today()

with col1:
    fecha_inicio = st.date_input("Fecha de Inicio", min_date)
with col2:
    fecha_fin = st.date_input("Fecha de Fin", max_date)

# Filtrar el DataFrame
mask = (df['Fecha'].dt.date >= fecha_inicio) & (df['Fecha'].dt.date <= fecha_fin)
df_filtrado = df.loc[mask].copy()

if df_filtrado.empty:
    st.warning("No hay datos para el rango de fechas seleccionado.")
    st.stop()

# --- CÁLCULOS ---
# Función auxiliar para calcular diferencia de horas entre dos columnas (formato HH:MM)
def calcular_horas(df, col_inicio, col_fin):
    try:
        # Convertimos a string, rellenamos y forzamos un formato de timedelta
        inicio = pd.to_timedelta(df[col_inicio].astype(str).str.strip() + ':00', errors='coerce')
        fin = pd.to_timedelta(df[col_fin].astype(str).str.strip() + ':00', errors='coerce')
        # Calculamos la diferencia en horas (considerando que el turno no pase de la medianoche)
        diferencia = (fin - inicio).dt.total_seconds() / 3600.0
        # Si la diferencia es negativa (pasó la medianoche), le sumamos 24 horas
        diferencia = diferencia.apply(lambda x: x + 24 if x < 0 else x)
        return diferencia.fillna(0)
    except:
        return pd.Series([0] * len(df))

# Calcular tiempos de RT y Parada
df_filtrado['Tiempo de RT (hrs)'] = calcular_horas(df_filtrado, 'Inicio del Retrabajo', 'Fin del retrabajo')

# Sumar el tiempo de parada 1 y parada 2
parada1 = calcular_horas(df_filtrado, 'Inicio de Parada', 'Fin de Parada')
parada2 = calcular_horas(df_filtrado, 'Inicio de Parada - 2', 'Fin de Parada - 2')
df_filtrado['Tiempo de Parada (hrs)'] = parada1 + parada2

# Totales globales para el PDF
total_ok = df_filtrado['Cantidad de Piezas OK'].sum()
total_scrap = df_filtrado['Cantidad de Pieza Scrap'].sum()
total_piezas_retrabajadas = total_ok + total_scrap
total_tiempo_rt = df_filtrado['Tiempo de RT (hrs)'].sum()
total_tiempo_parada = df_filtrado['Tiempo de Parada (hrs)'].sum()

# --- VISTA PREVIA ---
st.subheader("Resumen del Periodo")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Piezas Retrabajadas", f"{int(total_piezas_retrabajadas)}")
m2.metric("Total Piezas OK", f"{int(total_ok)}")
m3.metric("Total Piezas Scrap", f"{int(total_scrap)}")
m4.metric("Tiempo Total de RT (hrs)", f"{total_tiempo_rt:.2f}")

st.dataframe(df_filtrado[['Fecha', 'Operador', 'Inicio del Retrabajo', 'Fin del retrabajo', 'Cantidad de Piezas OK', 'Cantidad de Pieza Scrap']])

# --- GENERACIÓN DEL PDF ---
def generar_pdf():
    pdf = FPDF()
    pdf.add_page()
    
    # Encabezado
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.cell(0, 10, "Reporte de Retrabajo de Piezas", ln=True, align='C')
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, f"Periodo: {fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}", ln=True, align='C')
    pdf.ln(10)
    
    # Resumen General
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(0, 10, "Resumen Global:", ln=True)
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, f"- Piezas Retrabajadas Totales: {int(total_piezas_retrabajadas)}", ln=True)
    pdf.cell(0, 10, f"- Cantidad de Piezas OK: {int(total_ok)}", ln=True)
    pdf.cell(0, 10, f"- Cantidad de Piezas Scrap: {int(total_scrap)}", ln=True)
    pdf.cell(0, 10, f"- Tiempo Total de Retrabajo: {total_tiempo_rt:.2f} horas", ln=True)
    pdf.cell(0, 10, f"- Tiempo Total de Parada: {total_tiempo_parada:.2f} horas", ln=True)
    pdf.ln(10)
    
    # Detalle Diario/Registro
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(0, 10, "Detalle de Registros:", ln=True)
    pdf.set_font("Helvetica", size=10)
    
    # Encabezados de tabla
    ancho_cols = [25, 30, 20, 20, 20, 20, 25, 25]
    encabezados = ['Fecha', 'Operador', 'Inicio RT', 'Fin RT', 'Ini Parada', 'Fin Parada', 'Piezas OK', 'Scrap']
    
    for an, enc in zip(ancho_cols, encabezados):
        pdf.cell(an, 10, enc, border=1, align='C')
    pdf.ln()
    
    # Filas de tabla
    pdf.set_font("Helvetica", size=9)
    for _, row in df_filtrado.iterrows():
        fecha_str = row['Fecha'].strftime('%d/%m/%Y') if pd.notnull(row['Fecha']) else ''
        pdf.cell(ancho_cols[0], 10, fecha_str, border=1)
        pdf.cell(ancho_cols[1], 10, str(row['Operador'])[:15], border=1) # Truncar nombre si es largo
        pdf.cell(ancho_cols[2], 10, str(row['Inicio del Retrabajo']), border=1, align='C')
        pdf.cell(ancho_cols[3], 10, str(row['Fin del retrabajo']), border=1, align='C')
        pdf.cell(ancho_cols[4], 10, str(row['Inicio de Parada']), border=1, align='C')
        pdf.cell(ancho_cols[5], 10, str(row['Fin de Parada']), border=1, align='C')
        pdf.cell(ancho_cols[6], 10, str(int(row['Cantidad de Piezas OK'])), border=1, align='C')
        pdf.cell(ancho_cols[7], 10, str(int(row['Cantidad de Pieza Scrap'])), border=1, align='C')
        pdf.ln()

    # Convertir a bytes para la descarga
    return bytes(pdf.output())

# Botón de Descarga
st.subheader("Descargar Reporte")
pdf_bytes = generar_pdf()

st.download_button(
    label="📥 Descargar Reporte en PDF",
    data=pdf_bytes,
    file_name=f"Reporte_Retrabajo_{fecha_inicio}_al_{fecha_fin}.pdf",
    mime="application/pdf"
)
