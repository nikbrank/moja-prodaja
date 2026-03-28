import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
import urllib.parse

# --- 1. PODEŠAVANJE ---
st.set_page_config(page_title="Poslovni Panel v7.1", layout="wide")

# --- 2. KONEKCIJA ---
try:
    db_pass = st.secrets["DB_PASSWORD"]
    p_ref = st.secrets["PROJECT_REF"]
    app_pass = st.secrets["APP_LOGIN_SIFRA"]
    safe_pass = urllib.parse.quote_plus(db_pass)
    DB_URL = f"postgresql://postgres.{p_ref}:{safe_pass}@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    engine = create_engine(DB_URL, connect_args={"sslmode": "require"})
except Exception:
    st.error("Greška sa bazom!"); st.stop()

# --- 3. POMOĆNE FUNKCIJE ---
def izvrsi(upit, params=None):
    with engine.begin() as conn:
        conn.execute(text(upit), params or {})

def citaj(tabela, order_by="id ASC"):
    try:
        return pd.read_sql(f"SELECT * FROM {tabela} ORDER BY {order_by}", engine)
    except:
        return pd.DataFrame()

# --- 4. ROBUSNA INICIJALIZACIJA (REŠAVA ERROR 83) ---
def setup_baze():
    # Kreiramo osnovne tabele
    izvrsi("CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri_cene (id SERIAL PRIMARY KEY, kurir_id INTEGER, cena REAL, datum_od DATE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL)")
    
    # Glavna tabela - ako puca, dodajemo kolone koje fale
    izvrsi("""CREATE TABLE IF NOT EXISTS prodaja (
        id SERIAL PRIMARY KEY, datum DATE, kupac_id INTEGER, roba_id INTEGER, 
        komada INTEGER, bruto REAL, neto REAL, prevoz_tip TEXT, kurir_id INTEGER
    )""")
    
    # Provera da li prodaja ima stare kolone (za svaki slučaj)
    try:
        izvrsi("ALTER TABLE prodaja ADD COLUMN IF NOT EXISTS kupac_id INTEGER")
        izvrsi("ALTER TABLE prodaja ADD COLUMN IF NOT EXISTS roba_id INTEGER")
        izvrsi("ALTER TABLE prodaja ADD COLUMN IF NOT EXISTS kurir_id INTEGER")
    except: pass

setup_baze()

# --- 5. DIJALOZI ZA IZMENU (PRATE ID) ---
@st.dialog("Izmeni Artikal")
def izmeni_robu_dialog(row):
    novo = st.text_input("Novi naziv", value=row['naziv'])
    if st.button("Sačuvaj"):
        izvrsi("UPDATE tipovi_robe SET naziv=:n WHERE id=:id", {"n": novo, "id": row['id']})
        st.rerun()

@st.dialog("Izmeni Kurira")
def izmeni_kurira_dialog(row):
    novo = st.text_input("Novi naziv", value=row['naziv'])
    if st.button("Sačuvaj"):
        izvrsi("UPDATE kuriri SET naziv=:n WHERE id=:id", {"n": novo, "id": row['id']})
        st.rerun()

# --- 6. LOGIN ---
if "auth" not in st.session_state: st.session_state["auth"] = False
if not st.session_state["auth"]:
    loz = st.text_input("Šifra:", type="password")
    if st.button("Ulaz"):
        if loz == app_pass: st.session_state["auth"] = True; st.rerun()
    st.stop()

# --- 7. NAVIGACIJA ---
meni = st.sidebar.radio("Meni:", ["Pregled", "📝 Nova Faktura", "👥 Kupci", "📦 Katalog Robe", "🚚 Brza Pošta"])

# --- MODUL: PREGLED ---
if meni == "Pregled":
    st.title("Pregled")
    # SQL koji sigurno radi - koristi LEFT JOIN preko ID-eva
    query = """
        SELECT p.id, p.datum, k.ime as kupac, r.naziv as artikal, p.komada, p.neto, p.prevoz_tip, s.naziv as kurir,
        (SELECT cena FROM kuriri_cene WHERE kurir_id = p.kurir_id AND datum_od <= p.datum ORDER BY datum_od DESC LIMIT 1) as cena_dostave
        FROM prodaja p
        LEFT JOIN kupci k ON p.kupac_id = k.id
        LEFT JOIN tipovi_robe r ON p.roba_id = r.id
        LEFT JOIN kuriri s ON p.kurir_id = s.id
        ORDER BY p.id DESC
    """
    try:
        df_p = pd.read_sql(query, engine)
        if not df_p.empty:
            df_p['cena_dostave'] = df_p['cena_dostave'].fillna(0)
            df_p['zarada_sa_postom'] = df_p['neto'] - df_p['cena_dostave']
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Neto (Bez pošte)", f"{df_p['neto'].sum():,.2f}")
            c2.metric("Zarada (Sa poštom)", f"{df_p['zarada_sa_postom'].sum():,.2f}")
            c3.metric("Trošak kurira", f"{df_p['cena_dostave'].sum():,.2f}")
            
            st.dataframe(df_p, use_container_width=True)
        else: st.info("Nema podataka.")
    except Exception as e:
        st.error(f"Greška u prikazu: {e}")

