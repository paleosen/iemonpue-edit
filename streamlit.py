import streamlit as st
import pandas as pd
import numpy as np
from streamlit_sortables import sort_items
import io

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Data Processor Satker", layout="wide")

# CSS Tambahan untuk UI yang lebih stabil
st.markdown("""
    <style>
    .stMultiSelect span {
        white-space: normal !important;
        height: auto !important;
    }
    /* Mengurangi padding berlebih untuk stabilitas visual */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 1. FUNGSI PROCESSING DENGAN CACHE ---
@st.cache_data(show_spinner=False)
def process_dataframe(df, col_kode, col_uraian):
    df = df.copy()
    df['satker'] = None
    df['jenispekerjaan'] = None
    current_satker = None
    current_jenis = None
    indices_to_drop = []

    for index, row in df.iterrows():
        kode_raw = str(row[col_kode]).strip() if pd.notna(row[col_kode]) else ""
        uraian_val = str(row[col_uraian]) if pd.notna(row[col_uraian]) else ""
        dot_count = kode_raw.count('.')
        
        if kode_raw != "":
            if dot_count == 0:
                current_satker = uraian_val
                current_jenis = None 
                indices_to_drop.append(index)
            elif dot_count == 3:
                current_jenis = uraian_val
                indices_to_drop.append(index)
            else:
                df.at[index, 'satker'] = current_satker
                df.at[index, 'jenispekerjaan'] = current_jenis
        else:
            indices_to_drop.append(index)

    df_clean = df.drop(indices_to_drop).reset_index(drop=True)
    cols_original = [c for c in df_clean.columns if c not in ['satker', 'jenispekerjaan']]
    df_clean = df_clean[cols_original + ['satker', 'jenispekerjaan']]
    return df_clean

def mapping_unor(df, lists):
    df = df.copy()
    # Pre-calculate mapping for speed
    reverse_mapping = {}
    for group, items in lists.items():
        if group == 'Daftar Satker': continue
        for item in items:
            reverse_mapping[item] = group

    def check_unor(val):
        return reverse_mapping.get(val, 'Lainnya')

    if 'satker' in df.columns:
        df['unor'] = df['satker'].apply(check_unor)
        mask_pemda = df['unor'] == 'Pemda'
        valid_unors = df['unor'].mask(df['unor'].isin(['Pemda', 'Lainnya']))
        df.loc[mask_pemda, 'unor'] = valid_unors.bfill()
        df['unor'] = df['unor'].fillna('Pemda')
    return df

# --- INTERFACE STREAMLIT ---
st.title("📊 Data Processor Satker & Unor")

uploaded_file = st.file_uploader("Upload file Excel (data.xlsx)", type=["xlsx"])

if uploaded_file:
    # Membaca data dengan cache. 
    # Gunakan hash uploaded_file agar hanya reload jika file berubah.
    df_raw = pd.read_excel(uploaded_file)
    df_processed = process_dataframe(df_raw, col_kode='Kode', col_uraian='satker_paket_uraian')
    
    unique_satkers = list(df_processed['satker'].unique())

    # --- BAGIAN DRAG & DROP UNOR ---
    st.subheader("1. Pemetaan Kategori Unor")
    
    # Inisialisasi session state untuk mencegah reset saat interaksi lain
    if 'sort_data' not in st.session_state or st.session_state.get('last_file') != uploaded_file.name:
        st.session_state.sort_data = [
            {'header': 'Daftar Satker', 'items': unique_satkers},
            {'header': 'Pemda', 'items': []},
            {'header': 'BM', 'items': []},
            {'header': 'CK', 'items': []},
            {'header': 'SDA', 'items': []},
            {'header': 'PR', 'items': []},
            {'header': 'PS', 'items': []}
        ]
        st.session_state.last_file = uploaded_file.name

    # Render sortable
    # Komponen ini memicu rerun, tapi datanya sekarang terkunci di session_state
    current_sort = sort_items(st.session_state.sort_data, multi_containers=True)
    
    # Hanya perbarui jika ada perubahan nyata untuk mengurangi flickering
    if current_sort != st.session_state.sort_data:
        st.session_state.sort_data = current_sort
    
    mapping_lists = {g['header']: g['items'] for g in st.session_state.sort_data}
    
    st.divider()

    # --- BAGIAN SELEKSI JENIS PEKERJAAN ---
    st.subheader("2. Seleksi & Ekspor")
    
    # Gunakan FORM untuk mencegah reload setiap kali user menghapus item di multiselect
    with st.form("proses_data_form"):
        all_jenis = [str(j) for j in df_processed['jenispekerjaan'].unique() if j is not None]
        
        pilihan_aktif = st.multiselect(
            "Filter Jenis Pekerjaan (Item yang dihapus akan dibuang dari hasil akhir):",
            options=all_jenis,
            default=all_jenis
        )
        
        submit_button = st.form_submit_button("🚀 Proses Data dan Siapkan Unduhan")

    if submit_button:
        list_jenis_pekerjaan_dihapus = [j for j in all_jenis if j not in pilihan_aktif]
        
        with st.spinner("Sedang memproses data..."):
            # Jalankan Logika
            df_step_1 = mapping_unor(df_processed, mapping_lists)
            df_step_2 = df_step_1[~df_step_1['jenispekerjaan'].isin(list_jenis_pekerjaan_dihapus)].reset_index(drop=True)
            df_step_2['No'] = range(1, len(df_step_2) + 1)
            
            try:
                df_final = df_step_2[['No','satker_paket_uraian','unor','Tahun','target_vol','target_satuan','jenispekerjaan','satker']].rename(columns={
                    'satker_paket_uraian': 'Uraian Pekerjaan','target_vol': 'Volume','target_satuan': 'Satuan'
                })
                
                st.success("Berhasil diproses!")
                st.dataframe(df_final, use_container_width=True)
                
                # Persiapkan Excel dalam memori
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Data_Proses')
                
                st.download_button(
                    label="📥 Klik di sini untuk Download (.xlsx)",
                    data=output.getvalue(),
                    file_name=f'data_final_{uploaded_file.name}',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                )
            except KeyError as e:
                st.error(f"Kolom Excel tidak sesuai. Pastikan format file benar. Detail: {e}")

else:
    st.info("Silakan upload file Excel untuk memulai.")

# --- SUMBER REFERENSI ---
# Streamlit Inc. (2024). Optimize performance with st.cache_data. Streamlit Documentation. https://docs.streamlit.io/develop/api-reference/caching/st.cache_data
# Facebook. (n.d.). React Error #185: Maximum update depth exceeded. React Documentation. https://reactjs.org/docs/error-decoder.html?invariant=185