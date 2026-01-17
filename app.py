import streamlit as st
import pandas as pd
import requests
import re
import time
from supabase import create_client, Client

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="SEO 3.0 Content Machine (DB)", page_icon="🤖", layout="wide")

# --- STYLE CSS ---
st.markdown("""
<style>
    .block-container {padding-top: 1rem;}
    .stProgress > div > div > div > div { background-color: #4CAF50; }
</style>
""", unsafe_allow_html=True)

# --- MAPOWANIE KOLUMN (BAZA -> UI) ---
# Klucz: nazwa w bazie Supabase, Wartość: nazwa wyświetlana w Streamlit
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
    'headers_final': 'Nagłówki (Finalne)', # NOWA KOLUMNA
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

# Odwrócona mapa do zapisywania
REVERSE_COLUMN_MAP = {v: k for k, v in COLUMN_MAP.items()}

# --- SUPABASE INIT ---
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE"]["URL"]
    key = st.secrets["SUPABASE"]["KEY"]
    return create_client(url, key)

supabase = init_supabase()

# --- FUNKCJE BAZODANOWE ---

def fetch_data():
    """Pobiera dane z Supabase i zwraca DataFrame z ładnymi nazwami kolumn."""
    response = supabase.table("seo_content_tasks").select("*").order("id", desc=True).execute()
    data = response.data
    if not data:
        return pd.DataFrame(columns=COLUMN_MAP.values())
    
    df = pd.DataFrame(data)
    # Zmiana nazw kolumn na czytelne dla użytkownika
    df = df.rename(columns=COLUMN_MAP)
    return df

def add_record(keyword, lang, aio):
    """Dodaje nowy wiersz do bazy."""
    new_data = {
        "keyword": keyword,
        "language": lang,
        "aio_prompt": aio,
        "headers_final": "" # Inicjalizacja pustego pola
    }
    supabase.table("seo_content_tasks").insert(new_data).execute()

def update_record_in_db(row_id, updates):
    """Aktualizuje konkretne pola w bazie dla danego ID."""
    supabase.table("seo_content_tasks").update(updates).eq("id", row_id).execute()

def save_editor_changes(edited_df):
    """Zapisuje zmiany wprowadzone ręcznie w edytorze Streamlit."""
    # To jest uproszczona wersja - iterujemy po wierszach i aktualizujemy.
    # W produkcji dla dużej skali robi się to inaczej (tylko zmienione), ale tu wystarczy.
    
    # Zamiana nazw kolumn z powrotem na nazwy bazodanowe
    db_df = edited_df.rename(columns=REVERSE_COLUMN_MAP)
    
    # Konwersja do listy słowników
    records = db_df.to_dict('records')
    
    # Upsert (aktualizacja na podstawie ID)
    for record in records:
        if record.get('id'):
            supabase.table("seo_content_tasks").upsert(record).execute()

# --- FUNKCJE DIFY (BEZ ZMIAN W LOGICE, TYLKO W ZAPISIE) ---

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
        response = requests.post(url, headers=headers, json=payload, timeout=400)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# --- PROCESORY LOGIKI ---

def process_research(row_id, keyword, lang, aio):
    inputs = {"keyword": keyword, "language": lang, "aio": aio if aio else ""}
    resp = run_dify_workflow(st.secrets['dify']['API_KEY_RESEARCH'], inputs)
    
    updates = {}
    if "data" in resp and "outputs" in resp["data"]:
        out = resp["data"]["outputs"]
        updates = {
            "status_research": "✅ Gotowe",
            "serp_phrases": out.get("frazy z serp", ""),
            "senuto_phrases": out.get("frazy_senuto", ""),
            "info_graph": out.get("grafinformacji", ""),
            "competitors_headers": out.get("naglowki", ""),
            "knowledge_graph": out.get("knowledge_graph", "")
        }
    else:
        updates = {"status_research": f"❌ Błąd: {resp.get('error', 'Unknown')}"}
    
    update_record_in_db(row_id, updates)

