import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
import urllib.parse

# --- 1. PODEŠAVANJE ---
st.set_page_config(page_title="Poslovni Panel v6.6", layout="wide")

# --- 2. POVEZIVANJE ---
try:
    db_pass = st.secrets["DB_PASSWORD"]
    p_ref = st.secrets["PROJECT_REF"]
    app_pass = st.secrets["APP_LOGIN_SIFRA"]
    safe_pass = urllib.parse.quote_plus(db_pass)
    DB_URL = f"postgresql://postgres.{p_ref}:{safe_pass}@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    engine = create_engine(DB_URL, connect_args={"sslmode": "require"})
except Exception as e:
    st.error("Greška sa bazom!"); st.stop()

# --- 3. POMOĆNE FUNKCIJE ---
def izvrsi(upit, params=None):
    with engine.begin() as conn:
        conn.execute(text(upit), params or {})

def citaj(tabela, order_by=None):
    try:
        upit = f"SELECT * FROM {tabela}"
        if order_by: upit += f" ORDER BY {order_by}"
        return pd.read_sql(upit, engine)
    except:
        return pd.DataFrame()

# --- 4. HARD RESET & FIX (Samo ako tabela pravi problem) ---
# Ovim osiguravamo da 'naziv' bude UNIQUE kako bi 'ON CONFLICT' radio
try:
    izvrsi("CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE, cena REAL)")
    izvrsi("CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL)")
    izvrsi("""CREATE TABLE IF NOT EXISTS prodaja (
        id SERIAL PRIMARY KEY, datum TEXT, kupac_info TEXT, roba TEXT, 
        komada INTEGER, bruto REAL, neto REAL, okrug TEXT, prevoz TEXT, kurir TEXT
    )""")
except Exception:
    pass # Ako su već ispravno napravljene, ne diraj

# --- 5. GEOGRAFIJA ---
SRBIJA_MAPA = {
    "Južnobački": ["Novi Sad", "Bačka Palanka", "Bečej", "Temerin", "Vrbas", "Bački Petrovac", "Beočin", "Titel", "Žabalj", "Srbobran"],
    "Grad Beograd": ["Beograd", "Mladenovac", "Lazarevac", "Obrenovac", "Barajevo", "Grocka", "Sopot", "Surčin"],
    "Mačvanski": ["Šabac", "Loznica", "Bogatić", "Vladimirci", "Koceljeva", "Mali Zvornik", "Krupanj", "Ljubovija"],
    "Nišavski": ["Niš", "Aleksinac", "Svrljig", "Merošina", "Ražanj", "Doljevac", "Gadžin Han"],
    "Severnobački": ["Subotica", "Bačka Topola", "Mali Iđoš"]
    # Dodaj ostale po potrebi, skratio sam zbog preglednosti koda
}
SVI_GRADOVI = sorted([g for lista in SRBIJA_MAPA.values() for g in lista])

# --- 6. LOGIN ---
if "auth" not in st.session_state: st.session_state["auth"] = False
if not st.session_state["auth"]:
    st.title("🔐 Ulaz u sistem")
    lozinka = st.text_input("Lozinka:", type="password")
    if st.button("Prijavi se"):
        if lozinka == app_pass: st.session_state["auth"] = True; st.rerun()
        else: st.error("Pogrešna lozinka!")
    st.stop()

# --- 7. NAVIGACIJA ---
st.sidebar.title("Meni")
meni = st.sidebar.radio("Izaberi sekciju:", ["📊 Pregled", "📝 Nova Faktura", "👥 Kupci", "📦 Katalog Robe", "🚚 Brza Pošta"])

# --- MODUL: BRZA POŠTA (REŠAVAMO PROBLEM) ---
if meni == "🚚 Brza Pošta":
    st.title("🚚 Upravljanje Kuririma")
    with st.form("n_kurir"):
        c_n = st.text_input("Naziv službe (npr. BEX, AKS)")
        c_c = st.number_input("Cena po paketu (RSD)", min_value=0.0)
        if st.form_submit_button("Sačuvaj"):
            if c_n:
                # Koristimo čistiji SQL bez ON CONFLICT ako nismo sigurni u constraint
                postoji = citaj("kuriri")
                if not postoji.empty and c_n.strip() in postoji['naziv'].values:
                    st.warning("Ova služba već postoji!")
                else:
                    izvrsi("INSERT INTO kuriri (naziv, cena) VALUES (:n, :c)", {"n": c_n.strip(), "c": c_c})
                    st.success("Dodato!"); st.rerun()

    df_s = citaj("kuriri", "naziv ASC")
    if not df_s.empty:
        for _, row in df_s.iterrows():
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(f"**{row['naziv']}**")
            c2.write(f"{row['cena']} RSD")
            if c3.button("🗑️ Obriši", key=f"d_{row['id']}"):
                izvrsi("DELETE FROM kuriri WHERE id=:id", {"id": row['id']})
                st.rerun()

