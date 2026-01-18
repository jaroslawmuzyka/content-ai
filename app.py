import streamlit as st
import pandas as pd
import requests
import re
import time
import io
from supabase import create_client

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="SEO 3.0 Content Factory", page_icon="🏭", layout="wide")

# --- STYLE CSS ---
st.markdown("""
<style>
    .block-container {padding-top: 1rem;}
    /* Próba wymuszenia wyśrodkowania dla specyficznych kolumn w tabelach (nie zawsze działa w st.data_editor, ale pomaga w st.dataframe) */
    [data-testid="stDataFrame"] th[aria-label="ID"], [data-testid="stDataFrame"] td[aria-label="ID"] { text-align: center !important; }
    [data-testid="stDataFrame"] th[aria-label="Język"], [data-testid="stDataFrame"] td[aria-label="Język"] { text-align: center !important; }
</style>
""", unsafe_allow_html=True)

# --- MAPOWANIE KOLUMN (BAZA -> UI) ---
COLUMN_MAP = {
    'id': 'ID',
    'keyword': 'Słowo kluczowe',
    'language': 'Język',
    'aio_prompt': 'AIO',
    'status_research': 'Status Research',
    'serp_phrases': 'Frazy z wyników',
    'senuto_phrases': 'Frazy Senuto',
    'info_graph': 'Graf informacji',
    'competitors_headers': 'Nagłówki konkurencji',
    'knowledge_graph': 'Knowledge graph',
    'status_headers': 'Status Nagłówki',
    'headers_expanded': 'Nagłówki rozbudowane',
    'headers_h2': 'Nagłówki H2',
    'headers_questions': 'Nagłówki pytania',
    'headers_final': 'Nagłówki (Finalne)',
    'status_rag': 'Status RAG',
    'rag_content': 'RAG',
    'rag_general': 'RAG General',
    'status_brief': 'Status Brief',
    'brief_json': 'Brief',
    'brief_html': 'Brief plik',
    'instructions': 'Dodatkowe instrukcje',
    'status_writing': 'Status Generacja',
    'final_article': 'Generowanie contentu'
}

REVERSE_COLUMN_MAP = {v: k for k, v in COLUMN_MAP.items()}

# --- SUPABASE INIT ---
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE"]["URL"]
    key = st.secrets["SUPABASE"]["KEY"]
    return create_client(url, key)

supabase = init_supabase()

# --- FUNKCJE POMOCNICZE EXCEL ---

def to_excel(df):
    """Konwertuje DataFrame do pliku Excel w pamięci (buffer)."""
    output = io.BytesIO()
    # Używamy xlsxwriter lub openpyxl
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='SEO Content')
    return output.getvalue()

def generate_template_excel():
    """Generuje pusty szablon do importu."""
    # Tworzymy pusty DF z sugerowanymi kolumnami
    df_template = pd.DataFrame(columns=["Słowo kluczowe", "Język", "AIO"])
    # Dodajemy przykładowy wiersz
    df_template.loc[0] = ["Przykład: Jaki rower kupić", "pl", "Tutaj wpisz opcjonalne instrukcje AIO"]
    return to_excel(df_template)

# --- FUNKCJE DIFY ---
def run_dify_workflow(api_key, inputs, user_id="streamlit_user"):
    url = f"{st.secrets['dify']['BASE_URL']}/workflows/run"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": inputs,
        "response_mode": "blocking",
        "user": user_id
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=450)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# --- OBSŁUGA DANYCH ---

def fetch_data():
    """Pobiera dane i dodaje kolumnę 'Select' do zaznaczania."""
    response = supabase.table("seo_content_tasks").select("*").order("id", desc=True).execute()
    data = response.data
    if not data:
        return pd.DataFrame(columns=['Select'] + list(COLUMN_MAP.values()))
    
    df = pd.DataFrame(data)
    df = df.rename(columns=COLUMN_MAP)
    df.insert(0, 'Select', False)
    return df

