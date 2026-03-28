import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
import urllib.parse

# --- 1. PODEŠAVANJE ---
st.set_page_config(page_title="Poslovni Panel v7.0", layout="wide")

# --- 2. POVEZIVANJE ---
try:
    db_pass = st.secrets["DB_PASSWORD"]
    p_ref = st.secrets["PROJECT_REF"]
    app_pass = st.secrets["APP_LOGIN_SIFRA"]
    safe_pass = urllib.parse.quote_plus(db_pass)
    DB_URL = f"postgresql://postgres.{p_ref}:{safe_pass}@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    engine = create_engine(DB_URL, connect_args={"sslmode": "require"})
except Exception as e:
    st.error("Baza nije dostupna."); st.stop()

# --- 3. POMOĆNE FUNKCIJE ---
def izvrsi(upit, params=None):
    with engine.begin() as conn:
        conn.execute(text(upit), params or {})

def citaj(tabela, order_by=None):
    try:
        upit = f"SELECT * FROM {tabela}"
        if order_by: upit += f" ORDER BY {order_by}"
        return pd.read_sql(upit, engine)
    except: return pd.DataFrame()

# --- 4. NOVE TABELE I MIGRACIJA ---
def inicijalizacija_baze():
    # Tabela za kurire (osnovni podaci)
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    # Tabela za istoriju cena kurira
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri_cene (id SERIAL PRIMARY KEY, kurir_id INTEGER, cena REAL, datum_od DATE)")
    # Kupci i Roba
    izvrsi("CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL)")
    izvrsi("CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    # Glavna prodaja (sada čuva ID kurira i ID robe)
    izvrsi("""CREATE TABLE IF NOT EXISTS prodaja (
        id SERIAL PRIMARY KEY, datum DATE, kupac_id INTEGER, roba_id INTEGER, 
        komada INTEGER, bruto REAL, neto REAL, prevoz_tip TEXT, kurir_id INTEGER
    )""")

inicijalizacija_baze()

# --- 5. DIJALOZI ZA IZMENE ---
@st.dialog("Izmeni Artikal")
def izmeni_robu_dialog(row):
    novo_ime = st.text_input("Novi naziv", value=row['naziv'])
    if st.button("Sačuvaj"):
        izvrsi("UPDATE tipovi_robe SET naziv=:n WHERE id=:id", {"n": novo_ime, "id": row['id']})
        st.rerun()

@st.dialog("Izmeni Kupca")
def izmeni_kupca_dialog(row):
    n_ime = st.text_input("Ime", value=row['ime'])
    n_rabat = st.number_input("Rabat %", value=float(row['rabat']))
    if st.button("Ažuriraj"):
        izvrsi("UPDATE kupci SET ime=:i, rabat=:r WHERE id=:id", {"i": n_ime, "r": n_rabat, "id": row['id']})
        st.rerun()

# --- 6. LOGIN ---
if "auth" not in st.session_state: st.session_state["auth"] = False
if not st.session_state["auth"]:
    lozinka = st.text_input("Lozinka:", type="password")
    if st.button("Ulaz"):
        if lozinka == app_pass: st.session_state["auth"] = True; st.rerun()
    st.stop()

# --- 7. NAVIGACIJA ---
meni = st.sidebar.radio("Meni:", ["Pregled", "📝 Nova Faktura", "👥 Kupci", "📦 Katalog Robe", "🚚 Brza Pošta"])

# --- MODUL: PREGLED ---
if meni == "Pregled":
    st.title("Pregled")
    # Join upit da povučemo imena umesto ID-eva za prikaz
    query = """
        SELECT p.*, k.ime as kupac_ime, r.naziv as roba_ime, s.naziv as kurir_ime,
        (SELECT cena FROM kuriri_cene WHERE kurir_id = p.kurir_id AND datum_od <= p.datum ORDER BY datum_od DESC LIMIT 1) as cena_dostave
        FROM prodaja p
        LEFT JOIN kupci k ON p.kupac_id = k.id
        LEFT JOIN tipovi_robe r ON p.roba_id = r.id
        LEFT JOIN kuriri s ON p.kurir_id = s.id
        ORDER BY p.id DESC
    """
    df_p = pd.read_sql(query, engine)
    
    if not df_p.empty:
        df_p['cena_dostave'] = df_p['cena_dostave'].fillna(0)
        df_p['zarada_sa_postom'] = df_p['neto'] - df_p['cena_dostave']
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ukupno Neto (Bez pošte)", f"{df_p['neto'].sum():,.2f}")
        c2.metric("Ukupna Zarada (Sa poštom)", f"{df_p['zarada_sa_postom'].sum():,.2f}")
        c3.metric("Trošak dostave", f"{df_p['cena_dostave'].sum():,.2f}")
        
        st.dataframe(df_p[['id', 'datum', 'kupac_ime', 'roba_ime', 'komada', 'neto', 'zarada_sa_postom', 'kurir_ime']], width='stretch')
    else: st.info("Nema podataka.")

# --- MODUL: BRZA POŠTA (Istorija cena) ---
elif meni == "🚚 Brza Pošta":
    st.title("Brza Pošta & Istorija Cena")
    
    with st.form("novi_kurir"):
        n_kurir = st.text_input("Naziv nove službe")
        if st.form_submit_button("Dodaj službu"):
            izvrsi("INSERT INTO kuriri (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n_kurir})
            st.rerun()
            
    df_s = citaj("kuriri", "id ASC")
    if not df_s.empty:
        sel_kurir = st.selectbox("Izaberi službu za promenu cene:", [f"{r['id']} | {r['naziv']}" for _, r in df_s.iterrows()])
        k_id = int(sel_kurir.split(" | ")[0])
        
        with st.form("nova_cena"):
            c1, c2 = st.columns(2)
            n_cena = c1.number_input("Nova cena (RSD)", min_value=0.0)
            n_datum = c2.date_input("Važi od datuma", date.today())
            if st.form_submit_button("Ažuriraj cenu"):
                izvrsi("INSERT INTO kuriri_cene (kurir_id, cena, datum_od) VALUES (:id, :c, :d)", 
                       {"id": k_id, "c": n_cena, "d": n_datum})
                st.success("Cena proknjižena!")

        st.subheader("Istorija cena za izabranu službu")
        df_hist = pd.read_sql(f"SELECT * FROM kuriri_cene WHERE kurir_id = {k_id} ORDER BY datum_od DESC", engine)
        st.table(df_hist)

# --- MODUL: NOVA FAKTURA ---
elif meni == "📝 Nova Faktura":
    st.title("Nova Faktura")
    df_k = citaj("kupci", "id ASC")
    df_t = citaj("tipovi_robe", "id ASC")
    df_s = citaj("kuriri", "id ASC")
    
    if not df_k.empty and not df_t.empty:
        with st.form("f"):
            c1, c2 = st.columns(2)
            dat = c1.date_input("Datum", date.today())
            k_sel = c1.selectbox("Kupac", [f"{r['id']} | {r['ime']}" for _, r in df_k.iterrows()])
            r_sel = c2.selectbox("Roba", [f"{r['id']} | {r['naziv']}" for _, r in df_t.iterrows()])
            kol = c2.number_input("Komada", 1)
            bruto = c1.number_input("Bruto Iznos", 0.0)
            prevoz = c2.selectbox("Prevoz", ["Lično", "Kurir"])
            
            kurir_id = None
            if prevoz == "Kurir" and not df_s.empty:
                s_sel = c2.selectbox("Kurir", [f"{r['id']} | {r['naziv']}" for _, r in df_s.iterrows()])
                kurir_id = int(s_sel.split(" | ")[0])

            if st.form_submit_button("Proknjiži"):
                kid = int(k_sel.split(" | ")[0])
                rid = int(r_sel.split(" | ")[0])
                k_data = df_k[df_k['id'] == kid].iloc[0]
                neto = bruto * (1 - k_data['rabat']/100)
                
                izvrsi("""INSERT INTO prodaja (datum, kupac_id, roba_id, komada, bruto, neto, prevoz_tip, kurir_id) 
                       VALUES (:d, :ki, :ri, :ko, :b, :n, :pt, :si)""",
                       {"d": dat, "ki": kid, "ri": rid, "ko": kol, "b": bruto, "n": neto, "pt": prevoz, "si": kurir_id})
                st.rerun()

# --- MODUL: KATALOG ROBE ---
elif meni == "📦 Katalog Robe":
    st.title("Katalog Robe")
    with st.form("nr"):
        n = st.text_input("Naziv artikla")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n})
            st.rerun()
    
    df_t = citaj("tipovi_robe", "id ASC")
    for _, row in df_t.iterrows():
        c1, c2, c3 = st.columns([1, 4, 2])
        c1.write(f"ID: {row['id']}")
        c2.write(f"**{row['naziv']}**")
        if c3.button("✏️ Izmeni", key=f"e_{row['id']}"): izmeni_robu_dialog(row)
        if c3.button("🗑️", key=f"d_{row['id']}"): 
            izvrsi("DELETE FROM tipovi_robe WHERE id=:id", {"id": row['id']})
            st.rerun()
        st.divider()

# --- MODUL: KUPCI ---
elif meni == "👥 Kupci":
    st.title("Baza Kupaca")
    df_k = citaj("kupci", "id ASC")
    for _, row in df_k.iterrows():
        c1, c2, c3, c4 = st.columns([1, 3, 2, 2])
        c1.write(f"ID: {row['id']}")
        c2.write(row['ime'])
        c3.write(f"Rabat: {row['rabat']}%")
        if c4.button("✏️", key=f"ek_{row['id']}"): izmeni_kupca_dialog(row)