# --- MODUL: PREGLED ---
elif meni == "📊 Pregled":
    st.title("📊 Glavni Dashboard")
    df_p = citaj("prodaja", "id DESC")
    if not df_p.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Ukupno Neto", f"{df_p['neto'].sum():,.2f} RSD")
        col2.metric("Faktura", len(df_p))
        col3.metric("Komada", int(df_p['komada'].sum()))
        st.dataframe(df_p, width='stretch')
    else: st.info("Nema podataka.")

# --- MODUL: NOVA FAKTURA ---
elif meni == "📝 Nova Faktura":
    st.title("📝 Nova Faktura")
    df_k = citaj("kupci", "ime ASC")
    df_t = citaj("tipovi_robe", "naziv ASC")
    df_s = citaj("kuriri", "naziv ASC")
    
    if not df_k.empty and not df_t.empty:
        with st.form("f_forma"):
            c1, c2 = st.columns(2)
            dat = c1.date_input("Datum", date.today())
            k_izbor = c1.selectbox("Kupac", [f"{r['ime']} | {r['grad']}" for _, r in df_k.iterrows()])
            artikal = c2.selectbox("Roba", df_t['naziv'])
            kol = c2.number_input("Količina", min_value=1)
            iznos = c1.number_input("Bruto (RSD)", min_value=0.0)
            prevoz = c2.selectbox("Prevoz:", ["Lično", "Kurir"])
            
            kurir_ime = "N/A"
            if prevoz == "Kurir" and not df_s.empty:
                kurir_ime = c2.selectbox("Služba:", df_s['naziv'])

            if st.form_submit_button("Sačuvaj"):
                f_ime, f_grad = k_izbor.split(" | ")
                k_data = df_k[(df_k['ime'] == f_ime) & (df_k['grad'] == f_grad)].iloc[0]
                neto = iznos * (1 - k_data['rabat']/100)
                izvrsi("INSERT INTO prodaja (datum, kupac_info, roba, komada, bruto, neto, okrug, prevoz, kurir) VALUES (:d, :k, :r, :ko, :b, :n, :o, :p, :ku)",
                       {"d": str(dat), "k": k_izbor, "r": artikal, "ko": kol, "b": iznos, "n": neto, "o": k_data['okrug'], "p": prevoz, "ku": kurir_ime})
                st.success("Uneto!"); st.rerun()
    else: st.warning("Prvo popuni katalog i kupce!")

# --- MODUL: KUPCI ---
elif meni == "👥 Kupci":
    st.title("👥 Kupci")
    with st.form("n_kupac"):
        c1, c2, c3 = st.columns(3)
        n_ime = c1.text_input("Ime firme")
        n_grad = c2.selectbox("Grad", SVI_GRADOVI)
        n_rabat = c3.number_input("Rabat %", 0.0)
        if st.form_submit_button("Dodaj Kupca"):
            okr = next((o for o, g in SRBIJA_MAPA.items() if n_grad in g), "Ostalo")
            izvrsi("INSERT INTO kupci (ime, grad, okrug, rabat) VALUES (:i, :g, :o, :r)", {"i": n_ime, "g": n_grad, "o": okr, "r": n_rabat})
            st.rerun()
    
    df_k = citaj("kupci", "ime ASC")
    st.dataframe(df_k, width='stretch')

# --- MODUL: KATALOG ROBE ---
elif meni == "📦 Katalog Robe":
    st.title("📦 Katalog")
    with st.form("n_roba"):
        n_art = st.text_input("Novi artikal")
        if st.form_submit_button("Dodaj u katalog"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT (naziv) DO NOTHING", {"n": n_art.strip()})
            st.rerun()
    
    df_t = citaj("tipovi_robe", "naziv ASC")
    if not df_t.empty:
        for _, row in df_t.iterrows():
            c1, c2 = st.columns([5, 1])
            c1.write(row['naziv'])
            if c2.button("🗑️", key=f"dr_{row['id']}"):
                izvrsi("DELETE FROM tipovi_robe WHERE id=:id", {"id": row['id']})
                st.rerun()