def update_db_record(row_id, updates):
    supabase.table("seo_content_tasks").update(updates).eq("id", row_id).execute()

def delete_records(ids_list):
    """Usuwa rekordy z bazy na podstawie listy ID."""
    if not ids_list:
        return
    supabase.table("seo_content_tasks").delete().in_("id", ids_list).execute()

def save_manual_changes(edited_df):
    df_to_save = edited_df.drop(columns=['Select'], errors='ignore')
    df_to_save = df_to_save.rename(columns=REVERSE_COLUMN_MAP)
    records = df_to_save.to_dict('records')
    
    progress_text = "Zapisywanie zmian..."
    my_bar = st.progress(0, text=progress_text)
    total = len(records)
    for i, record in enumerate(records):
        if record.get('id'):
            supabase.table("seo_content_tasks").upsert(record).execute()
        my_bar.progress((i + 1) / total, text=f"Zapisano wiersz {i+1}/{total}")
    my_bar.empty()
    st.success("Zmiany zapisane w bazie!")

def extract_headers_from_text(text):
    if not isinstance(text, str): return []
    html_headers = re.findall(r'<h2.*?>(.*?)</h2>', text, re.IGNORECASE)
    if html_headers:
        return [re.sub(r'<.*?>', '', h).strip() for h in html_headers]
    return [line.strip() for line in text.split('\n') if line.strip()]

# --- LOGIKA BIZNESOWA (ETAPY) ---
# (Funkcje stage_research, stage_headers, stage_rag, stage_brief, stage_writing
# pozostają bez zmian w logice, więc dla czytelności kodu wklejam je skrótowo,
# ale w pełnym pliku muszą tam być)

def stage_research(row):
    inputs = {"keyword": row['Słowo kluczowe'], "language": row['Język'], "aio": row['AIO'] if row['AIO'] else ""}
    resp = run_dify_workflow(st.secrets['dify']['API_KEY_RESEARCH'], inputs)
    if "data" in resp and "outputs" in resp["data"]:
        out = resp["data"]["outputs"]
        return {
            "status_research": "✅ Gotowe",
            "serp_phrases": out.get("frazy z serp", ""),
            "senuto_phrases": out.get("frazy_senuto", ""),
            "info_graph": out.get("grafinformacji", ""),
            "competitors_headers": out.get("naglowki", ""),
            "knowledge_graph": out.get("knowledge_graph", "")
        }
    else:
        raise Exception(f"Dify Error: {resp.get('error', 'Unknown error')}")

def stage_headers(row):
    frazy_full = f"{row['Frazy z wyników']}\n{row['Frazy Senuto']}"
    inputs = {"keyword": row['Słowo kluczowe'], "language": row['Język'], "frazy": frazy_full, "graf": row['Graf informacji'], "headings": row['Nagłówki konkurencji']}
    resp = run_dify_workflow(st.secrets['dify']['API_KEY_HEADERS'], inputs)
    if "data" in resp and "outputs" in resp["data"]:
        out = resp["data"]["outputs"]
        h2 = out.get("naglowki_h2", "")
        questions = out.get("naglowki_pytania", "")
        final_headers = row['Nagłówki (Finalne)']
        if not final_headers: final_headers = questions if questions else h2
        return {
            "status_headers": "✅ Gotowe",
            "headers_expanded": out.get("naglowki_rozbudowane", ""),
            "headers_h2": h2,
            "headers_questions": questions,
            "headers_final": final_headers
        }
    else:
        raise Exception(f"Dify Error: {resp.get('error', 'Unknown error')}")

