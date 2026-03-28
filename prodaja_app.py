import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date, timedelta
import urllib.parse
import altair as alt

st.set_page_config(page_title="Poslovni Panel v8.1", layout="wide")

# --- KONEKCIJA ---
try:
    db_pass = st.secrets["DB_PASSWORD"]
    p_ref = st.secrets["PROJECT_REF"]
    app_pass = st.secrets["APP_LOGIN_SIFRA"]
    safe_pass = urllib.parse.quote_plus(db_pass)
    DB_URL = f"postgresql://postgres.{p_ref}:{safe_pass}@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    engine = create_engine(DB_URL, connect_args={"sslmode": "require"})
except Exception:
    st.error("Problem sa konekcijom!"); st.stop()

# --- GEOGRAFIJA ---
SRBIJA_MAPA = {
    "Južnobački": ["Novi Sad", "Bačka Palanka", "Bečej", "Temerin", "Vrbas", "Bački Petrovac", "Beočin", "Titel", "Žabalj", "Srbobran"],
    "Grad Beograd": ["Beograd", "Mladenovac", "Lazarevac", "Obrenovac", "Barajevo", "Grocka", "Sopot", "Surčin"],
    "Nišavski": ["Niš", "Aleksinac", "Svrljig", "Merošina", "Ražanj", "Doljevac", "Gadžin Han"],
    "Severnobački": ["Subotica", "Bačka Topola", "Mali Iđoš"],
    "Šumadijski": ["Kragujevac", "Aranđelovac", "Topola", "Rača", "Knić", "Batočina", "Lapovo"]
}
SVI_GRADOVI = sorted([g for lista in SRBIJA_MAPA.values() for g in lista])

# --- POMOĆNE FUNKCIJE ---
def izvrsi(upit, params=None):
    with engine.begin() as conn:
        conn.execute(text(upit), params or {})

def citaj(upit):
    try: return pd.read_sql(upit, engine)
    except: return pd.DataFrame()

# --- INICIJALIZACIJA BAZE ---
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

# --- LOGIN ---
if "auth" not in st.session_state: st.session_state["auth"] = False
if not st.session_state["auth"]:
    lozinka = st.text_input("Šifra:", type="password")
    if st.button("Ulaz"):
        if lozinka == app_pass: st.session_state["auth"] = True; st.rerun()
    st.stop()

meni = st.sidebar.radio("Meni:", ["📊 Pregled Faktura", "📝 Fakture (Unos)", "👥 Kupci & Analitika", "📦 Katalog Robe", "🚚 Brza Pošta"])

