import streamlit as st
import pandas as pd
from fpdf import FPDF
import datetime
import matplotlib.pyplot as plt
import os

# --- CONFIGURACIÓN DE PÁGINA ---
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
    
    df['Fecha'] = pd.to_datetime(df['Fecha'], format='%d/%m/%Y', errors='coerce')
    df['Cantidad de Piezas OK'] = pd.to_numeric(df['Cantidad de Piezas OK'], errors='coerce').fillna(0)
    df['Cantidad de Pieza Scrap'] = pd.to_numeric(df['Cantidad de Pieza Scrap'], errors='coerce').fillna(0)
    df['Total Piezas Fila'] = df['Cantidad de Piezas OK'] + df['Cantidad de Pieza Scrap']
    
    columnas_posibles = [
        'Piezas Fiat', 'Piezas Renault', 'Piezas Nissan', 
        'NISSAN SOLDADURA', 'Que pieza va a retrabajar?', 
        'Piezas Renault Soldadura', 'PIEZA'
    ]
    cols_piezas = [col for col in columnas_posibles if col in df.columns]

    def obtener_nombre_pieza(row):
        for col in cols_piezas:
            val = str(row[col]).strip()
            if val and val.lower() not in ['nan', 'none', '']:
                return val
        return 'Sin especificar'

    df['Nombre Pieza'] = df.apply(obtener_nombre_pieza, axis=1)
    
    cols_codigo_rt = [col for col in df.columns if 'Codigo RT' in col]
    def obtener_codigo_rt(row):
        for col in cols_codigo_rt:
            val = str(row[col]).strip()
            if val and val.lower() not in ['nan', 'none', '']:
                return val
        return 'S/D'
        
    df['Codigo RT Maestro'] = df.apply(obtener_codigo_rt, axis=1)
    df['Cliente'] = df['Cliente'].fillna('S/D').astype(str)
    df['Codigo Scrap'] = df['Codigo Scrap'].fillna('S/D').astype(str)

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

mask = (df['Fecha'].dt.date >= fecha_inicio) & (df['Fecha'].dt.date <= fecha_fin)
df_filtrado = df.loc[mask].copy()

if df_filtrado.empty:
    st.warning("No hay datos para el rango de fechas seleccionado.")
    st.stop()

# --- CÁLCULOS PARA EL PDF ---
# Función matematicamente más robusta para leer cualquier formato de hora
def calcular_horas(df, col_inicio, col_fin):
    try:
        inicio_str = df[col_inicio].astype(str).str.strip().replace('nan', '')
        fin_str = df[col_fin].astype(str).str.strip().replace('nan', '')
        
        inicio = pd.to_datetime(inicio_str, errors='coerce')
        fin = pd.to_datetime(fin_str, errors='coerce')
        
        diferencia = (fin - inicio).dt.total_seconds() / 3600.0
        diferencia = diferencia.apply(lambda x: x + 24 if pd.notnull(x) and x < 0 else x) 
        return diferencia.fillna(0)
    except Exception:
        return pd.Series([0.0] * len(df))

df_filtrado['Tiempo de RT (hrs)'] = calcular_horas(df_filtrado, 'Inicio del Retrabajo', 'Fin del retrabajo')

# 1. Totales Superiores
total_ok = df_filtrado['Cantidad de Piezas OK'].sum()
total_scrap = df_filtrado['Cantidad de Pieza Scrap'].sum()
total_piezas_retrabajadas = total_ok + total_scrap
total_tiempo_rt = df_filtrado['Tiempo de RT (hrs)'].sum()

# EXCLUIMOS LOS "SIN ESPECIFICAR"
df_piezas_validas = df_filtrado[df_filtrado['Nombre Pieza'] != 'Sin especificar']

# 2. Agrupación Avanzada del Top 15
top_15_piezas = df_piezas_validas.groupby(['Cliente', 'Nombre Pieza', 'Codigo RT Maestro']).agg(
    Total_Piezas=('Total Piezas Fila', 'sum'),
    OK=('Cantidad de Piezas OK', 'sum'),
    Scrap=('Cantidad de Pieza Scrap', 'sum'),
    Tiempo_RT=('Tiempo de RT (hrs)', 'sum')
).reset_index()
top_15_piezas = top_15_piezas.sort_values(by='Total_Piezas', ascending=False).head(15)

# 3. Listado de Piezas con Scrap
piezas_scrap = df_piezas_validas.groupby(['Cliente', 'Nombre Pieza', 'Codigo Scrap']).agg(
    Cantidad_Scrap=('Cantidad de Pieza Scrap', 'sum')
).reset_index()
piezas_scrap = piezas_scrap[piezas_scrap['Cantidad_Scrap'] > 0].sort_values(by='Cantidad_Scrap', ascending=False)


# --- CREACIÓN DEL GRÁFICO ---
grafico_path = 'grafico_top15.png'
if not top_15_piezas.empty:
    plt.figure(figsize=(10, 5))
    top_15_plot = top_15_piezas.sort_values(by='Total_Piezas', ascending=True)
    nombres_cortos = [str(n)[:25] + "..." if len(str(n)) > 25 else str(n) for n in top_15_plot['Nombre Pieza']]
    
    plt.barh(nombres_cortos, top_15_plot['Total_Piezas'], color='#2c7bb6')
    plt.xlabel('Cantidad Total Retrabajada')
    plt.ylabel('Nombre de la Pieza')
    plt.title('Top 15 Piezas con Mayor Retrabajo')
    plt.tight_layout()
    plt.savefig(grafico_path)
    plt.close()