def stage_rag(row):
    inputs = {"keyword": row['Słowo kluczowe'], "language": row['Język'], "headings": row['Nagłówki konkurencji']}
    resp = run_dify_workflow(st.secrets['dify']['API_KEY_RAG'], inputs)
    if "data" in resp and "outputs" in resp["data"]:
        out = resp["data"]["outputs"]
        return {"status_rag": "✅ Gotowe", "rag_content": out.get("dokladne", ""), "rag_general": out.get("ogolne", "")}
    else:
        raise Exception(f"Dify Error: {resp.get('error', 'Unknown error')}")

def stage_brief(row):
    h2_source = row['Nagłówki H2'] if row['Nagłówki H2'] else row['Nagłówki (Finalne)']
    if not h2_source: raise Exception("Brak nagłówków H2 do stworzenia briefu.")
    frazy_full = f"{row['Frazy z wyników']}\n{row['Frazy Senuto']}"
    inputs = {"keyword": row['Słowo kluczowe'], "keywords": frazy_full, "headings": h2_source, "knowledge_graph": row['Knowledge graph'], "information_graph": row['Graf informacji']}
    resp = run_dify_workflow(st.secrets['dify']['API_KEY_BRIEF'], inputs)
    if "data" in resp and "outputs" in resp["data"]:
        out = resp["data"]["outputs"]
        return {"status_brief": "✅ Gotowe", "brief_json": out.get("brief", ""), "brief_html": out.get("html", "")}
    else:
        raise Exception(f"Dify Error: {resp.get('error', 'Unknown error')}")

def stage_writing(row):
    headers_text = row['Nagłówki (Finalne)']
    headers_list = extract_headers_from_text(headers_text)
    if not headers_list: raise Exception("Pusta kolumna 'Nagłówki (Finalne)'.")
    full_knowledge = f"{row['RAG']}\n{row['RAG General']}"
    full_keywords = f"{row['Frazy z wyników']}, {row['Frazy Senuto']}"
    article_content = ""
    for h2 in headers_list:
        inputs = {
            "naglowek": h2, "language": row['Język'], "knowledge": full_knowledge, "keywords": full_keywords,
            "headings": row['Nagłówki rozbudowane'], "done": article_content, "keyword": row['Słowo kluczowe'], "instruction": row['Dodatkowe instrukcje']
        }
        resp = run_dify_workflow(st.secrets['dify']['API_KEY_WRITE'], inputs)
        if "data" in resp and "outputs" in resp["data"]:
            section = resp["data"]["outputs"].get("result", "")
            article_content += f"<h2>{h2}</h2>\n{section}\n\n"
        else:
            article_content += f"<h2>{h2}</h2>\n[BŁĄD GENEROWANIA: {resp.get('error')}]\n\n"
    return {"status_writing": "✅ Gotowe", "final_article": article_content}

# --- UNIWERSALNY PROCESOR BATCHOWY ---
def run_batch_process(selected_rows, process_func, status_col_db, success_msg):
    progress_container = st.empty()
    status_log = st.empty()
    stop_button_placeholder = st.empty()
    
    stop_process = False
    if stop_button_placeholder.button("⛔ ZATRZYMAJ PO OBECNYM REKORDZIE"):
        stop_process = True
    
    total = len(selected_rows)
    success_count = 0
    error_count = 0
    my_bar = progress_container.progress(0)
    
    for i, row in enumerate(selected_rows):
        row_id = row['ID']
        keyword = row['Słowo kluczowe']
        status_log.info(f"⏳ [{i+1}/{total}] Przetwarzanie: **{keyword}**...")
        update_db_record(row_id, {status_col_db: "🔄 W trakcie..."})
        
        try:
            updates = process_func(row)
            update_db_record(row_id, updates)
            success_count += 1
        except Exception as e:
            error_count += 1
            error_msg = str(e)[:100]
            update_db_record(row_id, {status_col_db: f"❌ Błąd: {error_msg}"})
            st.toast(f"Błąd przy '{keyword}': {error_msg}", icon="⚠️")
        
        my_bar.progress((i + 1) / total)
    
    my_bar.empty()
    stop_button_placeholder.empty()
    status_log.success(f"Zakończono! Sukces: {success_count}, Błędy: {error_count}")
    time.sleep(2)
    st.rerun()