def process_headers(row_id, keyword, lang, phrases_serp, phrases_senuto, info_graph, comp_headers):
    frazy_full = f"{phrases_serp}\n{phrases_senuto}"
    inputs = {
        "keyword": keyword,
        "language": lang,
        "frazy": frazy_full,
        "graf": info_graph,
        "headings": comp_headers
    }
    resp = run_dify_workflow(st.secrets['dify']['API_KEY_HEADERS'], inputs)
    
    updates = {}
    if "data" in resp and "outputs" in resp["data"]:
        out = resp["data"]["outputs"]
        # Automatycznie wpisujemy H2 do Finalnych, jeśli są puste, żeby ułatwić pracę
        # Ale użytkownik może je zmienić w edytorze przed generowaniem
        h2_content = out.get("naglowki_h2", "")
        
        updates = {
            "status_headers": "✅ Gotowe",
            "headers_expanded": out.get("naglowki_rozbudowane", ""),
            "headers_h2": h2_content,
            "headers_questions": out.get("naglowki_pytania", ""),
            # Domyślnie kopiujemy H2 do finalnych, chyba że użytkownik coś tam już ma (ale API nadpisuje zazwyczaj)
            "headers_final": h2_content 
        }
    else:
        updates = {"status_headers": f"❌ Błąd: {resp.get('error', 'Unknown')}"}
    
    update_record_in_db(row_id, updates)

def process_rag(row_id, keyword, lang, comp_headers):
    inputs = {"keyword": keyword, "language": lang, "headings": comp_headers}
    resp = run_dify_workflow(st.secrets['dify']['API_KEY_RAG'], inputs)
    
    updates = {}
    if "data" in resp and "outputs" in resp["data"]:
        out = resp["data"]["outputs"]
        updates = {
            "status_rag": "✅ Gotowe",
            "rag_content": out.get("dokladne", ""),
            "rag_general": out.get("ogolne", "")
        }
    else:
        updates = {"status_rag": f"❌ Błąd: {resp.get('error', 'Unknown')}"}
    
    update_record_in_db(row_id, updates)

def process_brief(row_id, keyword, phrases_serp, phrases_senuto, headers_h2, knowledge_graph, info_graph):
    frazy_full = f"{phrases_serp}\n{phrases_senuto}"
    inputs = {
        "keyword": keyword,
        "keywords": frazy_full,
        "headings": headers_h2,
        "knowledge_graph": knowledge_graph,
        "information_graph": info_graph
    }
    resp = run_dify_workflow(st.secrets['dify']['API_KEY_BRIEF'], inputs)
    
    updates = {}
    if "data" in resp and "outputs" in resp["data"]:
        out = resp["data"]["outputs"]
        updates = {
            "status_brief": "✅ Gotowe",
            "brief_json": out.get("brief", ""),
            "brief_html": out.get("html", "")
        }
    else:
        updates = {"status_brief": f"❌ Błąd: {resp.get('error', 'Unknown')}"}
    
    update_record_in_db(row_id, updates)

def extract_headers_from_text(text):
    """Wyciąga nagłówki z tekstu. Obsługuje tagi HTML <h2> lub zwykłe linie tekstu."""
    if not isinstance(text, str):
        return []
    
    # 1. Próba znalezienia tagów HTML <h2>
    html_headers = re.findall(r'<h2.*?>(.*?)</h2>', text, re.IGNORECASE)
    if html_headers:
        return [re.sub(r'<.*?>', '', h).strip() for h in html_headers]
    
    # 2. Jeśli brak HTML, zakładamy, że każda linia to nagłówek (fallback)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    # Filtrujemy bardzo krótkie linie lub śmieci, jeśli to konieczne
    return lines

def process_writing(row_id, keyword, lang, headers_final, headers_expanded, rag_content, rag_general, phrases_serp, phrases_senuto, instructions):
    """Generowanie contentu na podstawie kolumny 'Nagłówki (Finalne)'"""
    
    # UŻYWAMY KOLUMNY FINALNEJ!
    headers_list = extract_headers_from_text(headers_final)
    
    if not headers_list:
        update_record_in_db(row_id, {"status_writing": "❌ Brak nagłówków w kolumnie 'Finalne'"})
        return

    full_knowledge = f"{rag_content}\n{rag_general}"
    full_keywords = f"{phrases_serp}, {phrases_senuto}"
    
    article_content = ""
    
    # Aktualizacja statusu na start
    update_record_in_db(row_id, {"status_writing": "⏳ W trakcie..."})
    
    for h2 in headers_list:
        inputs = {
            "naglowek": h2,
            "language": lang,
            "knowledge": full_knowledge,
            "keywords": full_keywords,
            "headings": headers_expanded, 
            "done": article_content,
            "keyword": keyword,
            "instruction": instructions
        }
        
        resp = run_dify_workflow(st.secrets['dify']['API_KEY_WRITE'], inputs)
        
        if "data" in resp and "outputs" in resp["data"]:
            section_content = resp["data"]["outputs"].get("result", "")
            article_content += f"<h2>{h2}</h2>\n{section_content}\n\n"
            # Opcjonalnie: Zapisuj częściowo po każdej sekcji (bezpieczniej przy długich artach)
            update_record_in_db(row_id, {"final_article": article_content})
        else:
            article_content += f"<h2>{h2}</h2>\n[BŁĄD DIFY]\n\n"
    
    update_record_in_db(row_id, {
        "status_writing": "✅ Gotowe",
        "final_article": article_content
    })