# ==========================================
# 🚚 BRZA POŠTA (VRAĆENO I SREĐENO)
# ==========================================
if meni == "🚚 Brza Pošta":
    st.title("🚚 Upravljanje Brzom Poštom")
    with st.form("n_s"):
        n_ime = st.text_input("Naziv nove kurirske službe")
        if st.form_submit_button("Dodaj službu"):
            izvrsi("INSERT INTO kuriri (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n_ime})
            st.rerun()
    
    df_s = citaj("SELECT * FROM kuriri")
    if not df_s.empty:
        sel = st.selectbox("Izaberi službu za promenu cene:", [f"{r['id']} | {r['naziv']}" for _, r in df_s.iterrows()])
        kid = int(sel.split(" | ")[0])
        
        with st.form("n_c"):
            v = st.number_input("Cena po paketu (RSD)", min_value=0.0)
            d = st.date_input("Važi od datuma", date.today())
            if st.form_submit_button("Sačuvaj novu cenu"):
                izvrsi("INSERT INTO kuriri_cene (kurir_id, cena, datum_od) VALUES (:id, :c, :d)", {"id": kid, "c": v, "d": d})
                st.success("Cena ažurirana!"); st.rerun()
        
        st.subheader("Istorija cena za odabranu službu")
        st.dataframe(citaj(f"SELECT cena, datum_od FROM kuriri_cene WHERE kurir_id={kid} ORDER BY datum_od DESC"), use_container_width=True)

# ==========================================
# 📝 FAKTURE (UNOS SA VIŠE STAVKI I KURIRIMA)
# ==========================================
elif meni == "📝 Fakture (Unos)":
    st.title("Nova Faktura")
    df_k = citaj("SELECT * FROM kupci")
    df_r = citaj("SELECT * FROM tipovi_robe")
    df_s = citaj("SELECT * FROM kuriri")
    
    if "nove_stavke" not in st.session_state: st.session_state.nove_stavke = []
    
    if not df_k.empty and not df_r.empty:
        c1, c2, c3 = st.columns(3)
        kupac_sel = c1.selectbox("Kupac:", [f"{r['id']} | {r['ime']} ({r['grad']})" for _, r in df_k.iterrows()])
        kid = int(kupac_sel.split(" | ")[0])
        def_rabat = df_k[df_k['id'] == kid]['rabat'].values[0]
        
        dat = c2.date_input("Datum", date.today())
        pt = c3.selectbox("Tip prevoza", ["Lično", "Kurir"])
        
        si = 0
        br_pak = ""
        if pt == "Kurir" and not df_s.empty:
            s_sel = c3.selectbox("Kurirska služba", [f"{r['id']} | {r['naziv']}" for _, r in df_s.iterrows()])
            si = int(s_sel.split(" | ")[0])
            br_pak = c3.text_input("Broj paketa / Tracking")

        st.divider()
        sa1, sa2, sa3, sa4, sa5 = st.columns([3, 1, 2, 1, 1])
        roba_sel = sa1.selectbox("Artikal", [f"{r['id']} | {r['naziv']}" for _, r in df_r.iterrows()])
        kom = sa2.number_input("Kom", 1, min_value=1)
        bruto = sa3.number_input("Bruto (RSD)", 0.0)
        rab = sa4.number_input("Rabat %", value=float(def_rabat))
        
        if sa5.button("➕"):
            rid = int(roba_sel.split(" | ")[0])
            r_ime = roba_sel.split(" | ")[1]
            st.session_state.nove_stavke.append({
                "roba_id": rid, "naziv": r_ime, "komada": kom, 
                "bruto": bruto, "rabat": rab, "neto": bruto * (1 - rab/100)
            })
            st.rerun()
            
        if st.session_state.nove_stavke:
            df_st = pd.DataFrame(st.session_state.nove_stavke)
            st.table(df_st[['naziv', 'komada', 'bruto', 'rabat', 'neto']])
            if st.button("💾 PROKNJIŽI FAKTURU"):
                izvrsi("INSERT INTO fakture_glavno (datum, kupac_id, prevoz_tip, kurir_id, broj_paketa) VALUES (:d,:k,:p,:si,:bp)",
                       {"d": dat, "k": kid, "p": pt, "si": si, "bp": br_pak})
                fid = citaj("SELECT MAX(id) as last_id FROM fakture_glavno")['last_id'][0]
                for s in st.session_state.nove_stavke:
                    izvrsi("INSERT INTO fakture_stavke (faktura_id, roba_id, komada, rabat, neto) VALUES (:f,:r,:k,:rab,:n)",
                           {"f": int(fid), "r": int(s['roba_id']), "k": int(s['komada']), "rab": float(s['rabat']), "n": float(s['neto'])})
                st.session_state.nove_stavke = []
                st.success("Uspešno sačuvano!"); st.rerun()

# ==========================================
# 📊 PREGLED FAKTURA (PAGINACIJA)
# ==========================================
elif meni == "📊 Pregled Faktura":
    st.title("Arhiva Faktura")
    c1, c2, c3 = st.columns(3)
    s_ime = c1.text_input("Pretraži kupca:")
    d_od = c2.date_input("Od", date(2025, 1, 1))
    d_do = c3.date_input("Do", date.today())

    query = f"""
        SELECT f.id, f.datum, k.ime as kupac, f.prevoz_tip, f.broj_paketa, 
               SUM(s.neto) as total_neto, 
               (SELECT cena FROM kuriri_cene WHERE kurir_id = f.kurir_id AND datum_od <= f.datum ORDER BY datum_od DESC LIMIT 1) as trosak_poste
        FROM fakture_glavno f
        JOIN kupci k ON f.kupac_id = k.id
        LEFT JOIN fakture_stavke s ON f.id = s.faktura_id
        WHERE f.datum BETWEEN '{d_od}' AND '{d_do}'
        {f"AND k.ime ILIKE '%%{s_ime}%%'" if s_ime else ""}
        GROUP BY f.id, f.datum, k.ime, f.prevoz_tip, f.broj_paketa, f.kurir_id
        ORDER BY f.id DESC
    """
    df = citaj(query)
    if not df.empty:
        df['trosak_poste'] = df['trosak_poste'].fillna(0)
        per_page = 15
        page = st.number_input("Strana", 1, max_value=(len(df)//per_page)+1, step=1) - 1
        st.dataframe(df.iloc[page*per_page : (page+1)*per_page], use_container_width=True)
