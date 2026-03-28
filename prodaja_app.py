import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date, timedelta
import urllib.parse
import altair as alt

# --- 1. PODEŠAVANJE ---
st.set_page_config(page_title="Poslovni Panel v8.2", layout="wide")

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

# --- 3. GEOGRAFIJA ---
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

def citaj(upit):
    try: return pd.read_sql(upit, engine)
    except: return pd.DataFrame()

# --- 5. INICIJALIZACIJA (Mora biti precizna) ---
def init_db():
    izvrsi("CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri_cene (id SERIAL PRIMARY KEY, kurir_id INTEGER, cena REAL, datum_od DATE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL)")
    izvrsi("""CREATE TABLE IF NOT EXISTS fakture_glavno (
        id SERIAL PRIMARY KEY, datum DATE, kupac_id INTEGER, prevoz_tip TEXT, kurir_id INTEGER, broj_paketa TEXT
    )""")
    izvrsi("""CREATE TABLE IF NOT EXISTS fakture_stavke (
        id SERIAL PRIMARY KEY, faktura_id INTEGER, roba_id INTEGER, komada INTEGER, rabat REAL, neto REAL
    )""")
init_db()

# --- 6. DIJALOZI ZA IZMENU ---
@st.dialog("Izmeni Kupca")
def izmeni_kupca_dialog(row):
    i = st.text_input("Ime firme", value=row['ime'])
    g = st.selectbox("Grad", SVI_GRADOVI, index=SVI_GRADOVI.index(row['grad']) if row['grad'] in SVI_GRADOVI else 0)
    r = st.number_input("Podrazumevani Rabat %", value=float(row['rabat']))
    if st.button("Sačuvaj izmene"):
        o = next((okr for okr, gr in SRBIJA_MAPA.items() if g in gr), "Ostalo")
        izvrsi("UPDATE kupci SET ime=:i, grad=:g, okrug=:o, rabat=:r WHERE id=:id", 
               {"i": i, "g": g, "o": o, "r": r, "id": int(row['id'])})
        st.rerun()

# --- 7. NAVIGACIJA ---
if "auth" not in st.session_state: st.session_state["auth"] = False
if not st.session_state["auth"]:
    lozinka = st.text_input("Lozinka:", type="password")
    if st.button("Ulaz"):
        if lozinka == app_pass: st.session_state["auth"] = True; st.rerun()
    st.stop()

meni = st.sidebar.radio("Meni:", ["📊 Pregled Faktura", "📝 Fakture (Unos)", "👥 Kupci & Analitika", "📦 Katalog Robe", "🚚 Brza Pošta"])

# ==========================================
# 📝 FAKTURE (UNOS) - POPRAVLJEN TYPEERROR
# ==========================================
if meni == "📝 Fakture (Unos)":
    st.title("Nova Faktura (Više stavki)")
    df_k = citaj("SELECT * FROM kupci ORDER BY ime")
    df_r = citaj("SELECT * FROM tipovi_robe ORDER BY naziv")
    df_s = citaj("SELECT * FROM kuriri")
    
    if "stavke_f" not in st.session_state: st.session_state.stavke_f = []
    
    if not df_k.empty and not df_r.empty:
        c1, c2, c3 = st.columns(3)
        k_sel = c1.selectbox("Kupac:", [f"{r['id']} | {r['ime']} ({r['grad']})" for _, r in df_k.iterrows()])
        kid = int(k_sel.split(" | ")[0])
        def_rabat = float(df_k[df_k['id'] == kid]['rabat'].values[0])
        
        dat = c2.date_input("Datum", date.today())
        pt = c3.selectbox("Prevoz", ["Lično", "Kurir"])
        
        si = 0
        br_pak = ""
        if pt == "Kurir" and not df_s.empty:
            s_sel = c3.selectbox("Služba", [f"{r['id']} | {r['naziv']}" for _, r in df_s.iterrows()])
            si = int(s_sel.split(" | ")[0])
            br_pak = c3.text_input("Broj paketa")

        st.subheader("Dodaj stavku")
        sa1, sa2, sa3, sa4, sa5 = st.columns([3, 1, 2, 1, 1])
        r_sel = sa1.selectbox("Artikal", [f"{r['id']} | {r['naziv']}" for _, r in df_r.iterrows()])
        kom = sa2.number_input("Kom", value=1, min_value=1) # FIX: Eksplicitni int
        bruto = sa3.number_input("Bruto RSD", value=0.0, step=100.0)
        rab = sa4.number_input("Rabat %", value=def_rabat)
        
        if sa5.button("➕"):
            rid = int(r_sel.split(" | ")[0])
            r_naziv = r_sel.split(" | ")[1]
            st.session_state.stavke_f.append({
                "roba_id": rid, "naziv": r_naziv, "komada": int(kom), 
                "rabat": float(rab), "neto": float(bruto * (1 - rab/100))
            })
            st.rerun()
            
        if st.session_state.stavke_f:
            st.table(pd.DataFrame(st.session_state.stavke_f))
            if st.button("💾 SAČUVAJ FAKTURU"):
                izvrsi("INSERT INTO fakture_glavno (datum, kupac_id, prevoz_tip, kurir_id, broj_paketa) VALUES (:d,:k,:p,:si,:bp)",
                       {"d": dat, "k": kid, "p": pt, "si": si, "bp": br_pak})
                fid = int(citaj("SELECT MAX(id) as last_id FROM fakture_glavno")['last_id'][0])
                for s in st.session_state.stavke_f:
                    izvrsi("INSERT INTO fakture_stavke (faktura_id, roba_id, komada, rabat, neto) VALUES (:f,:r,:k,:rab,:n)",
                           {"f": fid, "r": s['roba_id'], "k": s['komada'], "rab": s['rabat'], "n": s['neto']})
                st.session_state.stavke_f = []
                st.success("Faktura ID #{} proknjižena!".format(fid))
                st.rerun()