# --- MODUL: BRZA POŠTA (Istorija) ---
elif meni == "🚚 Brza Pošta":
    st.title("Brza Pošta i Istorija")
    with st.form("nk"):
        ime = st.text_input("Nova služba")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO kuriri (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": ime})
            st.rerun()
    
    df_s = citaj("kuriri")
    if not df_s.empty:
        izbor = st.selectbox("Služba (ID | Naziv):", [f"{r['id']} | {r['naziv']}" for _, r in df_s.iterrows()])
        kid = int(izbor.split(" | ")[0])
        
        with st.form("nc"):
            c1, c2 = st.columns(2)
            c_val = c1.number_input("Cena", min_value=0.0)
            c_dat = c2.date_input("Od datuma", date.today())
            if st.form_submit_button("Sačuvaj cenu"):
                izvrsi("INSERT INTO kuriri_cene (kurir_id, cena, datum_od) VALUES (:id, :c, :d)", {"id": kid, "c": c_val, "d": c_dat})
                st.success("Sačuvano!"); st.rerun()
        
        st.write("Istorija cena:")
        st.dataframe(pd.read_sql(f"SELECT cena, datum_od FROM kuriri_cene WHERE kurir_id={kid} ORDER BY datum_od DESC", engine))
        if st.button("Izmeni naziv službe"): izmeni_kurira_dialog(df_s[df_s['id'] == kid].iloc[0])

# --- MODUL: KATALOG ---
elif meni == "📦 Katalog Robe":
    st.title("Katalog Robe")
    with st.form("nr"):
        n = st.text_input("Artikal")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n})
            st.rerun()
    
    df_t = citaj("tipovi_robe")
    for _, r in df_t.iterrows():
        col1, col2, col3 = st.columns([1, 4, 1])
        col1.write(f"ID: {r['id']}")
        col2.write(f"**{r['naziv']}**")
        if col3.button("✏️", key=f"e_{r['id']}"): izmeni_robu_dialog(r)
        st.divider()

# --- MODUL: NOVA FAKTURA ---
elif meni == "📝 Nova Faktura":
    st.title("Nova Faktura")
    df_k, df_t, df_s = citaj("kupci"), citaj("tipovi_robe"), citaj("kuriri")
    if not df_k.empty and not df_t.empty:
        with st.form("f"):
            c1, c2 = st.columns(2)
            d = c1.date_input("Datum", date.today())
            k_s = c1.selectbox("Kupac", [f"{r['id']} | {r['ime']}" for _, r in df_k.iterrows()])
            r_s = c2.selectbox("Roba", [f"{r['id']} | {r['naziv']}" for _, r in df_t.iterrows()])
            ko = c2.number_input("Kom", 1)
            b = c1.number_input("Bruto", 0.0)
            pt = c2.selectbox("Prevoz", ["Lično", "Kurir"])
            si = None
            if pt == "Kurir" and not df_s.empty:
                s_s = c2.selectbox("Služba", [f"{r['id']} | {r['naziv']}" for _, r in df_s.iterrows()])
                si = int(s_s.split(" | ")[0])
            
            if st.form_submit_button("Sačuvaj"):
                kid, rid = int(k_s.split(" | ")[0]), int(r_s.split(" | ")[0])
                rabat = df_k[df_k['id'] == kid]['rabat'].values[0]
                izvrsi("INSERT INTO prodaja (datum, kupac_id, roba_id, komada, bruto, neto, prevoz_tip, kurir_id) VALUES (:d,:ki,:ri,:ko,:b,:n,:pt,:si)",
                       {"d": d, "ki": kid, "ri": rid, "ko": ko, "b": b, "n": b*(1-rabat/100), "pt": pt, "si": si})
                st.rerun()

# --- MODUL: KUPCI ---
elif meni == "👥 Kupci":
    st.title("Kupci")
    df_k = citaj("kupci")
    for _, r in df_k.iterrows():
        st.write(f"ID: {r['id']} | **{r['ime']}** | Rabat: {r['rabat']}%")
