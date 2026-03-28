import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
import urllib.parse

# --- 1. PODEŠAVANJE ---
st.set_page_config(page_title="Poslovni Panel v7.4", layout="wide")

# --- 2. KONEKCIJA ---
try:
    db_pass = st.secrets["DB_PASSWORD"]
    p_ref = st.secrets["PROJECT_REF"]
    app_pass = st.secrets["APP_LOGIN_SIFRA"]
    safe_pass = urllib.parse.quote_plus(db_pass)
    DB_URL = f"postgresql://postgres.{p_ref}:{safe_pass}@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    engine = create_engine(DB_URL, connect_args={"sslmode": "require"})
except Exception:
    st.error("Baza nedostupna!"); st.stop()

# --- 3. POMOĆNE FUNKCIJE ---
def izvrsi(upit, params=None):
    with engine.begin() as conn:
        conn.execute(text(upit), params or {})

def citaj(tabela, order_by="id ASC"):
    try:
        return pd.read_sql(f"SELECT * FROM {tabela} ORDER BY {order_by}", engine)
    except:
        return pd.DataFrame()

# --- 4. POPRAVKA TIPOVA PODATAKA (MIGRACIJA) ---
def totalni_remont():
    izvrsi("CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri_cene (id SERIAL PRIMARY KEY, kurir_id INTEGER, cena REAL, datum_od DATE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL)")
    izvrsi("CREATE TABLE IF NOT EXISTS prodaja (id SERIAL PRIMARY KEY, datum TEXT)")

    # Popravljamo tip kolone 'datum' u prodaji ako je TEXT
    try:
        izvrsi("ALTER TABLE prodaja ALTER COLUMN datum TYPE DATE USING datum::DATE")
    except: pass

    # Dodajemo ostale kolone koje možda fale
    kolone = [
        ("kupac_id", "INTEGER"), ("roba_id", "INTEGER"), ("komada", "INTEGER"),
        ("bruto", "REAL"), ("neto", "REAL"), ("prevoz_tip", "TEXT"), ("kurir_id", "INTEGER")
    ]
    for col, tip in kolone:
        try:
            izvrsi(f"ALTER TABLE prodaja ADD COLUMN {col} {tip}")
        except: pass

totalni_remont()

# --- 5. LOGIN ---
if "auth" not in st.session_state: st.session_state["auth"] = False
if not st.session_state["auth"]:
    l = st.text_input("Šifra:", type="password")
    if st.button("Ulaz"):
        if l == app_pass: st.session_state["auth"] = True; st.rerun()
    st.stop()

# --- 6. NAVIGACIJA ---
meni = st.sidebar.radio("Meni:", ["Pregled", "📝 Nova Faktura", "👥 Kupci", "📦 Katalog Robe", "🚚 Brza Pošta"])

# --- MODUL: PREGLED ---
if meni == "Pregled":
    st.title("Pregled")
    # DODATO ::DATE DA REŠI GREŠKU SA OPERATOROM
    query = """
        SELECT p.id, p.datum, k.ime as kupac, r.naziv as artikal, p.komada, p.neto, p.prevoz_tip, s.naziv as kurir,
        (SELECT cena FROM kuriri_cene 
         WHERE kurir_id = p.kurir_id 
         AND datum_od <= p.datum::DATE 
         ORDER BY datum_od DESC LIMIT 1) as cena_kurira
        FROM prodaja p
        LEFT JOIN kupci k ON p.kupac_id = k.id
        LEFT JOIN tipovi_robe r ON p.roba_id = r.id
        LEFT JOIN kuriri s ON p.kurir_id = s.id
        ORDER BY p.id DESC
    """
    try:
        df_p = pd.read_sql(query, engine)
        if not df_p.empty:
            df_p['cena_kurira'] = df_p['cena_kurira'].fillna(0)
            df_p['zarada_sa_postom'] = df_p['neto'] - df_p['cena_kurira']
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Neto Prodaja", f"{df_p['neto'].sum():,.2f} RSD")
            c2.metric("Čista Zarada", f"{df_p['zarada_sa_postom'].sum():,.2f} RSD")
            c3.metric("Trošak dostave", f"{df_p['cena_kurira'].sum():,.2f} RSD")
            
            st.dataframe(df_p, use_container_width=True)
        else: st.info("Nema unetih podataka.")
    except Exception as e:
        st.error(f"SQL Greška: {e}")

