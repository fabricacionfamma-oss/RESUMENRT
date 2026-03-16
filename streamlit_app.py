import streamlit as st
import pandas as pd
from fpdf import FPDF
import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
# Usamos un layout centrado para que se vea más limpio
st.set_page_config(page_title="Generador de Reportes", layout="centered")

st.title("📄 Reporte de Retrabajo")
st.markdown("Selecciona el rango de fechas para generar y descargar tu reporte en PDF.")

# --- CARGA DE DATOS ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1l6a6ab82p_Nm0g0RdprVR7AWSvMgYjRp-16M1210hMU/export?format=csv&gid=1779842834"

@st.cache_data(ttl=600)
def load_data(url):
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip() 
    return df

try:
    df = load_data(SHEET_URL)
    
    # Convertir a formatos correctos
    df['Fecha'] = pd.to_datetime(df['Fecha'], format='%d/%m/%Y', errors='coerce')
    df['Cantidad de Piezas OK'] = pd.to_numeric(df['Cantidad de Piezas OK'], errors='coerce').fillna(0)
    df['Cantidad de Pieza Scrap'] = pd.to_numeric(df['Cantidad de Pieza Scrap'], errors='coerce').fillna(0)
    
    # Crear columna de total por fila para facilitar los cálculos del Top 15
    df['Total Piezas Fila'] = df['Cantidad de Piezas OK'] + df['Cantidad de Pieza Scrap']
    
    # Asegurar que la columna de piezas sea texto
    df['Que pieza va a retrabajar?'] = df['Que pieza va a retrabajar?'].fillna('Sin especificar').astype(str)

except Exception as e:
    st.error(f"Error general al conectarse con el Google Sheet. Detalles: {e}")
    st.stop()

# --- FILTROS DE FECHA ---
col1, col2 = st.columns(2)

min_date = df['Fecha'].min().date() if pd.notnull(df['Fecha'].min()) else datetime.date.today()
max_date = df['Fecha'].max().date() if pd.notnull(df['Fecha'].max()) else datetime.date.today()

with col1:
    fecha_inicio = st.date_input("Fecha de Inicio", min_date)
with col2:
    fecha_fin = st.date_input("Fecha de Fin", max_date)

# Filtrar dataframe
mask = (df['Fecha'].dt.date >= fecha_inicio) & (df['Fecha'].dt.date <= fecha_fin)
df_filtrado = df.loc[mask].copy()

if df_filtrado.empty:
    st.warning("No hay datos para el rango de fechas seleccionado.")
    st.stop()

# --- CÁLCULOS PARA EL PDF ---
# 1. Calcular el tiempo de RT (Fin - Inicio)
def calcular_horas(df, col_inicio, col_fin):
    try:
        inicio = pd.to_timedelta(df[col_inicio].astype(str).str.strip() + ':00', errors='coerce')
        fin = pd.to_timedelta(df[col_fin].astype(str).str.strip() + ':00', errors='coerce')
        diferencia = (fin - inicio).dt.total_seconds() / 3600.0
        diferencia = diferencia.apply(lambda x: x + 24 if x < 0 else x) # Por si pasa la medianoche
        return diferencia.fillna(0)
    except:
        return pd.Series([0] * len(df))

df_filtrado['Tiempo de RT (hrs)'] = calcular_horas(df_filtrado, 'Inicio del Retrabajo', 'Fin del retrabajo')

# Totales Superiores
total_ok = df_filtrado['Cantidad de Piezas OK'].sum()
total_scrap = df_filtrado['Cantidad de Pieza Scrap'].sum()
total_piezas_retrabajadas = total_ok + total_scrap
total_tiempo_rt = df_filtrado['Tiempo de RT (hrs)'].sum()

# 2. Top 15 Piezas Retrabajadas
top_15_piezas = df_filtrado.groupby('Que pieza va a retrabajar?')['Total Piezas Fila'].sum().reset_index()
top_15_piezas = top_15_piezas.sort_values(by='Total Piezas Fila', ascending=False).head(15)

# 3. Listado de Piezas con Scrap
piezas_scrap = df_filtrado.groupby('Que pieza va a retrabajar?')['Cantidad de Pieza Scrap'].sum().reset_index()
# Filtramos solo las que tienen scrap mayor a 0 y ordenamos de mayor a menor
piezas_scrap = piezas_scrap[piezas_scrap['Cantidad de Pieza Scrap'] > 0].sort_values(by='Cantidad de Pieza Scrap', ascending=False)

