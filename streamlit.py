import streamlit as st
import pandas as pd
import numpy as np
from streamlit_sortables import sort_items

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Data Processor Satker", layout="wide")

# CSS Tambahan agar pilihan multiselect tidak terpotong (wrap text)
st.markdown("""
    <style>
    .stMultiSelect span {
        white-space: normal !important;
        height: auto !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 1. FUNGSI PROCESSING AWAL (DARI NOTEBOOK) ---
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

# --- 2. FUNGSI MAPPING UNOR & BACKFILL (DARI NOTEBOOK + LOGIKA PEMDA) ---
def mapping_unor(df, lists):
    df = df.copy()
    def check_unor(val):
        if val in lists['Pemda']: return 'Pemda'
        if val in lists['BM']:    return 'BM'
        if val in lists['CK']:    return 'CK'
        if val in lists['SDA']:   return 'SDA'
        if val in lists['PR']:    return 'PR'
        if val in lists['PS']:    return 'PS'
        return 'Lainnya'

    if 'satker' in df.columns:
        df['unor'] = df['satker'].apply(check_unor)
        
        # Logika khusus Pemda: Ganti dengan Unor pertama di bawahnya
        mask_pemda = df['unor'] == 'Pemda'
        valid_unors = df['unor'].mask(df['unor'].isin(['Pemda', 'Lainnya']))
        df.loc[mask_pemda, 'unor'] = valid_unors.bfill()
        df['unor'] = df['unor'].fillna('Pemda')
    return df

# --- 3. FUNGSI PENGHAPUSAN JENIS PEKERJAAN ---
def penghapusan_jenispekerjaan_tidaksesuai(df, kriteria_tidak_sesuai):
    """
    Menghapus baris-baris di DataFrame dimana kolom 'jenispekerjaan' 
    ada di dalam list kriteria_tidak_sesuai.
    """
    df = df.copy()
    df_filtered = df[~df['jenispekerjaan'].isin(kriteria_tidak_sesuai)].reset_index(drop=True)
    return df_filtered

# --- 4. FUNGSI URUT NOMOR ---
def urut_nomor(df):
    df = df.copy()
    df['No'] = range(1, len(df) + 1)
    return df

# --- INTERFACE STREAMLIT ---
st.title("📊 Data Processor Satker & Unor")

uploaded_file = st.file_uploader("Upload file Excel (data.xlsx)", type=["xlsx"])

if uploaded_file:
    # Membaca data awal
    df_raw = pd.read_excel(uploaded_file)
    
    # Jalankan proses awal pemisahan satker & jenis pekerjaan
    df_processed = process_dataframe(df_raw, col_kode='Kode', col_uraian='satker_paket_uraian')
    
    st.divider()
    
    # --- BAGIAN DRAG & DROP UNOR ---
    st.subheader("1. Pemetaan Kategori Unor")
    st.write("Geser Satker ke kategori yang sesuai untuk menentukan 'Unor'.")
    
    unique_satkers = list(df_processed['satker'].unique())
    
    # Komponen Sortable (Drag & Drop)
    sort_data = sort_items([
        {'header': 'Daftar Satker', 'items': unique_satkers},
        {'header': 'Pemda', 'items': []},
        {'header': 'BM', 'items': []},
        {'header': 'CK', 'items': []},
        {'header': 'SDA', 'items': []},
        {'header': 'PR', 'items': []},
        {'header': 'PS', 'items': []}
    ], multi_containers=True)
    
    # Konversi hasil sort menjadi dictionary list
    mapping_lists = {g['header']: g['items'] for g in sort_data}
    
    st.divider()

    # --- BAGIAN SELEKSI JENIS PEKERJAAN ---
    st.subheader("2. Seleksi Jenis Pekerjaan")
    all_jenis = [str(j) for j in df_processed['jenispekerjaan'].unique() if j is not None]
    
    # Mengatur 'default' agar menampilkan seluruh jenis pekerjaan di awal
    # User nantinya tinggal menghapus item yang tidak diinginkan (dianggap tidak sesuai)
    pilihan_aktif = st.multiselect(
        "Daftar Jenis Pekerjaan (Hapus nama yang TIDAK SESUAI):",
        options=all_jenis,
        default=all_jenis,
        help="Nama yang panjang akan otomatis ditampilkan utuh ke bawah. Item yang Anda hapus dari daftar ini akan dibuang dari hasil akhir."
    )

    # Menentukan kriteria yang tidak sesuai (yang dihapus oleh user dari pilihan_aktif)
    list_jenis_pekerjaan_dihapus = [j for j in all_jenis if j not in pilihan_aktif]

    if st.button("Proses dan Export ke Excel"):
        # Langkah A: Mapping Unor
        df_step_1 = mapping_unor(df_processed, mapping_lists)
        
        # Langkah B: Penghapusan berdasarkan list yang dihapus oleh user
        df_step_2 = penghapusan_jenispekerjaan_tidaksesuai(df_step_1, list_jenis_pekerjaan_dihapus)
        
        # Langkah C: Urut Nomor
        df_step_3 = urut_nomor(df_step_2)
        
        # Langkah D: Finalisasi Kolom
        df_final = df_step_3[['No','satker_paket_uraian','unor','Tahun','target_vol','target_satuan','jenispekerjaan','satker']].rename(columns={
        'satker_paket_uraian': 'Uraian Pekerjaan','target_vol': 'Volume','target_satuan': 'Satuan'})
        
        st.success("Proses selesai!")
        st.write("### Preview Hasil Akhir")
        # Update parameter use_container_width=True menjadi width='stretch'
        st.dataframe(df_final, width='stretch')
        
        # Ekspor ke Excel (.xlsx) 
        # Menggunakan to_excel tanpa memerlukan import io eksplisit di header
        # Streamlit download_button mendukung penulisan file langsung via buffer internal Pandas
        import io
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_final.to_excel(writer, index=False, sheet_name='Data_Proses')
        excel_data = output.getvalue()
        
        st.download_button(
            label="📥 Download Hasil Proses (.xlsx)",
            data=excel_data,
            file_name='data_hasil_final.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

else:
    st.info("Menunggu upload file Excel untuk memulai pemrosesan.")