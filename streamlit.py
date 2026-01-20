import streamlit as st
import pandas as pd
import numpy as np
from streamlit_sortables import sort_items
import io

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Data Processor Satker", layout="wide")

# CSS Tambahan agar pilihan multiselect tidak terpotong
st.markdown("""
    <style>
    .stMultiSelect span {
        white-space: normal !important;
        height: auto !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 1. FUNGSI PROCESSING DENGAN CACHE ---
@st.cache_data
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
    def check_unor(val):
        if val in lists.get('Pemda', []): return 'Pemda'
        if val in lists.get('BM', []):    return 'BM'
        if val in lists.get('CK', []):    return 'CK'
        if val in lists.get('SDA', []):   return 'SDA'
        if val in lists.get('PR', []):    return 'PR'
        if val in lists.get('PS', []):    return 'PS'
        return 'Lainnya'

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
    # Membaca data awal dengan cache agar tidak loop
    df_raw = pd.read_excel(uploaded_file)
    df_processed = process_dataframe(df_raw, col_kode='Kode', col_uraian='satker_paket_uraian')
    
    unique_satkers = list(df_processed['satker'].unique())

    st.divider()
    
    # --- BAGIAN DRAG & DROP UNOR ---
    st.subheader("1. Pemetaan Kategori Unor")
    st.info("Geser Satker ke kategori yang sesuai.")
    
    # Inisialisasi daftar item jika belum ada di session state
    if 'sort_data' not in st.session_state:
        st.session_state.sort_data = [
            {'header': 'Daftar Satker', 'items': unique_satkers},
            {'header': 'Pemda', 'items': []},
            {'header': 'BM', 'items': []},
            {'header': 'CK', 'items': []},
            {'header': 'SDA', 'items': []},
            {'header': 'PR', 'items': []},
            {'header': 'PS', 'items': []}
        ]

    # Render sortable dan simpan hasilnya kembali ke session_state
    # Penggunaan return value langsung dari sort_items sering memicu loop jika tidak hati-hati
    current_sort = sort_items(st.session_state.sort_data, multi_containers=True)
    st.session_state.sort_data = current_sort
    
    # Konversi hasil sort menjadi dictionary list untuk mapping
    mapping_lists = {g['header']: g['items'] for g in st.session_state.sort_data}
    
    st.divider()

    # --- BAGIAN SELEKSI JENIS PEKERJAAN ---
    st.subheader("2. Seleksi Jenis Pekerjaan")
    all_jenis = [str(j) for j in df_processed['jenispekerjaan'].unique() if j is not None]
    
    pilihan_aktif = st.multiselect(
        "Daftar Jenis Pekerjaan (Hapus nama yang TIDAK SESUAI):",
        options=all_jenis,
        default=all_jenis
    )

    list_jenis_pekerjaan_dihapus = [j for j in all_jenis if j not in pilihan_aktif]

    if st.button("Proses dan Export ke Excel"):
        # Jalankan Logika
        df_step_1 = mapping_unor(df_processed, mapping_lists)
        df_step_2 = df_step_1[~df_step_1['jenispekerjaan'].isin(list_jenis_pekerjaan_dihapus)].reset_index(drop=True)
        df_step_2['No'] = range(1, len(df_step_2) + 1)
        
        # Finalisasi Kolom
        try:
            df_final = df_step_2[['No','satker_paket_uraian','unor','Tahun','target_vol','target_satuan','jenispekerjaan','satker']].rename(columns={
                'satker_paket_uraian': 'Uraian Pekerjaan','target_vol': 'Volume','target_satuan': 'Satuan'
            })
            
            st.success("Proses selesai!")
            st.dataframe(df_final, use_container_width=True)
            
            # Excel Export
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False, sheet_name='Data_Proses')
            
            st.download_button(
                label="📥 Download Hasil Proses (.xlsx)",
                data=output.getvalue(),
                file_name='data_hasil_final.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
        except KeyError as e:
            st.error(f"Gagal memproses kolom. Pastikan file Excel memiliki kolom yang sesuai. Error: {e}")

else:
    st.info("Menunggu upload file Excel untuk memulai pemrosesan.")