# --- GENERACIÓN DEL PDF ---
def generar_pdf():
    pdf = FPDF(orientation='L')
    pdf.add_page()
    
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.cell(0, 10, "Reporte de Retrabajo de Piezas", ln=True, align='C')
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 10, f"Periodo: {fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}", ln=True, align='C')
    pdf.ln(5)
    
    # ---------------------------------------------------------
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(0, 10, "1. Resumen Global", ln=True)
    pdf.set_font("Helvetica", size=11)
    
    pdf.cell(70, 7, "Total de Piezas Retrabajadas:", border=0)
    pdf.cell(30, 7, str(int(total_piezas_retrabajadas)), border=0, ln=True)
    
    pdf.cell(70, 7, "Total Piezas OK:", border=0)
    pdf.cell(30, 7, str(int(total_ok)), border=0, ln=True)
    
    pdf.cell(70, 7, "Total Piezas Scrap:", border=0)
    pdf.cell(30, 7, str(int(total_scrap)), border=0, ln=True)
    
    pdf.cell(70, 7, "Tiempo Total de RT (Hrs):", border=0)
    pdf.cell(30, 7, f"{total_tiempo_rt:.2f}", border=0, ln=True)
    pdf.ln(5)
    
    # ---------------------------------------------------------
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(0, 10, "2. Top 15 Piezas Retrabajadas", ln=True)
    
    if top_15_piezas.empty:
        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 10, "No hay registros de piezas validas en este periodo.", ln=True)
    else:
        pdf.set_font("Helvetica", style="B", size=9)
        pdf.cell(30, 8, "Cliente", border=1, align='C')
        pdf.cell(80, 8, "Pieza", border=1, align='C')
        pdf.cell(45, 8, "Cod. RT", border=1, align='C')
        pdf.cell(25, 8, "Cant. OK", border=1, align='C')
        pdf.cell(25, 8, "Scrap", border=1, align='C')
        pdf.cell(25, 8, "Total", border=1, align='C')
        pdf.cell(25, 8, "Tiempo RT", border=1, align='C', ln=True)
        
        pdf.set_font("Helvetica", size=8)
        for _, row in top_15_piezas.iterrows():
            cliente = str(row['Cliente'])[:15]
            pieza = str(row['Nombre Pieza'])[:50] 
            cod_rt = str(row['Codigo RT Maestro'])[:25]
            ok = str(int(row['OK']))
            scrap = str(int(row['Scrap']))
            total = str(int(row['Total_Piezas']))
            tiempo = f"{row['Tiempo_RT']:.2f}h"
            
            pdf.cell(30, 8, cliente, border=1)
            pdf.cell(80, 8, pieza, border=1)
            pdf.cell(45, 8, cod_rt, border=1)
            pdf.cell(25, 8, ok, border=1, align='C')
            pdf.cell(25, 8, scrap, border=1, align='C')
            pdf.cell(25, 8, total, border=1, align='C')
            pdf.cell(25, 8, tiempo, border=1, align='C', ln=True)
            
    # ---------------------------------------------------------
    if os.path.exists(grafico_path):
        pdf.add_page()
        pdf.set_font("Helvetica", style="B", size=12)
        pdf.cell(0, 10, "Gráfico Analítico: Distribución de las Top 15 Piezas", ln=True)
        pdf.image(grafico_path, x=20, w=240)
        os.remove(grafico_path)
    
    # ---------------------------------------------------------
    pdf.add_page() 
    
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(0, 10, "3. Resumen de Scrap", ln=True)
    pdf.ln(2)
    
    if piezas_scrap.empty:
        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 10, "No se registraron piezas con Scrap en este periodo.", ln=True)
    else:
        pdf.set_font("Helvetica", style="B", size=9)
        pdf.cell(30, 8, "Cliente", border=1, align='C')
        pdf.cell(100, 8, "Pieza", border=1, align='C')
        pdf.cell(90, 8, "Motivo (Cod. Scrap)", border=1, align='C')
        pdf.cell(35, 8, "Cant. Scrap", border=1, align='C', ln=True)
        
        pdf.set_font("Helvetica", size=8)
        for _, row in piezas_scrap.iterrows():
            cliente = str(row['Cliente'])[:15]
            pieza = str(row['Nombre Pieza'])[:65]
            motivo = str(row['Codigo Scrap'])[:55]
            cantidad_scrap = str(int(row['Cantidad_Scrap']))
            
            pdf.cell(30, 8, cliente, border=1)
            pdf.cell(100, 8, pieza, border=1)
            pdf.cell(90, 8, motivo, border=1)
            pdf.cell(35, 8, cantidad_scrap, border=1, align='C', ln=True)

    return bytes(pdf.output())

# --- BOTÓN DE DESCARGA ---
st.write("---")
col_vacia, col_boton, col_vacia2 = st.columns([1, 2, 1])

with col_boton:
    pdf_bytes = generar_pdf()
    st.download_button(
        label="📥 Descargar Reporte Completo en PDF",
        data=pdf_bytes,
        file_name=f"Reporte_Retrabajo_{fecha_inicio}_al_{fecha_fin}.pdf",
        mime="application/pdf",
        use_container_width=True
    )
