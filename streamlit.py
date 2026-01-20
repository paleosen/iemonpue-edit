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
    # Membaca data awal
    df_raw = pd.read_excel(uploaded_file)
    df_processed = process_dataframe(df_raw, col_kode='Kode', col_uraian='satker_paket_uraian')
    
    unique_satkers = list(df_processed['satker'].unique())

    # --- INISIALISASI STATE (Hanya Sekali per File) ---
    if 'sort_data_state' not in st.session_state or st.session_state.get('last_file_processed') != uploaded_file.name:
        st.session_state.sort_data_state = [
            {'header': 'Daftar Satker', 'items': unique_satkers},
            {'header': 'Pemda', 'items': []},
            {'header': 'BM', 'items': []},
            {'header': 'CK', 'items': []},
            {'header': 'SDA', 'items': []},
            {'header': 'PR', 'items': []},
            {'header': 'PS', 'items': []}
        ]
        st.session_state.last_file_processed = uploaded_file.name

    # --- BAGIAN INPUT ---
    # Catatan: sort_items memiliki bug infinite loop jika dimasukkan ke dalam st.form pada beberapa versi.
    # Kita menggunakannya di luar form tetapi hasilnya disimpan ke variabel temporary untuk diproses saat submit.
    
    st.subheader("1. Pemetaan Kategori Unor")
    st.info("Susun daftar Satker ke kategori Unor di bawah ini (Drag & Drop).")
    
    # Gunakan variabel penampung sementara agar tidak langsung merusak state utama jika terjadi trigger otomatis
    temp_sort_result = sort_items(st.session_state.sort_data_state, multi_containers=True)
    
    st.divider()
    
    # Gunakan form untuk tombol proses dan filter lainnya
    with st.form("processing_form"):
        st.subheader("2. Seleksi Jenis Pekerjaan")
        all_jenis = [str(j) for j in df_processed['jenispekerjaan'].unique() if j is not None]
        pilihan_aktif = st.multiselect(
            "Filter Jenis Pekerjaan (Hapus yang tidak sesuai):",
            options=all_jenis,
            default=all_jenis
        )
        
        st.write("---")
        submit_button = st.form_submit_button("🚀 Jalankan Proses dan Generate Excel")

    # --- LOGIKA EKSEKUSI ---
    if submit_button:
        # Sinkronisasi hasil sort ke state utama hanya saat tombol ditekan
        st.session_state.sort_data_state = temp_sort_result
        
        mapping_lists = {g['header']: g['items'] for g in temp_sort_result}
        list_jenis_pekerjaan_dihapus = [j for j in all_jenis if j not in pilihan_aktif]

        with st.spinner("Sedang memproses data..."):
            # Langkah 1: Mapping Unor
            df_step_1 = mapping_unor(df_processed, mapping_lists)
            
            # Langkah 2: Filter Jenis Pekerjaan
            df_step_2 = df_step_1[~df_step_1['jenispekerjaan'].isin(list_jenis_pekerjaan_dihapus)].reset_index(drop=True)
            
            # Langkah 3: Finalisasi
            df_step_2['No'] = range(1, len(df_step_2) + 1)
            
            try:
                # Pastikan kolom-kolom ini ada di dataframe Anda
                available_cols = df_step_2.columns.tolist()
                target_cols = ['No','satker_paket_uraian','unor','Tahun','target_vol','target_satuan','jenispekerjaan','satker','lokasi','jenis_pengadaan','metode_pemilihan','pagu_efektif','realisasi','progress_keu','progress_fisik']
                
                # Filter hanya kolom yang benar-benar ada untuk menghindari error
                cols_to_use = [c for c in target_cols if c in available_cols]
                
                df_final = df_step_2[cols_to_use].rename(columns={
                    'satker_paket_uraian': 'Uraian Pekerjaan',
                    'target_vol': 'Volume',
                    'target_satuan': 'Satuan'
                })
                
                st.success("Pemrosesan Berhasil!")
                st.dataframe(df_final, use_container_width=True)
                
                # Ekspor ke Excel
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Data_Proses')
                
                st.download_button(
                    label="📥 Download Hasil (.xlsx)",
                    data=output.getvalue(),
                    file_name=f'hasil_proses_{uploaded_file.name}',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                )
            except Exception as e:
                st.error(f"Terjadi kesalahan saat menyusun data: {e}")

else:
    st.info("Silakan unggah file Excel untuk memulai.")

# --- SUMBER REFERENSI ---
# Facebook. (n.d.). React Error #185: Maximum update depth exceeded. React Documentation. https://reactjs.org/docs/error-decoder.html?invariant=185
# Streamlit Inc. (2024). Batch input widgets with st.form. Streamlit Documentation. https://docs.streamlit.io/develop/api-reference/execution-flow/st.form
# Ghaisani, A. (2023). Handling Infinite Loops in Streamlit Components. Streamlit Community. https://discuss.streamlit.io/