# --- GENERACIÓN DEL PDF ---
def generar_pdf():
    pdf = FPDF()
    pdf.add_page()
    
    # Título y Periodo
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.cell(0, 10, "Reporte de Retrabajo de Piezas", ln=True, align='C')
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 10, f"Periodo: {fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}", ln=True, align='C')
    pdf.ln(5)
    
    # ---------------------------------------------------------
    # SECCIÓN 1: TOTALES GLOBALES
    # ---------------------------------------------------------
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(0, 10, "1. Resumen Global", ln=True)
    pdf.set_font("Helvetica", size=11)
    
    # Dibujamos un pequeño cuadro de resumen
    pdf.cell(80, 8, "Total de Piezas Retrabajadas:", border=0)
    pdf.cell(40, 8, str(int(total_piezas_retrabajadas)), border=0, ln=True)
    
    pdf.cell(80, 8, "Total Piezas OK:", border=0)
    pdf.cell(40, 8, str(int(total_ok)), border=0, ln=True)
    
    pdf.cell(80, 8, "Total Piezas Scrap:", border=0)
    pdf.cell(40, 8, str(int(total_scrap)), border=0, ln=True)
    
    pdf.cell(80, 8, "Tiempo Total de RT (Hrs):", border=0)
    pdf.cell(40, 8, f"{total_tiempo_rt:.2f}", border=0, ln=True)
    pdf.ln(5)
    
    # ---------------------------------------------------------
    # SECCIÓN 2: TOP 15 PIEZAS RETRABAJADAS
    # ---------------------------------------------------------
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(0, 10, "2. Top 15 Piezas Retrabajadas", ln=True)
    
    # Encabezados de tabla
    pdf.set_font("Helvetica", style="B", size=10)
    pdf.cell(140, 8, "Nombre de la Pieza", border=1, align='C')
    pdf.cell(40, 8, "Cantidad Total", border=1, align='C', ln=True)
    
    # Filas de tabla
    pdf.set_font("Helvetica", size=9)
    for _, row in top_15_piezas.iterrows():
        # Truncar el nombre de la pieza a 80 caracteres para que no rompa la tabla
        nombre_pieza = str(row['Que pieza va a retrabajar?'])[:80] 
        cantidad = str(int(row['Total Piezas Fila']))
        
        pdf.cell(140, 8, nombre_pieza, border=1)
        pdf.cell(40, 8, cantidad, border=1, align='C', ln=True)
    
    pdf.ln(5)
    
    # ---------------------------------------------------------
    # SECCIÓN 3: PIEZAS QUE GENERARON SCRAP
    # ---------------------------------------------------------
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(0, 10, "3. Listado de Piezas con Scrap", ln=True)
    
    if piezas_scrap.empty:
        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 10, "No se registraron piezas con Scrap en este periodo.", ln=True)
    else:
        # Encabezados de tabla
        pdf.set_font("Helvetica", style="B", size=10)
        pdf.cell(140, 8, "Nombre de la Pieza", border=1, align='C')
        pdf.cell(40, 8, "Cantidad Scrap", border=1, align='C', ln=True)
        
        # Filas de tabla
        pdf.set_font("Helvetica", size=9)
        for _, row in piezas_scrap.iterrows():
            nombre_pieza = str(row['Que pieza va a retrabajar?'])[:80]
            cantidad_scrap = str(int(row['Cantidad de Pieza Scrap']))
            
            pdf.cell(140, 8, nombre_pieza, border=1)
            pdf.cell(40, 8, cantidad_scrap, border=1, align='C', ln=True)

    # Devolver bytes del PDF
    return bytes(pdf.output())

# --- BOTÓN DE DESCARGA ---
st.write("---")
col_vacia, col_boton, col_vacia2 = st.columns([1, 2, 1])

with col_boton:
    pdf_bytes = generar_pdf()
    st.download_button(
        label="📥 Descargar Reporte en PDF",
        data=pdf_bytes,
        file_name=f"Reporte_Retrabajo_{fecha_inicio}_al_{fecha_fin}.pdf",
        mime="application/pdf",
        use_container_width=True
    )