# ==========================================
# 👥 KUPCI & ANALITIKA (KOMPLETAN MODUL)
# ==========================================
elif meni == "👥 Kupci & Analitika":
    t1, t2, t3 = st.tabs(["Unos/Izmena", "Mapa i Pokrivenost", "Analitika Kupca"])
    
    with t1:
        with st.form("n_k"):
            c1, c2, c3 = st.columns(3)
            i = c1.text_input("Ime firme")
            g_sel = c2.selectbox("Izaberi Grad", ["DODAJ NOVI"] + SVI_GRADOVI)
            g_man = c2.text_input("Ime grada (ako je NOVI)")
            o_man = c3.text_input("Okrug (ako je NOVI)")
            r = c3.number_input("Rabat %", 0.0)
            if st.form_submit_button("Dodaj"):
                grad = g_man if g_sel == "DODAJ NOVI" else g_sel
                okr = o_man if g_sel == "DODAJ NOVI" else next((o for o, gr in SRBIJA_MAPA.items() if grad in gr), "Ostalo")
                izvrsi("INSERT INTO kupci (ime, grad, okrug, rabat) VALUES (:i, :g, :o, :r)", {"i": i, "g": grad, "o": okr, "r": r})
                st.rerun()
        
        df_k = citaj("SELECT * FROM kupci ORDER BY ime")
        for _, r in df_k.iterrows():
            c1, c2 = st.columns([5, 1])
            c1.write(f"ID: {r['id']} | **{r['ime']}** - {r['grad']} ({r['okrug']})")
            if c2.button("✏️", key=f"edit_k_{r['id']}"): izmeni_kupca_dialog(r)
            st.divider()

    with t2:
        df_m = citaj("SELECT okrug, COUNT(id) as br FROM kupci GROUP BY okrug")
        st.bar_chart(df_m.set_index('okrug'))

# ==========================================
# 📦 KATALOG ROBE
# ==========================================
elif meni == "📦 Katalog Robe":
    st.title("📦 Katalog")
    with st.form("n_r"):
        n = st.text_input("Naziv nove robe")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n})
            st.rerun()
    
    df_t = citaj("SELECT * FROM tipovi_robe ORDER BY id")
    for _, r in df_t.iterrows():
        c1, c2, c3 = st.columns([1, 4, 1])
        c1.write(f"ID: {r['id']}")
        c2.write(f"**{r['naziv']}**")
        if c3.button("🗑️", key=f"del_r_{r['id']}"):
            izvrsi("DELETE FROM tipovi_robe WHERE id=:id", {"id": int(r['id'])})
            st.rerun()
        st.divider()

# ==========================================
# 📊 PREGLED FAKTURA (PAGINACIJA)
# ==========================================
elif meni == "📊 Pregled Faktura":
    st.title("Arhiva")
    df = citaj("""
        SELECT f.id, f.datum, k.ime as kupac, SUM(s.neto) as total 
        FROM fakture_glavno f 
        JOIN kupci k ON f.kupac_id = k.id 
        JOIN fakture_stavke s ON f.id = s.faktura_id 
        GROUP BY f.id, f.datum, k.ime ORDER BY f.id DESC
    """)
    if not df.empty:
        st.dataframe(df, use_container_width=True)

# ==========================================
# 🚚 BRZA POŠTA
# ==========================================
elif meni == "🚚 Brza Pošta":
    st.title("Službe")
    with st.form("n_s"):
        n = st.text_input("Kurirska služba")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO kuriri (naziv) VALUES (:n)", {"n": n})
            st.rerun()
