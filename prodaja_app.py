import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
import urllib.parse

# --- 1. PODEŠAVANJE ---
st.set_page_config(page_title="Poslovni Panel v6.7", layout="wide")

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
        df = pd.read_sql(upit, engine)
        return df
    except:
        return pd.DataFrame()

# --- 4. FORCE REPAIR (Popravlja strukturu ako puca) ---
def popravi_tabele():
    # Ako tabela 'kuriri' postoji ali nema kolonu 'naziv', obriši je i napravi ponovo
    df_provera = citaj("kuriri")
    if not df_provera.empty and 'naziv' not in df_provera.columns:
        izvrsi("DROP TABLE kuriri")
    
    # Standardno kreiranje
    izvrsi("CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE, cena REAL)")
    izvrsi("CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL)")
    izvrsi("""CREATE TABLE IF NOT EXISTS prodaja (
        id SERIAL PRIMARY KEY, datum TEXT, kupac_info TEXT, roba TEXT, 
        komada INTEGER, bruto REAL, neto REAL, okrug TEXT, prevoz TEXT, kurir TEXT
    )""")

popravi_tabele()

# --- 5. GEOGRAFIJA (Skraćeno radi preglednosti) ---
SRBIJA_MAPA = {
    "Južnobački": ["Novi Sad", "Bačka Palanka", "Bečej", "Temerin", "Vrbas", "Bački Petrovac", "Beočin", "Titel", "Žabalj", "Srbobran"],
    "Grad Beograd": ["Beograd", "Mladenovac", "Lazarevac", "Obrenovac", "Barajevo", "Grocka", "Sopot", "Surčin"],
    "Nišavski": ["Niš", "Aleksinac", "Svrljig", "Merošina", "Ražanj", "Doljevac", "Gadžin Han"],
    "Severnobački": ["Subotica", "Bačka Topola", "Mali Iđoš"]
}
SVI_GRADOVI = sorted([g for lista in SRBIJA_MAPA.values() for g in lista])

# --- 6. LOGIN ---
if "auth" not in st.session_state: st.session_state["auth"] = False
if not st.session_state["auth"]:
    st.title("🔐 Ulaz")
    lozinka = st.text_input("Lozinka:", type="password")
    if st.button("Prijavi se"):
        if lozinka == app_pass: st.session_state["auth"] = True; st.rerun()
        else: st.error("Pogrešna lozinka!")
    st.stop()

# --- 7. NAVIGACIJA ---
meni = st.sidebar.radio("Meni:", ["📊 Pregled", "📝 Nova Faktura", "👥 Kupci", "📦 Katalog Robe", "🚚 Brza Pošta"])

# --- MODUL: BRZA POŠTA ---
if meni == "🚚 Brza Pošta":
    st.title("🚚 Kurirske Službe")
    with st.form("n_kurir"):
        c_n = st.text_input("Naziv službe")
        c_c = st.number_input("Cena (RSD)", min_value=0.0)
        if st.form_submit_button("Sačuvaj"):
            if c_n:
                df_s = citaj("kuriri")
                # Provera postojanja bezbedno
                if not df_s.empty and 'naziv' in df_s.columns and c_n.strip() in df_s['naziv'].values:
                    st.warning("Već postoji!")
                else:
                    izvrsi("INSERT INTO kuriri (naziv, cena) VALUES (:n, :c) ON CONFLICT (naziv) DO NOTHING", 
                           {"n": c_n.strip(), "c": c_c})
                    st.rerun()

    df_s = citaj("kuriri", "naziv ASC")
    if not df_s.empty and 'naziv' in df_s.columns:
        for _, row in df_s.iterrows():
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(row['naziv'])
            c2.write(f"{row['cena']} RSD")
            if c3.button("🗑️", key=f"ds_{row['id']}"):
                izvrsi("DELETE FROM kuriri WHERE id=:id", {"id": row['id']})
                st.rerun()

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
            if prevoz == "Kurir" and not df_s.empty and 'naziv' in df_s.columns:
                kurir_ime = c2.selectbox("Služba:", df_s['naziv'])

            if st.form_submit_button("Sačuvaj"):
                f_ime, f_grad = k_izbor.split(" | ")
                k_data = df_k[(df_k['ime'] == f_ime) & (df_k['grad'] == f_grad)].iloc[0]
                neto = iznos * (1 - k_data['rabat']/100)
                izvrsi("INSERT INTO prodaja (datum, kupac_info, roba, komada, bruto, neto, okrug, prevoz, kurir) VALUES (:d, :k, :r, :ko, :b, :n, :o, :p, :ku)",
                       {"d": str(dat), "k": k_izbor, "r": artikal, "ko": kol, "b": iznos, "n": neto, "o": k_data['okrug'], "p": prevoz, "ku": kurir_ime})
                st.success("Faktura proknjižena!"); st.rerun()

# --- OSTALI MODULI (Pregled, Kupci, Katalog) ---
elif meni == "📊 Pregled":
    st.title("📊 Dashboard")
    df_p = citaj("prodaja", "id DESC")
    if not df_p.empty:
        st.dataframe(df_p, width='stretch')
    else: st.info("Prazno.")

elif meni == "👥 Kupci":
    st.title("👥 Kupci")
    with st.form("nk"):
        c1, c2, c3 = st.columns(3)
        i, g = c1.text_input("Firma"), c2.selectbox("Grad", SVI_GRADOVI)
        r = c3.number_input("Rabat %", 0.0)
        if st.form_submit_button("Dodaj"):
            okr = next((o for o, gr in SRBIJA_MAPA.items() if g in gr), "Ostalo")
            izvrsi("INSERT INTO kupci (ime, grad, okrug, rabat) VALUES (:i, :g, :o, :r)", {"i": i, "g": g, "o": okr, "r": r})
            st.rerun()
    st.dataframe(citaj("kupci", "ime ASC"), width='stretch')

elif meni == "📦 Katalog Robe":
    st.title("📦 Katalog")
    with st.form("nr"):
        n = st.text_input("Artikal")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT (naziv) DO NOTHING", {"n": n.strip()})
            st.rerun()
    df_t = citaj("tipovi_robe", "naziv ASC")
    if not df_t.empty:
        for _, row in df_t.iterrows():
            c1, c2 = st.columns([5, 1])
            c1.write(row['naziv'])
            if c2.button("🗑️", key=f"dr_{row['id']}"):
                izvrsi("DELETE FROM tipovi_robe WHERE id=:id", {"id": row['id']})
                st.rerun()