# --- AUTORYZACJA ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        pwd = st.text_input("Hasło dostępu", type="password")
        if pwd:
            if pwd == st.secrets["general"]["APP_PASSWORD"]:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Nieprawidłowe hasło")
        return False
    return True

# --- MAIN APP ---
if check_password():
    st.title("🚀 SEO 3.0 Content Manager (Supabase)")
    
    # POBRANIE DANYCH
    if "data_version" not in st.session_state:
        st.session_state.data_version = 0

    df = fetch_data()

    # SIDEBAR
    with st.sidebar:
        st.header("Dodaj temat")
        new_kw = st.text_input("Słowo kluczowe")
        new_lang = st.text_input("Język", value="pl")
        new_aio = st.text_area("AIO (opcjonalnie)")
        
        if st.button("Dodaj"):
            add_record(new_kw, new_lang, new_aio)
            st.success("Dodano!")
            st.session_state.data_version += 1
            st.rerun()
            
        st.divider()
        if st.button("Odśwież dane 🔄"):
            st.rerun()

    # DATA EDITOR
    st.subheader("Baza tematów")
    
    # Konfiguracja edytora - ukrywamy ID, ale potrzebujemy go do logiki
    edited_df = st.data_editor(
        df,
        key="main_editor",
        height=400,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ID": st.column_config.NumberColumn(disabled=True),
            "Generowanie contentu": st.column_config.TextColumn(width="large"),
            "Nagłówki (Finalne)": st.column_config.TextColumn(width="medium", help="Tutaj wpisz/edytuj nagłówki, które pójdą do generowania treści")
        }
    )

    # Przycisk do zapisu ręcznych zmian
    if st.button("💾 Zapisz ręczne zmiany w tabeli"):
        save_editor_changes(edited_df)
        st.success("Zmiany zapisane w Supabase!")
        time.sleep(1)
        st.rerun()

    # AKCJE MASOWE
    st.divider()
    st.subheader("Akcje Automatyczne")
    
    # Wybór wierszy (symulacja - w data_editor nie ma checkboxów defaultowo, 
    # więc działamy na zasadzie: wykonaj dla wszystkich, które mają status 'Oczekuje' lub wykonaj dla konkretnego ID z selectboxa)
    
    # Dla uproszczenia interfejsu zrobimy panel akcji dla wybranego wiersza lub "Dla wszystkich przefiltrowanych"
    # Ale najprościej i najbezpieczniej: Przyciski iterują po tabeli z ekranu.
    
    c1, c2, c3, c4, c5 = st.columns(5)
    
    with c1:
        if st.button("1. RESEARCH 🔍"):
            progress = st.progress(0)
            rows = edited_df.to_dict('records')
            for i, row in enumerate(rows):
                # Możesz dodać warunek if row['Status Research'] != '✅ Gotowe':
                process_research(row['ID'], row['Słowo kluczowe'], row['Język'], row['AIO'])
                progress.progress((i+1)/len(rows))
            st.success("Zakończono Research")
            st.rerun()

    with c2:
        if st.button("2. NAGŁÓWKI 📑"):
            progress = st.progress(0)
            rows = edited_df.to_dict('records')
            for i, row in enumerate(rows):
                if row['Status Research'] == '✅ Gotowe':
                    process_headers(row['ID'], row['Słowo kluczowe'], row['Język'], 
                                    row['Frazy z wyników'], row['Frazy Senuto'], row['Graf informacji'], row['Nagłówki konkurencji'])
                progress.progress((i+1)/len(rows))
            st.success("Zakończono Nagłówki")
            st.rerun()

    with c3:
        if st.button("3. RAG 🧠"):
            progress = st.progress(0)
            rows = edited_df.to_dict('records')
            for i, row in enumerate(rows):
                if row['Nagłówki konkurencji']:
                    process_rag(row['ID'], row['Słowo kluczowe'], row['Język'], row['Nagłówki konkurencji'])
                progress.progress((i+1)/len(rows))
            st.success("Zakończono RAG")
            st.rerun()

    with c4:
        if st.button("4. BRIEF 📝"):
            progress = st.progress(0)
            rows = edited_df.to_dict('records')
            for i, row in enumerate(rows):
                # Brief wymaga H2. Możemy użyć Finalnych jeśli są, lub H2. Tu używamy H2 wg Twojego poprzedniego opisu.
                if row['Nagłówki H2']: 
                    process_brief(row['ID'], row['Słowo kluczowe'], row['Frazy z wyników'], row['Frazy Senuto'], 
                                  row['Nagłówki H2'], row['Knowledge graph'], row['Graf informacji'])
                progress.progress((i+1)/len(rows))
            st.success("Zakończono Brief")
            st.rerun()
            
    with c5:
        if st.button("5. GENERUJ ✍️"):
            st.info("Generowanie z kolumny 'Nagłówki (Finalne)'...")
            progress = st.progress(0)
            rows = edited_df.to_dict('records')
            for i, row in enumerate(rows):
                # Sprawdzamy czy są nagłówki finalne
                if row['Nagłówki (Finalne)'] and row['Status Research'] == '✅ Gotowe':
                    process_writing(
                        row['ID'], row['Słowo kluczowe'], row['Język'],
                        row['Nagłówki (Finalne)'], # Źródło struktury
                        row['Nagłówki rozbudowane'], # Kontekst
                        row['RAG'], row['RAG General'],
                        row['Frazy z wyników'], row['Frazy Senuto'],
                        row['Dodatkowe instrukcje']
                    )
                progress.progress((i+1)/len(rows))
            st.success("Zakończono generowanie")
            st.rerun()

    # PODGLĄD SZCZEGÓŁÓW (DOMYŚLNIE UKRYTY)
    st.divider()
    
    # Lista wyboru wiersza
    if not df.empty:
        options = {f"{r['ID']}: {r['Słowo kluczowe']}": r['ID'] for index, r in df.iterrows()}
        selected_label = st.selectbox("Wybierz wiersz do analizy:", list(options.keys()))
        selected_id = options[selected_label]
        
        # Pobieramy aktualny wiersz z DataFrame (edited_df ma najświeższe dane z UI)
        row_data = edited_df[edited_df['ID'] == selected_id].iloc[0]

        # EXPANDER DOMYŚLNIE ZWINIĘTY (expanded=False)
        with st.expander(f"🔍 Podgląd szczegółów: {row_data['Słowo kluczowe']}", expanded=False):
            
            t1, t2, t3, t4, t5 = st.tabs(["1. Research", "2. Nagłówki (Wszystkie)", "3. RAG", "4. Brief", "5. Wynik"])
            
            with t1:
                c_a, c_b = st.columns(2)
                with c_a:
                    st.text_area("Frazy SERP", row_data['Frazy z wyników'], height=200)
                    st.text_area("Graf Informacji", row_data['Graf informacji'], height=200)
                with c_b:
                    st.text_area("Frazy Senuto", row_data['Frazy Senuto'], height=200)
                    st.text_area("Knowledge Graph", row_data['Knowledge graph'], height=200)

            with t2:
                # WSZYSTKIE TYPY NAGŁÓWKÓW
                st.markdown("#### Edytuj 'Nagłówki (Finalne)' tutaj lub w głównej tabeli")
                st.info("To pole 'Nagłówki (Finalne)' jest używane w kroku 5 do generowania treści.")
                
                col_h1, col_h2 = st.columns(2)
                with col_h1:
                    st.text_area("Nagłówki H2 (z AI)", row_data['Nagłówki H2'], height=300)
                    st.text_area("Nagłówki Pytania (z AI)", row_data['Nagłówki pytania'], height=300)
                with col_h2:
                    st.text_area("Nagłówki Rozbudowane (Kontekst)", row_data['Nagłówki rozbudowane'], height=300)
                    st.text_area("🔹 Nagłówki (Finalne) - ŹRÓDŁO GENERACJI", row_data['Nagłówki (Finalne)'], height=300, key=f"final_h_{selected_id}")

            with t3:
                st.text_area("RAG Dokładny", row_data['RAG'], height=300)
                st.text_area("RAG Ogólny", row_data['RAG General'], height=300)

            with t4:
                if row_data['Brief plik']:
                    st.components.v1.html(row_data['Brief plik'], height=500, scrolling=True)
                else:
                    st.info("Brak wygenerowanego briefu HTML")
                
                with st.expander("Zobacz JSON Briefu"):
                    st.code(row_data['Brief'], language='json')

            with t5:
                if row_data['Generowanie contentu']:
                    st.markdown("### Podgląd wyrenderowany:")
                    st.markdown(row_data['Generowanie contentu'], unsafe_allow_html=True)
                    st.divider()
                    st.markdown("### Kod HTML:")
                    st.code(row_data['Generowanie contentu'], language='html')
                else:
                    st.warning("Jeszcze nie wygenerowano treści.")