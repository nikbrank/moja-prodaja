import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
import urllib.parse

# --- 1. PODEŠAVANJE ---
st.set_page_config(page_title="Poslovni Panel v7.5", layout="wide")

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

# --- 3. GEOGRAFIJA (VRAĆENO) ---
SRBIJA_MAPA = {
    "Južnobački": ["Novi Sad", "Bačka Palanka", "Bečej", "Temerin", "Vrbas", "Bački Petrovac", "Beočin", "Titel", "Žabalj", "Srbobran"],
    "Grad Beograd": ["Beograd", "Mladenovac", "Lazarevac", "Obrenovac", "Barajevo", "Grocka", "Sopot", "Surčin"],
    "Nišavski": ["Niš", "Aleksinac", "Svrljig", "Merošina", "Ražanj", "Doljevac", "Gadžin Han"],
    "Severnobački": ["Subotica", "Bačka Topola", "Mali Iđoš"],
    "Šumadijski": ["Kragujevac", "Aranđelovac", "Topola", "Rača", "Knić", "Batočina", "Lapovo"]
}
SVI_GRADOVI = sorted([g for lista in SRBIJA_MAPA.values() for g in lista])

# --- 4. POMOĆNE FUNKCIJE ---
def izvrsi(upit, params=None):
    with engine.begin() as conn:
        conn.execute(text(upit), params or {})

def citaj(tabela, order_by="id ASC"):
    try:
        return pd.read_sql(f"SELECT * FROM {tabela} ORDER BY {order_by}", engine)
    except:
        return pd.DataFrame()

# --- 5. BAZA (SREĐIVANJE TIPOVA) ---
def inicijalizacija():
    izvrsi("CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri_cene (id SERIAL PRIMARY KEY, kurir_id INTEGER, cena REAL, datum_od DATE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL)")
    izvrsi("CREATE TABLE IF NOT EXISTS prodaja (id SERIAL PRIMARY KEY, datum DATE)")

    kolone = [
        ("kupac_id", "INTEGER"), ("roba_id", "INTEGER"), ("komada", "INTEGER"),
        ("bruto", "REAL"), ("neto", "REAL"), ("prevoz_tip", "TEXT"), ("kurir_id", "INTEGER")
    ]
    for col, tip in kolone:
        try:
            izvrsi(f"ALTER TABLE prodaja ADD COLUMN {col} {tip}")
        except: pass
    
    try:
        izvrsi("ALTER TABLE prodaja ALTER COLUMN datum TYPE DATE USING datum::DATE")
    except: pass

inicijalizacija()

# --- 6. DIJALOZI ZA IZMENU ---
@st.dialog("Izmeni Artikal")
def izmeni_robu_dialog(row):
    novo = st.text_input("Novi naziv", value=row['naziv'])
    if st.button("Sačuvaj"):
        izvrsi("UPDATE tipovi_robe SET naziv=:n WHERE id=:id", {"n": novo, "id": row['id']})
        st.rerun()

@st.dialog("Izmeni Kupca")
def izmeni_kupca_dialog(row):
    n_ime = st.text_input("Ime", value=row['ime'])
    n_grad = st.selectbox("Grad", SVI_GRADOVI, index=SVI_GRADOVI.index(row['grad']) if row['grad'] in SVI_GRADOVI else 0)
    n_rabat = st.number_input("Rabat %", value=float(row['rabat']))
    if st.button("Ažuriraj"):
        n_okr = next((o for o, gr in SRBIJA_MAPA.items() if n_grad in gr), "Ostalo")
        izvrsi("UPDATE kupci SET ime=:i, grad=:g, okrug=:o, rabat=:r WHERE id=:id", 
               {"i": n_ime, "g": n_grad, "o": n_okr, "r": n_rabat, "id": row['id']})
        st.rerun()

# --- 7. LOGIN ---
if "auth" not in st.session_state: st.session_state["auth"] = False
if not st.session_state["auth"]:
    lozinka = st.text_input("Lozinka:", type="password")
    if st.button("Ulaz"):
        if lozinka == app_pass: st.session_state["auth"] = True; st.rerun()
    st.stop()

# --- 8. NAVIGACIJA ---
meni = st.sidebar.radio("Meni:", ["Pregled", "📝 Nova Faktura", "👥 Kupci", "📦 Katalog Robe", "🚚 Brza Pošta"])

