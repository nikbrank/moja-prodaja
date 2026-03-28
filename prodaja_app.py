import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
import urllib.parse

# --- 1. PODEŠAVANJE STRANICE ---
st.set_page_config(page_title="Poslovni Panel v4.1", layout="wide")

# --- 2. POVEZIVANJE (Preko Secrets-a) ---
try:
    db_pass = st.secrets["DB_PASSWORD"]
    p_ref = st.secrets["PROJECT_REF"]
    app_pass = st.secrets["APP_LOGIN_SIFRA"]
    
    # Sigurno pakovanje lozinke za URL
    safe_pass = urllib.parse.quote_plus(db_pass)
    
    # Konekcija ka Supabase (AWS-1 Ireland)
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

# Geografska mapa za automatsko dodeljivanje okruga
SRBIJA_MAPA = {
    "Severnobački": ["Subotica", "Bačka Topola", "Mali Iđoš"],
    "Južnobački": ["Novi Sad", "Bačka Palanka", "Vrbas", "Temerin", "Bečej", "Žabalj", "Srbobran"],
    "Sremski": ["Sremska Mitrovica", "Inđija", "Stara Pazova", "Ruma", "Šid", "Pećinci", "Irig"],
    "Mačvanski": ["Šabac", "Loznica", "Bogatić", "Vladimirci"],
    "Grad Beograd": ["Beograd", "Mladenovac", "Lazarevac", "Obrenovac", "Surčin", "Barajevo", "Grocka", "Sopot"]
}
SVI_GRADOVI = sorted(list(set([g for lista in SRBIJA_MAPA.values() for g in lista])))

# Inicijalizacija tabela (ako ne postoje)
izvrsi("""
    CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL);
    CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS prodaja (
        id SERIAL PRIMARY KEY, datum TEXT, kupac TEXT, 
        roba TEXT, komada INTEGER, bruto REAL, neto REAL
    );
""")

# --- 5. NAVIGACIJA ---
st.sidebar.title("🏢 Poslovni Sistem v4.1")
meni = st.sidebar.radio("Navigacija:", ["📊 Dashboard", "📝 Nova Faktura", "👥 Kupci", "📦 Katalog Robe"])

# --- MODUL: DASHBOARD ---
if meni == "📊 Dashboard":
    st.title("📊 Izveštaji i Analitika")
    df_p = citaj("prodaja", "datum DESC")
    
    if not df_p.empty:
        # Metrike na vrhu
        c1, c2, c3 = st.columns(3)
        c1.metric("Ukupan Neto (RSD)", f"{df_p['neto'].sum():,.2f}")
        c2.metric("Broj Faktura", len(df_p))
        c3.metric("Prodatih Artikala", int(df_p['komada'].sum()))
        
        st.markdown("---")
        
        # Analitika po artiklima
        st.subheader("📦 Prodaja po tipu artikla")
        analitika_robe = df_p.groupby('roba').agg({
            'komada': 'sum',
            'neto': 'sum'
        }).reset_index().sort_values(by='neto', ascending=False)
        analitika_robe.columns = ['Naziv Artikla', 'Ukupno Komada', 'Ukupna Vrednost (Neto)']
        st.table(analitika_robe)
        
        st.markdown("---")
        st.subheader("📜 Istorija svih prodaja")
        st.dataframe(df_p, use_container_width=True)
    else:
        st.info("Baza je trenutno prazna. Unesite prvu fakturu u meniju sa strane.")

# --- MODUL: NOVA FAKTURA ---
elif meni == "📝 Nova Faktura":
    st.title("📝 Unos nove prodaje")
    df_k = citaj("kupci", "ime ASC")
    df_t = citaj("tipovi_robe", "naziv ASC")
    
    if not df_k.empty and not df_t.empty:
        with st.form("faktura_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            dat = c1.date_input("Datum", date.today())
            lista_prikaz = [f"{r['ime']} ({r['grad']})" for i, r in df_k.iterrows()]
            izabran_k_pun = c1.selectbox("Izaberi Kupca", lista_prikaz)
            
            ime_firme = izabran_k_pun.rsplit(" (", 1)[0]
            tip_robe = c2.selectbox("Artikal iz kataloga", df_t['naziv'])
            kolicina = c2.number_input("Broj komada", min_value=1)
            bruto_iznos = c1.number_input("Bruto Iznos (RSD)", min_value=0.0)
            
            rabat_kupca = df_k[df_k['ime'] == ime_firme]['rabat'].values[0]
            
            if st.form_submit_button("✅ Sačuvaj na Cloud"):
                neto_obracun = bruto_iznos * (1 - rabat_kupca/100)
                izvrsi("""INSERT INTO prodaja (datum, kupac, roba, komada, bruto, neto) 
                          VALUES (:d, :k, :r, :ko, :b, :n)""",
                       {"d": str(dat), "k": ime_firme, "r": tip_robe, "ko": kolicina, "b": bruto_iznos, "n": neto_obracun})
                st.success(f"Uspešno snimljeno! Neto iznos: {neto_obracun:,.2f} RSD")
    else:
        st.warning("Prvo morate popuniti listu Kupaca i Katalog Robe.")

# --- MODUL: KUPCI ---
elif meni == "👥 Kupci":
    st.title("👥 Baza Kupaca")
    tab1, tab2 = st.tabs(["➕ Dodaj Kupca", "🔍 Lista i Brisanje"])

    with tab1:
        with st.form("novi_kupac_form", clear_on_submit=True):
            f_ime = st.text_input("Naziv Firme")
            f_grad = st.selectbox("Grad", SVI_GRADOVI)
            f_rabat = st.number_input("Rabat (%)", min_value=0.0)
            f_okrug = next((o for o, g in SRBIJA_MAPA.items() if f_grad in g), "Ostalo")
            
            if st.form_submit_button("Sačuvaj Kupca"):
                izvrsi("INSERT INTO kupci (ime, grad, okrug, rabat) VALUES (:i, :g, :o, :r)", 
                       {"i": f_ime, "g": f_grad, "o": f_okrug, "r": f_rabat})
                st.success("Kupac uspešno dodat!")
                st.rerun()

    with tab2:
        df_k_prikaz = citaj("kupci", "ime ASC")
        if not df_k_prikaz.empty:
            st.dataframe(df_k_prikaz[['ime', 'grad', 'okrug', 'rabat']], use_container_width=True)
            k_bris = st.selectbox("Izaberi kupca za brisanje:", df_k_prikaz['ime'])
            if st.button("❌ Obriši kupca"):
                izvrsi("DELETE FROM kupci WHERE ime = :i", {"i": k_bris})
                st.rerun()

# --- MODUL: KATALOG ROBE ---
elif meni == "📦 Katalog Robe":
    st.title("📦 Katalog Robe / Usluga")
    with st.form("katalog_form", clear_on_submit=True):
        n_art = st.text_input("Naziv artikla (Bočna fioka, Džambo šina, Korpa za veš...)")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n_art.strip()})
            st.rerun()
    
    df_t_prikaz = citaj("tipovi_robe", "naziv ASC")
    st.dataframe(df_t_prikaz, use_container_width=True)
    if not df_t_prikaz.empty:
        r_bris = st.selectbox("Izaberi artikal za uklanjanje:", df_t_prikaz['naziv'])
        if st.button("🗑️ Ukloni iz kataloga"):
            izvrsi("DELETE FROM tipovi_robe WHERE naziv = :n", {"n": r_bris})
            st.rerun()