# --- AUTORYZACJA ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        pwd = st.text_input("Hasło dostępu", type="password")
        if pwd == st.secrets["general"]["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            st.rerun()
        elif pwd:
            st.error("Złe hasło")
        return False
    return True

# --- MAIN APP ---
if check_password():
    
    # SIDEBAR - IMPORT / EXPORT / ADD
    with st.sidebar:
        st.title("🏭 Content Factory")
        
        # 1. IMPORT
        st.header("1. Import z Excela")
        
        # Link do szablonu
        template_bytes = generate_template_excel()
        st.download_button(
            label="📥 Pobierz szablon importu (XLSX)",
            data=template_bytes,
            file_name="example-import.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Pobierz pusty plik Excel z odpowiednimi kolumnami"
        )
        
        uploaded_file = st.file_uploader("Wgraj plik (XLSX/CSV)", type=['xlsx', 'csv'])
        
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    import_df = pd.read_csv(uploaded_file)
                else:
                    import_df = pd.read_excel(uploaded_file)
                
                st.write("Podgląd pliku:", import_df.head(2))
                
                # Mapowanie
                cols = import_df.columns.tolist()
                c_kw = st.selectbox("Kolumna: Słowo kluczowe", cols, index=0)
                c_lang = st.selectbox("Kolumna: Język", [None] + cols, index=None)
                c_aio = st.selectbox("Kolumna: AIO (opcjonalnie)", [None] + cols, index=None)
                
                if st.button("📥 Importuj do Bazy"):
                    count = 0
                    progress_text = "Importowanie..."
                    my_bar = st.progress(0, text=progress_text)
                    
                    for i, row in import_df.iterrows():
                        kw = row[c_kw]
                        lang = row[c_lang] if c_lang else "pl"
                        aio = row[c_aio] if c_aio and not pd.isna(row[c_aio]) else ""
                        
                        supabase.table("seo_content_tasks").insert({
                            "keyword": str(kw),
                            "language": str(lang),
                            "aio_prompt": str(aio),
                            "headers_final": ""
                        }).execute()
                        count += 1
                        my_bar.progress((i + 1) / len(import_df))
                    
                    my_bar.empty()
                    st.success(f"Zaimportowano {count} wierszy!")
                    time.sleep(1)
                    st.rerun()
            except Exception as e:
                st.error(f"Błąd pliku: {e}")
        
        st.divider()
        
        # 2. DODAJ RĘCZNIE
        st.header("2. Dodaj Ręcznie")
        with st.form("add_manual"):
            m_kw = st.text_input("Słowo kluczowe")
            m_lang = st.text_input("Język", value="pl")
            m_aio = st.text_area("AIO (opcjonalnie)")
            m_sub = st.form_submit_button("Dodaj")
            if m_sub and m_kw:
                supabase.table("seo_content_tasks").insert({
                    "keyword": m_kw, "language": m_lang, "aio_prompt": m_aio, "headers_final": ""
                }).execute()
                st.success("Dodano!")
                st.rerun()

        st.divider()

        # 3. EXPORT
        st.header("3. Eksport Danych")
        if st.button("Przygotuj plik Excel"):
            # Pobieramy wszystko
            full_df = fetch_data()
            if not full_df.empty:
                # Usuwamy kolumnę select jeśli jest
                export_df = full_df.drop(columns=['Select'], errors='ignore')
                excel_data = to_excel(export_df)
                st.download_button(
                    label="💾 Pobierz wszystko (XLSX)",
                    data=excel_data,
                    file_name="seo_export_full.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("Brak danych do pobrania")

    # --- GŁÓWNY OBSZAR ---
    
    df = fetch_data()
    
    st.header("📋 Lista Zadań")
    
    # Filtrowanie
    col_f1, col_f2 = st.columns([2, 2])
    with col_f1:
        status_filter = st.selectbox("Filtruj wg statusu Research", ["Wszystkie", "Oczekuje", "✅ Gotowe", "❌ Błąd"])
    
    if status_filter != "Wszystkie":
        df = df[df['Status Research'].str.contains(status_filter, na=False)]

    # KONFIGURACJA KOLUMN DLA ST.DATA_EDITOR
    # Ustawiamy szerokość na ~200px (approx 3-4cm) dla kolumn tekstowych
    # ID i Język - małe i wyśrodkowane (via CSS hack na górze + mała szerokość)
    column_cfg = {
        "Select": st.column_config.CheckboxColumn("Zaznacz", default=False, width="small"),
        "ID": st.column_config.NumberColumn(width="small", disabled=True, format="%d"),
        "Słowo kluczowe": st.column_config.TextColumn(width=200),
        "Język": st.column_config.TextColumn(width="small"),
        "AIO": st.column_config.TextColumn(width=200),
        
        # Statusy
        "Status Research": st.column_config.TextColumn(width="small"),
        "Status Nagłówki": st.column_config.TextColumn(width="small"),
        "Status RAG": st.column_config.TextColumn(width="small"),
        "Status Brief": st.column_config.TextColumn(width="small"),
        "Status Generacja": st.column_config.TextColumn(width="small"),

        # Dane merytoryczne - szerokość ok. 3-4cm (medium/200px)
        "Frazy z wyników": st.column_config.TextColumn(width=200),
        "Frazy Senuto": st.column_config.TextColumn(width=200),
        "Graf informacji": st.column_config.TextColumn(width=200),
        "Nagłówki konkurencji": st.column_config.TextColumn(width=200),
        "Knowledge graph": st.column_config.TextColumn(width=200),
        "Nagłówki rozbudowane": st.column_config.TextColumn(width=200),
        "Nagłówki H2": st.column_config.TextColumn(width=200),
        "Nagłówki pytania": st.column_config.TextColumn(width=200),
        "Nagłówki (Finalne)": st.column_config.TextColumn(width=300, help="Główne źródło do generowania"), # Trochę szersze dla wygody
        "RAG": st.column_config.TextColumn(width=200),
        "RAG General": st.column_config.TextColumn(width=200),
        "Brief": st.column_config.TextColumn(width=200),
        "Brief plik": st.column_config.TextColumn(width=200),
        "Dodatkowe instrukcje": st.column_config.TextColumn(width=200),
        "Generowanie contentu": st.column_config.TextColumn(width=200, disabled=True),
    }

    edited_df = st.data_editor(
        df,
        key="data_editor",
        height=500,
        use_container_width=False, # Ważne: False pozwala respektować szerokości kolumn w pixelach
        hide_index=True,
        column_config=column_cfg
    )

    # AKCJE POD TABELĄ (Zapisz / Usuń / Info)
    col_save, col_del, col_info = st.columns([1, 1, 4])
    
    selected_rows = edited_df[edited_df['Select'] == True]
    count_selected = len(selected_rows)

    with col_save:
        if st.button("💾 Zapisz Zmiany"):
            save_manual_changes(edited_df)
            time.sleep(1)
            st.rerun()
            
    with col_del:
        if st.button("🗑️ Usuń zaznaczone", type="primary"):
            if count_selected > 0:
                ids_to_del = selected_rows['ID'].tolist()
                delete_records(ids_to_del)
                st.success(f"Usunięto {count_selected} wierszy.")
                time.sleep(1)
                st.rerun()
            else:
                st.warning("Najpierw zaznacz wiersze.")

    with col_info:
        st.info(f"Zaznaczono wierszy: **{count_selected}**")

    st.divider()
    
    # --- PANEL STEROWANIA (AKCJE MASOWE) ---
    st.subheader("⚙️ Uruchom Procesy (Dla zaznaczonych)")
    
    if count_selected == 0:
        st.caption("Zaznacz wiersze w kolumnie 'Select' powyżej, aby uruchomić procesy.")
    else:
        c1, c2, c3, c4, c5 = st.columns(5)
        rows_to_process = selected_rows.to_dict('records')

        with c1:
            if st.button(f"1. RESEARCH ({count_selected})"):
                run_batch_process(rows_to_process, stage_research, "status_research", "Research zakończony")

        with c2:
            if st.button(f"2. NAGŁÓWKI ({count_selected})"):
                run_batch_process(rows_to_process, stage_headers, "status_headers", "Nagłówki wygenerowane")

        with c3:
            if st.button(f"3. RAG ({count_selected})"):
                run_batch_process(rows_to_process, stage_rag, "status_rag", "Baza RAG zbudowana")

        with c4:
            if st.button(f"4. BRIEF ({count_selected})"):
                run_batch_process(rows_to_process, stage_brief, "status_brief", "Briefy gotowe")
        
        with c5:
            if st.button(f"5. GENERUJ CONTENT ({count_selected})"):
                st.warning("Generowanie na podstawie kolumny 'Nagłówki (Finalne)'")
                run_batch_process(rows_to_process, stage_writing, "status_writing", "Treści wygenerowane")

    # --- PODGLĄD SZCZEGÓŁÓW ---
    st.divider()
    
    if not df.empty:
        all_ids = df['ID'].tolist()
        keywords = df['Słowo kluczowe'].tolist()
        # Tworzymy listę wyboru
        options = {f"#{ids} - {kw}": ids for ids, kw in zip(all_ids, keywords)}
        
        selected_option = st.selectbox("Wybierz artykuł do podglądu:", options.keys())
        selected_id_view = options[selected_option]
        
        # Pobieramy wiersz z edited_df
        try:
            view_row = edited_df[edited_df['ID'] == selected_id_view].iloc[0]
            
            with st.expander("🔍 Pokaż szczegóły artykułu", expanded=False):
                t1, t2, t3, t4, t5 = st.tabs(["Research", "Nagłówki", "RAG", "Brief", "Wynik"])
                
                with t1:
                    col_a, col_b = st.columns(2)
                    col_a.text_area("SERP", view_row['Frazy z wyników'], height=200)
                    col_a.text_area("Graf", view_row['Graf informacji'], height=200)
                    col_b.text_area("Senuto", view_row['Frazy Senuto'], height=200)
                    col_b.text_area("Knowledge Graph", view_row['Knowledge graph'], height=200)
                
                with t2:
                    st.markdown("### Struktura")
                    c_h1, c_h2 = st.columns(2)
                    c_h1.text_area("H2 (Robocze)", view_row['Nagłówki H2'], height=250)
                    c_h1.text_area("Pytania (Robocze)", view_row['Nagłówki pytania'], height=250)
                    
                    c_h2.success("👇 Źródło do generowania")
                    c_h2.text_area("⭐ NAGŁÓWKI (FINALNE)", view_row['Nagłówki (Finalne)'], height=530)
                
                with t3:
                    st.text_area("Wiedza Dokładna", view_row['RAG'], height=300)
                    st.text_area("Wiedza Ogólna", view_row['RAG General'], height=300)
                    
                with t4:
                    if view_row['Brief plik']:
                        st.components.v1.html(view_row['Brief plik'], height=600, scrolling=True)
                    else:
                        st.info("Brak briefu HTML")
                
                with t5:
                    if view_row['Generowanie contentu']:
                        st.markdown(view_row['Generowanie contentu'], unsafe_allow_html=True)
                        st.divider()
                        st.code(view_row['Generowanie contentu'], language='html')
                    else:
                        st.warning("Brak treści.")
        except IndexError:
            st.warning("Wybierz poprawny wiersz.")