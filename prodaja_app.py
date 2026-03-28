import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
import urllib.parse

# --- 1. PODEŠAVANJE ---
st.set_page_config(page_title="Poslovni Panel v7.2", layout="wide")

# --- 2. KONEKCIJA ---
try:
    db_pass = st.secrets["DB_PASSWORD"]
    p_ref = st.secrets["PROJECT_REF"]
    app_pass = st.secrets["APP_LOGIN_SIFRA"]
    safe_pass = urllib.parse.quote_plus(db_pass)
    DB_URL = f"postgresql://postgres.{p_ref}:{safe_pass}@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    engine = create_engine(DB_URL, connect_args={"sslmode": "require"})
except Exception:
    st.error("Baza nije dostupna!"); st.stop()

# --- 3. POMOĆNE FUNKCIJE ---
def izvrsi(upit, params=None):
    with engine.begin() as conn:
        conn.execute(text(upit), params or {})

def citaj(tabela, order_by="id ASC"):
    try:
        return pd.read_sql(f"SELECT * FROM {tabela} ORDER BY {order_by}", engine)
    except:
        return pd.DataFrame()

# --- 4. POPRAVKA STRUKTURE (MIGRACIJA) ---
def sredi_bazu():
    # Osnovne tabele
    izvrsi("CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri_cene (id SERIAL PRIMARY KEY, kurir_id INTEGER, cena REAL, datum_od DATE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL)")
    
    # Glavna tabela prodaje
    izvrsi("""CREATE TABLE IF NOT EXISTS prodaja (
        id SERIAL PRIMARY KEY, datum DATE, kupac_id INTEGER, roba_id INTEGER, 
        komada INTEGER, bruto REAL, neto REAL, prevoz_tip TEXT, kurir_id INTEGER
    )""")

    # PROVERA KOLONA (Da izbegnemo UndefinedColumn error)
    with engine.connect() as conn:
        res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='prodaja'"))
        postojece = [r[0] for r in res]
        
        # Ako imamo staru kolonu 'prevoz' a nemamo 'prevoz_tip', preimenuj je ili dodaj
        if 'prevoz_tip' not in postojece:
            if 'prevoz' in postojece:
                izvrsi("ALTER TABLE prodaja RENAME COLUMN prevoz TO prevoz_tip")
            else:
                izvrsi("ALTER TABLE prodaja ADD COLUMN prevoz_tip TEXT")
        
        # Dodaj ostale koje fale za ID tracking
        if 'kupac_id' not in postojece: izvrsi("ALTER TABLE prodaja ADD COLUMN kupac_id INTEGER")
        if 'roba_id' not in postojece: izvrsi("ALTER TABLE prodaja ADD COLUMN roba_id INTEGER")
        if 'kurir_id' not in postojece: izvrsi("ALTER TABLE prodaja ADD COLUMN kurir_id INTEGER")

sredi_bazu()

# --- 5. DIJALOZI ZA IZMENE ---
@st.dialog("Izmeni Artikal")
def izmeni_robu_dialog(row):
    n = st.text_input("Novi naziv", value=row['naziv'])
    if st.button("Sačuvaj"):
        izvrsi("UPDATE tipovi_robe SET naziv=:n WHERE id=:id", {"n": n, "id": row['id']})
        st.rerun()

@st.dialog("Izmeni Kurira")
def izmeni_kurira_dialog(row):
    n = st.text_input("Novi naziv", value=row['naziv'])
    if st.button("Sačuvaj"):
        izvrsi("UPDATE kuriri SET naziv=:n WHERE id=:id", {"n": n, "id": row['id']})
        st.rerun()

# --- 6. LOGIN ---
if "auth" not in st.session_state: st.session_state["auth"] = False
if not st.session_state["auth"]:
    l = st.text_input("Lozinka:", type="password")
    if st.button("Ulaz"):
        if l == app_pass: st.session_state["auth"] = True; st.rerun()
    st.stop()

# --- 7. NAVIGACIJA ---
meni = st.sidebar.radio("Meni:", ["Pregled", "📝 Nova Faktura", "👥 Kupci", "📦 Katalog Robe", "🚚 Brza Pošta"])