# --- MODUL: PREGLED ---
if meni == "Pregled":
    st.title("Pregled")
    query = """
        SELECT p.id, p.datum, k.ime as kupac, k.okrug, r.naziv as artikal, p.komada, p.neto, p.prevoz_tip, s.naziv as kurir,
        (SELECT cena FROM kuriri_cene WHERE kurir_id = p.kurir_id AND datum_od <= p.datum::DATE ORDER BY datum_od DESC LIMIT 1) as cena_kurira
        FROM prodaja p
        LEFT JOIN kupci k ON p.kupac_id = k.id
        LEFT JOIN tipovi_robe r ON p.roba_id = r.id
        LEFT JOIN kuriri s ON p.kurir_id = s.id
        ORDER BY p.id DESC
    """
    df_p = pd.read_sql(query, engine)
    
    if not df_p.empty:
        df_p['cena_kurira'] = df_p['cena_kurira'].fillna(0)
        df_p['zarada_sa_postom'] = df_p['neto'] - df_p['cena_kurira']
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Neto Prodaja", f"{df_p['neto'].sum():,.2f}")
        c2.metric("Zarada (Neto - Kurir)", f"{df_p['zarada_sa_postom'].sum():,.2f}")
        c3.metric("Ukupno Dostava", f"{df_p['cena_kurira'].sum():,.2f}")
        
        st.dataframe(df_p, use_container_width=True)
    else: st.info("Prazno.")

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
                izvrsi("INSERT INTO prodaja (datum, kupac_id, roba_id, komada, bruto, neto, prevoz_tip, kurir_id) VALUES (:d,:ki,:ri,:ko,:b,:n,:pt,:si)",
                       {"d": d, "ki": kid, "ri": rid, "ko": ko, "b": b, "n": b*(1-rabat/100), "pt": pt, "si": si})
                st.success("Sačuvano!"); st.rerun()

# --- MODUL: KUPCI (VRAĆENA MAPA I OKRUZI) ---
elif meni == "👥 Kupci":
    st.title("👥 Kupci")
    with st.form("nk"):
        c1, c2, c3 = st.columns(3)
        i = c1.text_input("Ime firme / Kupca")
        g = c2.selectbox("Grad", SVI_GRADOVI)
        r = c3.number_input("Rabat %", 0.0)
        if st.form_submit_button("Dodaj"):
            okr = next((o for o, gr in SRBIJA_MAPA.items() if g in gr), "Ostalo")
            izvrsi("INSERT INTO kupci (ime, grad, okrug, rabat) VALUES (:i, :g, :o, :r)", {"i": i, "g": g, "o": okr, "r": r})
            st.rerun()
    
    df_k = citaj("kupci")
    for _, r in df_k.iterrows():
        c1, c2, c3 = st.columns([1, 4, 1])
        c1.write(f"ID: {r['id']}")
        c2.write(f"**{r['ime']}** | {r['grad']} ({r['okrug']}) | Rabat: {r['rabat']}%")
        if c3.button("✏️", key=f"ek_{r['id']}"): izmeni_kupca_dialog(r)
        st.divider()

# --- MODUL: KATALOG ---
elif meni == "📦 Katalog Robe":
    st.title("📦 Katalog")
    with st.form("nr"):
        n = st.text_input("Naziv artikla")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n})
            st.rerun()
    df_t = citaj("tipovi_robe")
    for _, r in df_t.iterrows():
        c1, c2, c3 = st.columns([1, 4, 1])
        c1.write(f"ID: {r['id']}")
        c2.write(f"**{r['naziv']}**")
        if c3.button("✏️", key=f"er_{r['id']}"): izmeni_robu_dialog(r)
        st.divider()

# --- MODUL: BRZA POŠTA ---
elif meni == "🚚 Brza Pošta":
    st.title("🚚 Brza Pošta")
    with st.form("ns"):
        n = st.text_input("Naziv službe")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO kuriri (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n})
            st.rerun()
    
    df_s = citaj("kuriri")
    if not df_s.empty:
        izb = st.selectbox("Služba:", [f"{r['id']} | {r['naziv']}" for _, r in df_s.iterrows()])
        kid = int(izb.split(" | ")[0])
        with st.form("nc"):
            cena = st.number_input("Nova cena", min_value=0.0)
            dat = st.date_input("Važi od", date.today())
            if st.form_submit_button("Sačuvaj cenu"):
                izvrsi("INSERT INTO kuriri_cene (kurir_id, cena, datum_od) VALUES (:id, :c, :d)", {"id": kid, "c": cena, "d": dat})
                st.rerun()
        st.write("Istorija cena:")
        st.dataframe(pd.read_sql(f"SELECT cena, datum_od FROM kuriri_cene WHERE kurir_id={kid} ORDER BY datum_od DESC", engine))
