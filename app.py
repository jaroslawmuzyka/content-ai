import streamlit as st
import pandas as pd
import requests
import json
import time
import re

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="SEO 3.0 Content Machine", page_icon="🤖", layout="wide")

# --- STYLE CSS (opcjonalnie dla lepszego wyglądu tabeli) ---
st.markdown("""
<style>
    .block-container {padding-top: 1rem;}
    div[data-testid="stExpander"] div[role="button"] p {font-size: 1.1rem; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# --- ZMIENNE GLOBALNE I KOLUMNY ---
COLUMNS = [
    'Słowo kluczowe', 'Język', 'AIO', 
    'Status_Research', 'Frazy_SERP', 'Frazy_Senuto', 'Graf_Informacji', 'Nagłówki_Konkurencji', 'Knowledge_Graph',
    'Status_Headers', 'Nagłówki_Rozbudowane', 'Nagłówki_H2', 'Nagłówki_Pytania',
    'Status_RAG', 'RAG_Content', 'RAG_General',
    'Status_Brief', 'Brief_JSON', 'Brief_HTML',
    'Dodatkowe_instrukcje', 
    'Status_Writing', 'Artykuł'
]

# --- FUNKCJE POMOCNICZE: AUTORYZACJA ---
def check_password():
    """Zwraca True jeśli hasło jest poprawne."""
    def password_entered():
        if st.session_state["password"] == st.secrets["general"]["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Hasło dostępu", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Hasło dostępu", type="password", on_change=password_entered, key="password")
        st.error("😕 Nieprawidłowe hasło")
        return False
    else:
        return True

# --- FUNKCJE POMOCNICZE: DIFY API ---
def run_dify_workflow(api_key, inputs, user_id="streamlit_user"):
    """Wysyła zapytanie do API Dify w trybie blokującym."""
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
        response = requests.post(url, headers=headers, json=payload, timeout=300) # Timeout 5 min
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

# --- LOGIKA BIZNESOWA: PRZETWARZANIE WIERSZY ---

def process_research(row):
    """KROK 1: Research (SEO 3.0 8.2-8.3)"""
    inputs = {
        "keyword": row['Słowo kluczowe'],
        "language": row['Język'],
        "aio": row['AIO'] if row['AIO'] else ""
    }
    
    resp = run_dify_workflow(st.secrets['dify']['API_KEY_RESEARCH'], inputs)
    
    if "data" in resp and "outputs" in resp["data"]:
        out = resp["data"]["outputs"]
        return {
            "Status_Research": "✅ Gotowe",
            "Frazy_SERP": out.get("frazy z serp", ""),
            "Frazy_Senuto": out.get("frazy_senuto", ""),
            "Graf_Informacji": out.get("grafinformacji", ""),
            "Nagłówki_Konkurencji": out.get("naglowki", ""),
            "Knowledge_Graph": out.get("knowledge_graph", "")
        }
    else:
        return {"Status_Research": f"❌ Błąd: {resp.get('error', 'Unknown')}"}

def process_headers(row):
    """KROK 2: Budowa nagłówków (SEO 3.0 8.4)"""
    # Łączymy frazy z SERP i Senuto
    frazy_full = f"{row['Frazy_SERP']}\n{row['Frazy_Senuto']}"
    
    inputs = {
        "keyword": row['Słowo kluczowe'],
        "language": row['Język'],
        "frazy": frazy_full,
        "graf": row['Graf_Informacji'],
        "headings": row['Nagłówki_Konkurencji']
    }
    
    resp = run_dify_workflow(st.secrets['dify']['API_KEY_HEADERS'], inputs)
    
    if "data" in resp and "outputs" in resp["data"]:
        out = resp["data"]["outputs"]
        return {
            "Status_Headers": "✅ Gotowe",
            "Nagłówki_Rozbudowane": out.get("naglowki_rozbudowane", ""),
            "Nagłówki_H2": out.get("naglowki_h2", ""),
            "Nagłówki_Pytania": out.get("naglowki_pytania", "")
        }
    else:
        return {"Status_Headers": f"❌ Błąd: {resp.get('error', 'Unknown')}"}

def process_rag(row):
    """KROK 3: Budowa RAG (SEO 3.0 8.5)"""
    inputs = {
        "keyword": row['Słowo kluczowe'],
        "language": row['Język'],
        "headings": row['Nagłówki_Konkurencji'] # Wykorzystujemy nagłówki konkurencji do scrapowania kontekstu
    }
    
    resp = run_dify_workflow(st.secrets['dify']['API_KEY_RAG'], inputs)
    
    if "data" in resp and "outputs" in resp["data"]:
        out = resp["data"]["outputs"]
        return {
            "Status_RAG": "✅ Gotowe",
            "RAG_Content": out.get("dokladne", ""),
            "RAG_General": out.get("ogolne", "")
        }
    else:
        return {"Status_RAG": f"❌ Błąd: {resp.get('error', 'Unknown')}"}

def process_brief(row):
    """KROK 4: Content Brief"""
    # Łączymy frazy
    frazy_full = f"{row['Frazy_SERP']}\n{row['Frazy_Senuto']}"
    
    inputs = {
        "keyword": row['Słowo kluczowe'], # Opcjonalne w briefie, ale dobre dla kontekstu
        "keywords": frazy_full,
        "headings": row['Nagłówki_H2'], # Używamy wygenerowanych H2
        "knowledge_graph": row['Knowledge_Graph'],
        "information_graph": row['Graf_Informacji']
    }
    
    resp = run_dify_workflow(st.secrets['dify']['API_KEY_BRIEF'], inputs)
    
    if "data" in resp and "outputs" in resp["data"]:
        out = resp["data"]["outputs"]
        return {
            "Status_Brief": "✅ Gotowe",
            "Brief_JSON": out.get("brief", ""),
            "Brief_HTML": out.get("html", "")
        }
    else:
        return {"Status_Brief": f"❌ Błąd: {resp.get('error', 'Unknown')}"}

def extract_h2_headers(html_content):
    """Pomocnicza funkcja do wyciągnięcia czystego tekstu z tagów <h2>"""
    if not isinstance(html_content, str):
        return []
    # Szuka <h2>Tekst</h2> lub <H2>Tekst</H2>
    headers = re.findall(r'<h2.*?>(.*?)</h2>', html_content, re.IGNORECASE)
    # Czyścimy ewentualne tagi w środku
    clean_headers = [re.sub(r'<.*?>', '', h).strip() for h in headers]
    return clean_headers

def process_writing(row):
    """KROK 5: Generowanie Contentu (Pętla po nagłówkach)"""
    
    # 1. Pobieramy listę H2 z kolumny Nagłówki_H2
    headers_list = extract_h2_headers(row['Nagłówki_H2'])
    
    if not headers_list:
        return {"Status_Writing": "❌ Błąd: Brak nagłówków H2 do pisania"}
    
    # Przygotowanie kontekstu (RAG + Grafy)
    full_knowledge = f"{row.get('RAG_Content', '')}\n{row.get('RAG_General', '')}"
    full_keywords = f"{row['Frazy_SERP']}, {row['Frazy_Senuto']}"
    
    article_content = ""
    status_msg = "Przetwarzanie..."
    
    # Pętla generowania sekcja po sekcji
    total_headers = len(headers_list)
    
    # Placeholder dla paska postępu w UI (trudne do zrobienia wewnątrz funkcji bez przekazania obiektu,
    # więc zrobimy to "ślepo" lub zwrócimy wynik na końcu)
    
    for i, h2 in enumerate(headers_list):
        inputs = {
            "naglowek": h2,
            "language": row['Język'],
            "knowledge": full_knowledge,
            "keywords": full_keywords,
            "headings": row['Nagłówki_Rozbudowane'], # Pełna struktura dla kontekstu
            "done": article_content, # Co już napisano (dla spójności)
            "keyword": row['Słowo kluczowe'],
            "instruction": row.get('Dodatkowe_instrukcje', "")
        }
        
        # Wywołanie API Write
        resp = run_dify_workflow(st.secrets['dify']['API_KEY_WRITE'], inputs)
        
        if "data" in resp and "outputs" in resp["data"]:
            section_content = resp["data"]["outputs"].get("result", "")
            # Dodajemy nagłówek i treść do artykułu (formatowanie HTML)
            # Uwaga: Workflow zwraca samą treść bez nagłówka H2 (zgodnie z promptem "Don't add heading at the beginning"), 
            # więc dodajemy go ręcznie dla struktury, albo polegamy na tym co zwrócił.
            # Z promptu wynika, że zwraca sam content. Dodajmy H2 ręcznie dla czytelności finalnego HTML.
            article_content += f"<h2>{h2}</h2>\n{section_content}\n\n"
        else:
            article_content += f"<h2>{h2}</h2>\n[BŁĄD GENEROWANIA SEKCJI]\n\n"
            
    return {
        "Status_Writing": "✅ Gotowe",
        "Artykuł": article_content
    }

# --- GŁÓWNA APLIKACJA ---

if check_password():
    st.title("🤖 SEO 3.0 Content Machine - Panel Zarządzania")
    st.info("Zarządzaj procesem generowania treści z wykorzystaniem workflow DIFY.")

    # --- INICJALIZACJA STANU DANYCH ---
    if "df" not in st.session_state:
        # Pusty DataFrame z odpowiednimi kolumnami
        st.session_state.df = pd.DataFrame(columns=COLUMNS)

    # --- SIDEBAR: IMPORT/EXPORT ---
    with st.sidebar:
        st.header("📂 Pliki")
        
        # Upload CSV
        uploaded_file = st.file_uploader("Wgraj CSV/Excel", type=["csv", "xlsx"])
        if uploaded_file:
            if uploaded_file.name.endswith('.csv'):
                loaded_df = pd.read_csv(uploaded_file)
            else:
                loaded_df = pd.read_excel(uploaded_file)
            
            # Dopasowanie kolumn (dodanie brakujących)
            for col in COLUMNS:
                if col not in loaded_df.columns:
                    loaded_df[col] = ""
            
            # Filtrowanie tylko do naszych kolumn
            st.session_state.df = loaded_df[COLUMNS]
            st.success("Wczytano dane!")

        # Download CSV
        if not st.session_state.df.empty:
            csv = st.session_state.df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Pobierz CSV",
                csv,
                "seo_content_export.csv",
                "text/csv",
                key='download-csv'
            )
            
        st.divider()
        st.header("➕ Dodaj nowy wiersz")
        new_keyword = st.text_input("Słowo kluczowe")
        new_lang = st.text_input("Język", value="pl")
        new_aio = st.text_area("AIO (opcjonalnie)")
        
        if st.button("Dodaj do tabeli"):
            if new_keyword:
                new_row = {col: "" for col in COLUMNS}
                new_row['Słowo kluczowe'] = new_keyword
                new_row['Język'] = new_lang
                new_row['AIO'] = new_aio
                new_row['Status_Research'] = "Oczekuje"
                new_row['Status_Headers'] = "Oczekuje"
                new_row['Status_RAG'] = "Oczekuje"
                new_row['Status_Brief'] = "Oczekuje"
                new_row['Status_Writing'] = "Oczekuje"
                
                st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True)
                st.rerun()

    # --- GŁÓWNY WIDOK: EDYTOR DANYCH ---
    st.subheader("Arkusz Roboczy")
    
    # Data Editor pozwala na edycję "w miejscu"
    edited_df = st.data_editor(
        st.session_state.df,
        key="editor",
        num_rows="dynamic",
        height=400,
        use_container_width=True
    )
    
    # Aktualizacja stanu po edycji ręcznej
    if not edited_df.equals(st.session_state.df):
        st.session_state.df = edited_df

    # --- ACTIONS ---
    st.subheader("🚀 Akcje Masowe")
    col1, col2, col3, col4, col5 = st.columns(5)

    # 1. RESEARCH
    with col1:
        if st.button("1. Uruchom RESEARCH 🔍"):
            progress_bar = st.progress(0)
            rows_to_process = st.session_state.df.index.tolist()
            total = len(rows_to_process)
            
            for i, idx in enumerate(rows_to_process):
                row = st.session_state.df.iloc[idx]
                # Przetwarzaj tylko jeśli puste lub błąd, lub wymuszono (tutaj przetwarzamy wszystko)
                with st.spinner(f"Research dla: {row['Słowo kluczowe']}..."):
                    result = process_research(row)
                    # Aktualizacja DataFrame
                    for key, val in result.items():
                        st.session_state.df.at[idx, key] = val
                progress_bar.progress((i + 1) / total)
            st.success("Research zakończony!")
            st.rerun()

    # 2. HEADERS
    with col2:
        if st.button("2. Generuj NAGŁÓWKI 📑"):
            progress_bar = st.progress(0)
            rows_to_process = st.session_state.df.index.tolist()
            total = len(rows_to_process)
            
            for i, idx in enumerate(rows_to_process):
                row = st.session_state.df.iloc[idx]
                if row['Status_Research'] == "✅ Gotowe":
                    with st.spinner(f"Nagłówki dla: {row['Słowo kluczowe']}..."):
                        result = process_headers(row)
                        for key, val in result.items():
                            st.session_state.df.at[idx, key] = val
                else:
                    st.warning(f"Pominięto '{row['Słowo kluczowe']}' - brak Researchu.")
                progress_bar.progress((i + 1) / total)
            st.success("Nagłówki wygenerowane!")
            st.rerun()

    # 3. RAG
    with col3:
        if st.button("3. Buduj BAZĘ RAG 🧠"):
            progress_bar = st.progress(0)
            rows_to_process = st.session_state.df.index.tolist()
            total = len(rows_to_process)
            
            for i, idx in enumerate(rows_to_process):
                row = st.session_state.df.iloc[idx]
                if row['Nagłówki_Konkurencji']: # Wymagane do RAG
                    with st.spinner(f"RAG dla: {row['Słowo kluczowe']}..."):
                        result = process_rag(row)
                        for key, val in result.items():
                            st.session_state.df.at[idx, key] = val
                else:
                    st.warning(f"Pominięto '{row['Słowo kluczowe']}' - brak danych wejściowych.")
                progress_bar.progress((i + 1) / total)
            st.success("Baza RAG gotowa!")
            st.rerun()

    # 4. BRIEF
    with col4:
        if st.button("4. Generuj BRIEF 📝"):
            progress_bar = st.progress(0)
            rows_to_process = st.session_state.df.index.tolist()
            total = len(rows_to_process)
            
            for i, idx in enumerate(rows_to_process):
                row = st.session_state.df.iloc[idx]
                # Sprawdź czy mamy H2 i wiedzę
                if row['Nagłówki_H2'] and row['Graf_Informacji']:
                    with st.spinner(f"Brief dla: {row['Słowo kluczowe']}..."):
                        result = process_brief(row)
                        for key, val in result.items():
                            st.session_state.df.at[idx, key] = val
                else:
                    st.warning(f"Pominięto '{row['Słowo kluczowe']}' - brak nagłówków H2 lub grafu.")
                progress_bar.progress((i + 1) / total)
            st.success("Briefy wygenerowane!")
            st.rerun()

    # 5. WRITING
    with col5:
        if st.button("5. PISZ ARTYKUŁ ✍️"):
            st.warning("To może potrwać dłuższą chwilę, ponieważ generujemy treść sekcja po sekcji.")
            progress_bar = st.progress(0)
            rows_to_process = st.session_state.df.index.tolist()
            total = len(rows_to_process)
            
            for i, idx in enumerate(rows_to_process):
                row = st.session_state.df.iloc[idx]
                
                # Warunki startowe
                if row['Nagłówki_H2'] and row['Nagłówki_Rozbudowane']:
                    with st.spinner(f"Pisanie artykułu: {row['Słowo kluczowe']}... (Może to zająć kilka minut)"):
                        result = process_writing(row)
                        for key, val in result.items():
                            st.session_state.df.at[idx, key] = val
                else:
                    st.warning(f"Pominięto '{row['Słowo kluczowe']}' - brak struktury nagłówków.")
                
                progress_bar.progress((i + 1) / total)
            st.success("Pisanie zakończone!")
            st.rerun()

    # --- PODGLĄD SZCZEGÓŁÓW ---
    st.divider()
    st.subheader("🔍 Podgląd szczegółów wybranego wiersza")
    
    selected_row_idx = st.selectbox("Wybierz wiersz do podglądu:", st.session_state.df.index, format_func=lambda x: f"{x}: {st.session_state.df.iloc[x]['Słowo kluczowe']}")
    
    if selected_row_idx is not None:
        row_data = st.session_state.df.iloc[selected_row_idx]
        
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["Research", "Nagłówki", "RAG", "Brief", "Artykuł"])
        
        with tab1:
            st.json({
                "SERP": row_data['Frazy_SERP'],
                "Senuto": row_data['Frazy_Senuto'],
                "Graf": row_data['Graf_Informacji'],
                "Knowledge Graph": row_data['Knowledge_Graph']
            })
            
        with tab2:
            st.text_area("H2", row_data['Nagłówki_H2'], height=200)
            st.text_area("Rozbudowane", row_data['Nagłówki_Rozbudowane'], height=200)
            
        with tab3:
            st.text_area("RAG Content", row_data['RAG_Content'], height=300)
            
        with tab4:
            st.components.v1.html(row_data['Brief_HTML'], height=400, scrolling=True)
            with st.expander("Pokaż JSON Briefu"):
                st.code(row_data['Brief_JSON'], language='json')
                
        with tab5:
            if row_data['Artykuł']:
                st.markdown(row_data['Artykuł'], unsafe_allow_html=True)
                st.divider()
                st.text_area("Kod HTML Artykułu", row_data['Artykuł'], height=400)
            else:
                st.info("Artykuł nie został jeszcze wygenerowany.")