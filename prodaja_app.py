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
except Exception:
    st.error("Baza nije dostupna."); st.stop()

# --- 3. POMOĆNE FUNKCIJE ---
def izvrsi(upit, params=None):
    with engine.begin() as conn:
        conn.execute(text(upit), params or {})

def citaj(tabela, order_by="id ASC"):
    try:
        upit = f"SELECT * FROM {tabela} ORDER BY {order_by}"
        return pd.read_sql(upit, engine)
    except:
        return pd.DataFrame()

# --- 4. BAZA INICIJALIZACIJA (STRUKTURA) ---
izvrsi("CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
izvrsi("CREATE TABLE IF NOT EXISTS kuriri (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
izvrsi("CREATE TABLE IF NOT EXISTS kuriri_cene (id SERIAL PRIMARY KEY, kurir_id INTEGER, cena REAL, datum_od DATE)")
izvrsi("CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL)")
izvrsi("""CREATE TABLE IF NOT EXISTS prodaja (
    id SERIAL PRIMARY KEY, datum DATE, kupac_id INTEGER, roba_id INTEGER, 
    komada INTEGER, bruto REAL, neto REAL, prevoz_tip TEXT, kurir_id INTEGER
)""")

# --- 5. DIJALOZI ---
@st.dialog("Izmeni Artikal")
def izmeni_robu_dialog(row):
    novo_ime = st.text_input("Novi naziv", value=row['naziv'])
    if st.button("Sačuvaj izmenu"):
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
    # Kompleksan SQL koji vuče cenu kurira koja je važila na DAN prodaje
    query = """
        SELECT p.*, k.ime as kupac_ime, r.naziv as roba_ime, s.naziv as kurir_ime,
        (SELECT cena FROM kuriri_cene WHERE kurir_id = p.kurir_id AND datum_od <= p.datum ORDER BY datum_od DESC LIMIT 1) as cena_kurira
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
        c1.metric("Ukupno Neto (Bez pošte)", f"{df_p['neto'].sum():,.2f} RSD")
        c2.metric("Ukupna Zarada (Sa poštom)", f"{df_p['zarada_sa_postom'].sum():,.2f} RSD")
        c3.metric("Ukupan trošak dostave", f"{df_p['cena_kurira'].sum():,.2f} RSD")
        
        st.dataframe(df_p[['id', 'datum', 'kupac_ime', 'roba_ime', 'komada', 'neto', 'zarada_sa_postom', 'kurir_ime', 'cena_kurira']], use_container_width=True)
    else:
        st.info("Nema podataka o prodaji.")

# --- MODUL: BRZA POŠTA (Istorija cena) ---
elif meni == "🚚 Brza Pošta":
    st.title("Brza Pošta & Istorija Cena")
    
    tab1, tab2 = st.tabs(["Novi Kurir", "Ažuriranje & Istorija"])
    
    with tab1:
        with st.form("n_k"):
            n_ime = st.text_input("Naziv nove kurirske službe")
            if st.form_submit_button("Dodaj"):
                izvrsi("INSERT INTO kuriri (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n_ime})
                st.rerun()
    
    with tab2:
        df_s = citaj("kuriri")
        if not df_s.empty:
            sel_k = st.selectbox("Izaberi službu (ID | Naziv):", [f"{r['id']} | {r['naziv']}" for _, r in df_s.iterrows()])
            k_id = int(sel_k.split(" | ")[0])
            
            with st.form("nova_cena_forma"):
                c1, c2 = st.columns(2)
                nova_c = c1.number_input("Cena (RSD)", min_value=0.0)
                od_dat = c2.date_input("Važi od datuma", date.today())
                if st.form_submit_button("Sačuvaj cenu"):
                    izvrsi("INSERT INTO kuriri_cene (kurir_id, cena, datum_od) VALUES (:id, :c, :d)", 
                           {"id": k_id, "c": nova_c, "d": od_dat})
                    st.success("Cena uspešno proknjižena!")
            
            st.subheader(f"Istorija cena za {sel_k}")
            df_hist = pd.read_sql(f"SELECT id, cena, datum_od FROM kuriri_cene WHERE kurir_id = {k_id} ORDER BY datum_od DESC", engine)
            st.dataframe(df_hist, use_container_width=True)

# --- MODUL: NOVA FAKTURA ---
elif meni == "📝 Nova Faktura":
    st.title("Nova Faktura")
    df_k = citaj("kupci", "ime ASC")
    df_t = citaj("tipovi_robe", "naziv ASC")
    df_s = citaj("kuriri", "naziv ASC")
    
    if not df_k.empty and not df_t.empty:
        with st.form("f_forma"):
            c1, c2 = st.columns(2)
            dat = c1.date_input("Datum", date.today())
            k_izbor = c1.selectbox("Kupac (ID | Ime)", [f"{r['id']} | {r['ime']}" for _, r in df_k.iterrows()])
            art_izbor = c2.selectbox("Roba (ID | Naziv)", [f"{r['id']} | {r['naziv']}" for _, r in df_t.iterrows()])
            kol = c2.number_input("Količina", 1)
            bruto = c1.number_input("Bruto (RSD)", 0.0)
            p_tip = c2.selectbox("Prevoz", ["Lično", "Kurir"])
            
            s_id = None
            if p_tip == "Kurir" and not df_s.empty:
                s_izbor = c2.selectbox("Kurirska služba", [f"{r['id']} | {r['naziv']}" for _, r in df_s.iterrows()])
                s_id = int(s_izbor.split(" | ")[0])

            if st.form_submit_button("Proknjiži"):
                kid = int(k_izbor.split(" | ")[0])
                rid = int(art_izbor.split(" | ")[0])
                k_rabat = df_k[df_k['id'] == kid]['rabat'].values[0]
                neto = bruto * (1 - k_rabat/100)
                
                izvrsi("""INSERT INTO prodaja (datum, kupac_id, roba_id, komada, bruto, neto, prevoz_tip, kurir_id) 
                       VALUES (:d, :ki, :ri, :ko, :b, :n, :pt, :si)""",
                       {"d": dat, "ki": kid, "ri": rid, "ko": kol, "b": bruto, "n": neto, "pt": p_tip, "si": s_id})
                st.success("Faktura sačuvana!"); st.rerun()

# --- MODUL: KATALOG ROBE ---
elif meni == "📦 Katalog Robe":
    st.title("Katalog Robe")
    with st.form("n_r"):
        n_ime = st.text_input("Novi artikal")
        if st.form_submit_button("Dodaj u katalog"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n_ime.strip()})
            st.rerun()
    
    df_t = citaj("tipovi_robe")
    if not df_t.empty:
        for _, row in df_t.iterrows():
            c1, c2, c3, c4 = st.columns([1, 4, 1, 1])
            c1.write(f"ID: {row['id']}")
            c2.write(f"**{row['naziv']}**")
            if c3.button("✏️", key=f"e_{row['id']}"): izmeni_robu_dialog(row)
            if c4.button("🗑️", key=f"d_{row['id']}"):
                izvrsi("DELETE FROM tipovi_robe WHERE id=:id", {"id": row['id']})
                st.rerun()
            st.divider()

# --- MODUL: KUPCI ---
elif meni == "👥 Kupci":
    st.title("Baza Kupaca")
    df_k = citaj("kupci")
    if not df_k.empty:
        for _, row in df_k.iterrows():
            c1, c2, c3, c4 = st.columns([1, 3, 2, 1])
            c1.write(f"ID: {row['id']}")
            c2.write(f"**{row['ime']}** ({row['grad']})")
            c3.write(f"Rabat: {row['rabat']}%")
            if c4.button("✏️", key=f"ek_{row['id']}"): izmeni_kupca_dialog(row)
            st.divider()