# --- MODUL: BRZA POŠTA (Istorija cena) ---
elif meni == "🚚 Brza Pošta":
    st.title("🚚 Brza Pošta & Istorija Cena")
    with st.form("n_k"):
        n_ime = st.text_input("Naziv nove službe")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO kuriri (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n_ime})
            st.rerun()
    
    df_s = citaj("kuriri")
    if not df_s.empty:
        sel = st.selectbox("Izaberi službu za promenu cene:", [f"{r['id']} | {r['naziv']}" for _, r in df_s.iterrows()])
        kid = int(sel.split(" | ")[0])
        
        with st.form("n_c"):
            v = st.number_input("Cena (RSD)", min_value=0.0)
            d = st.date_input("Važi od datuma", date.today())
            if st.form_submit_button("Sačuvaj cenu"):
                izvrsi("INSERT INTO kuriri_cene (kurir_id, cena, datum_od) VALUES (:id, :c, :d)", {"id": kid, "c": v, "d": d})
                st.success("Cena ažurirana!"); st.rerun()
        
        st.subheader("Istorija cena")
        st.dataframe(pd.read_sql(f"SELECT id, cena, datum_od FROM kuriri_cene WHERE kurir_id={kid} ORDER BY datum_od DESC", engine), use_container_width=True)

# --- MODUL: KATALOG ROBE ---
elif meni == "📦 Katalog Robe":
    st.title("📦 Katalog Robe")
    with st.form("n_r"):
        n_art = st.text_input("Naziv artikla")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n_art})
            st.rerun()
    
    df_t = citaj("tipovi_robe")
    for _, r in df_t.iterrows():
        c1, c2, c3 = st.columns([1, 4, 1])
        c1.write(f"ID: {r['id']}")
        c2.write(f"**{r['naziv']}**")
        if c3.button("🗑️", key=f"dr_{r['id']}"):
            izvrsi("DELETE FROM tipovi_robe WHERE id=:id", {"id": r['id']})
            st.rerun()
        st.divider()

# --- MODUL: NOVA FAKTURA ---
elif meni == "📝 Nova Faktura":
    st.title("Nova Faktura")
    df_k, df_t, df_s = citaj("kupci"), citaj("tipovi_robe"), citaj("kuriri")
    if not df_k.empty and not df_t.empty:
        with st.form("f"):
            c1, c2 = st.columns(2)
            dat = c1.date_input("Datum", date.today())
            k_s = c1.selectbox("Kupac (ID | Ime)", [f"{r['id']} | {r['ime']}" for _, r in df_k.iterrows()])
            r_s = c2.selectbox("Roba (ID | Naziv)", [f"{r['id']} | {r['naziv']}" for _, r in df_t.iterrows()])
            ko = c2.number_input("Komada", 1)
            b = c1.number_input("Bruto Iznos", 0.0)
            pt = c2.selectbox("Prevoz", ["Lično", "Kurir"])
            
            si = None
            if pt == "Kurir" and not df_s.empty:
                s_s = c2.selectbox("Služba", [f"{r['id']} | {r['naziv']}" for _, r in df_s.iterrows()])
                si = int(s_s.split(" | ")[0])
            
            if st.form_submit_button("Proknjiži"):
                kid, rid = int(k_s.split(" | ")[0]), int(r_s.split(" | ")[0])
                rabat = df_k[df_k['id'] == kid]['rabat'].values[0]
                n_iznos = b * (1 - rabat/100)
                izvrsi("INSERT INTO prodaja (datum, kupac_id, roba_id, komada, bruto, neto, prevoz_tip, kurir_id) VALUES (:d,:ki,:ri,:ko,:b,:n,:pt,:si)",
                       {"d": dat, "ki": kid, "ri": rid, "ko": ko, "b": b, "n": n_iznos, "pt": pt, "si": si})
                st.success("Faktura sačuvana!"); st.rerun()

# --- MODUL: KUPCI ---
elif meni == "👥 Kupci":
    st.title("👥 Kupci")
    with st.form("n_k"):
        c1, c2, c3 = st.columns(3)
        i, g, r = c1.text_input("Ime"), c2.text_input("Grad"), c3.number_input("Rabat %", 0.0)
        if st.form_submit_button("Dodaj Kupca"):
            izvrsi("INSERT INTO kupci (ime, grad, rabat) VALUES (:i, :g, :r)", {"i": i, "g": g, "r": r})
            st.rerun()
    st.dataframe(citaj("kupci"), use_container_width=True)
