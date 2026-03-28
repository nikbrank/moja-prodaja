import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
import urllib.parse

# --- 1. PODEŠAVANJE STRANICE ---
st.set_page_config(page_title="Poslovni Panel v3.0", layout="wide")

# --- 2. POVEZIVANJE (Secrets) ---
try:
    db_pass = st.secrets["DB_PASSWORD"]
    p_ref = st.secrets["PROJECT_REF"]
    app_pass = st.secrets["APP_LOGIN_SIFRA"]
    
    # Enkodovanje lozinke za siguran URL prenos
    safe_pass = urllib.parse.quote_plus(db_pass)
    
    # Glavni URL ka Supabase (AWS-1 Ireland)
    DB_URL = f"postgresql://postgres.{p_ref}:{safe_pass}@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    engine = create_engine(DB_URL, connect_args={"sslmode": "require"})
except KeyError as e:
    st.error(f"Greška: Nedostaje ključ u secrets.toml -> {e}")
    st.stop()

# --- 3. LOGIN SISTEM ---
if "autentifikovan" not in st.session_state:
    st.session_state["autentifikovan"] = False

if not st.session_state["autentifikovan"]:
    st.title("🔐 Privatni Cloud Panel")
    lozinka = st.text_input("Unesi lozinku za pristup:", type="password")
    if st.button("Prijavi se"):
        if lozinka == app_pass:
            st.session_state["autentifikovan"] = True
            st.rerun()
        else:
            st.error("Netačna lozinka!")
    st.stop()

# --- 4. FUNKCIJE ZA RAD SA BAZOM ---
def izvrsi(upit, params=None):
    with engine.begin() as conn:
        conn.execute(text(upit), params or {})

def citaj(tabela, order_by=None):
    upit = f"SELECT * FROM {tabela}"
    if order_by: upit += f" ORDER BY {order_by}"
    return pd.read_sql(upit, engine)

# Inicijalizacija tabela (ako ne postoje)
izvrsi("""
    CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, rabat REAL);
    CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS prodaja (
        id SERIAL PRIMARY KEY, datum TEXT, kupac TEXT, 
        roba TEXT, komada INTEGER, bruto REAL, neto REAL
    );
""")

# --- 5. NAVIGACIJA ---
st.sidebar.title("🏢 Cloud Panel v3")
meni = st.sidebar.radio("Navigacija:", ["📊 Dashboard", "📝 Nova Faktura", "👥 Kupci", "📦 Katalog Robe"])

# --- MODUL: DASHBOARD ---
if meni == "📊 Dashboard":
    st.title("📊 Analitika Prodaje")
    df_p = citaj("prodaja", "datum DESC")
    
    if not df_p.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Ukupan Neto Promet", f"{df_p['neto'].sum():,.2f} RSD")
        c2.metric("Broj Prodaja", len(df_p))
        c3.metric("Prodatih Komada", int(df_p['komada'].sum()))
        
        st.subheader("Poslednje transakcije")
        st.dataframe(df_p, use_container_width=True)
    else:
        st.info("Još uvek nema unetih prodaja.")

# --- MODUL: NOVA FAKTURA ---
elif meni == "📝 Nova Faktura":
    st.title("📝 Unos Prodaje")
    df_k = citaj("kupci", "ime ASC")
    df_t = citaj("tipovi_robe", "naziv ASC")
    
    if not df_k.empty and not df_t.empty:
        with st.form("faktura_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            dat = c1.date_input("Datum", date.today())
            izabran_k = c1.selectbox("Kupac", df_k['ime'])
            
            izabrana_r = c2.selectbox("Tip robe", df_t['naziv'])
            komada = c2.number_input("Količina", min_value=1)
            iznos = c1.number_input("Bruto Iznos (RSD)", min_value=0.0)
            
            # Automatsko povlačenje rabata za izabranog kupca
            r_val = df_k[df_k['ime'] == izabran_k]['rabat'].values[0]
            st.caption(f"Podrazumevani rabat za ovog kupca: {r_val}%")
            
            if st.form_submit_button("Sačuvaj na Cloud"):
                neto_v = iznos * (1 - r_val/100)
                izvrsi("""INSERT INTO prodaja (datum, kupac, roba, komada, bruto, neto) 
                          VALUES (:d, :k, :r, :ko, :b, :n)""",
                       {"d": str(dat), "k": izabran_k, "r": izabrana_r, "ko": komada, "b": iznos, "n": neto_v})
                st.success("Uspešno snimljeno u bazu!")
    else:
        st.warning("Prvo dodajte kupce i katalog robe u meniju sa strane.")

# --- MODUL: KUPCI ---
elif meni == "👥 Kupci":
    st.title("👥 Baza Kupaca")
    with st.expander("➕ Dodaj novog kupca"):
        with st.form("novi_kupac"):
            ime = st.text_input("Naziv firme")
            grad = st.text_input("Grad")
            rabat = st.number_input("Rabat (%)", min_value=0.0, max_value=100.0)
            if st.form_submit_button("Sačuvaj Kupca"):
                izvrsi("INSERT INTO kupci (ime, grad, rabat) VALUES (:i, :g, :r)", 
                       {"i": ime, "g": grad, "r": rabat})
                st.success("Kupac dodat!")
                st.rerun()
    
    st.dataframe(citaj("kupci", "ime ASC"), use_container_width=True)

# --- MODUL: KATALOG ROBE ---
elif meni == "📦 Katalog Robe":
    st.title("📦 Katalog Robe / Usluga")
    with st.form("nova_roba"):
        n_artikal = st.text_input("Naziv artikla (npr. CNC Sečenje, Drvo, Usluga...)")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n_artikal.strip()})
            st.rerun()
    
    df_t = citaj("tipovi_robe", "naziv ASC")
    st.dataframe(df_t, use_container_width=True)