# --- MODUL: PREGLED ---
if meni == "Pregled":
    st.title("Pregled")
    query = """
        SELECT p.id, p.datum, k.ime as kupac, r.naziv as artikal, p.komada, p.neto, p.prevoz_tip, s.naziv as kurir,
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
        c1.metric("Neto (Bez dostave)", f"{df_p['neto'].sum():,.2f}")
        c2.metric("Zarada (Neto - Kurir)", f"{df_p['zarada_sa_postom'].sum():,.2f}")
        c3.metric("Ukupno dostava", f"{df_p['cena_dostave'].sum():,.2f}")
        
        st.dataframe(df_p, use_container_width=True)
        if st.button("🗑️ Obriši selektovanu prodaju"):
             st.warning("Selektuj ID prodaje u dnu da bi obrisao (opciono).")
    else: st.info("Nema podataka.")

# --- MODUL: BRZA POŠTA (Istorija) ---
elif meni == "🚚 Brza Pošta":
    st.title("Brza Pošta & Istorija")
    with st.form("nk"):
        n_ime = st.text_input("Naziv nove službe")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO kuriri (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n_ime})
            st.rerun()
    
    df_s = citaj("kuriri")
    if not df_s.empty:
        izb = st.selectbox("Izaberi službu (ID | Naziv):", [f"{r['id']} | {r['naziv']}" for _, r in df_s.iterrows()])
        kid = int(izb.split(" | ")[0])
        
        with st.form("nc"):
            c1, c2 = st.columns(2)
            val = c1.number_input("Cena (RSD)", min_value=0.0)
            dat = c2.date_input("Važi od datuma", date.today())
            if st.form_submit_button("Sačuvaj cenu"):
                izvrsi("INSERT INTO kuriri_cene (kurir_id, cena, datum_od) VALUES (:id, :c, :d)", {"id": kid, "c": val, "d": dat})
                st.success("Sačuvano!"); st.rerun()
        
        st.write("Istorija cena:")
        st.dataframe(pd.read_sql(f"SELECT id, cena, datum_od FROM kuriri_cene WHERE kurir_id={kid} ORDER BY datum_od DESC", engine), use_container_width=True)
        if st.button("✏️ Izmeni naziv službe"): izmeni_kurira_dialog(df_s[df_s['id'] == kid].iloc[0])

# --- MODUL: KATALOG ---
elif meni == "📦 Katalog Robe":
    st.title("Katalog Robe")
    with st.form("nr"):
        n_art = st.text_input("Artikal")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n_art})
            st.rerun()
    
    df_t = citaj("tipovi_robe")
    for _, r in df_t.iterrows():
        col1, col2, col3 = st.columns([1, 4, 1])
        col1.write(f"ID: {r['id']}")
        col2.write(f"**{r['naziv']}**")
        if col3.button("✏️", key=f"er_{r['id']}"): izmeni_robu_dialog(r)
        st.divider()

# --- MODUL: NOVA FAKTURA ---
elif meni == "📝 Nova Faktura":
    st.title("Nova Faktura")
    df_k, df_t, df_s = citaj("kupci"), citaj("tipovi_robe"), citaj("kuriri")
    if not df_k.empty and not df_t.empty:
        with st.form("f"):
            c1, c2 = st.columns(2)
            d = c1.date_input("Datum", date.today())
            k_s = c1.selectbox("Kupac (ID | Ime)", [f"{r['id']} | {r['ime']}" for _, r in df_k.iterrows()])
            r_s = c2.selectbox("Roba (ID | Naziv)", [f"{r['id']} | {r['naziv']}" for _, r in df_t.iterrows()])
            ko = c2.number_input("Kom", 1)
            b = c1.number_input("Bruto", 0.0)
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
                       {"d": d, "ki": kid, "ri": rid, "ko": ko, "b": b, "n": n_iznos, "pt": pt, "si": si})
                st.success("Uspeh!"); st.rerun()

# --- MODUL: KUPCI ---
elif meni == "👥 Kupci":
    st.title("Kupci")
    df_k = citaj("kupci")
    for _, r in df_k.iterrows():
        c1, c2, c3 = st.columns([1, 4, 1])
        c1.write(f"ID: {r['id']}")
        c2.write(f"**{r['ime']}** | {r['grad']} | Rabat: {r['rabat']}%")
        st.divider()
