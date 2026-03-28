import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date, timedelta
import urllib.parse
import altair as alt

st.set_page_config(page_title="Poslovni Panel v8.0", layout="wide")

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

# --- INICIJALIZACIJA BAZE (NOVA STRUKTURA) ---
def init_db():
    izvrsi("CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kuriri_cene (id SERIAL PRIMARY KEY, kurir_id INTEGER, cena REAL, datum_od DATE)")
    izvrsi("CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL)")
    
    # NOVE TABELE ZA VIŠE STAVKI PO FAKTURI
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

meni = st.sidebar.radio("Meni:", ["📊 Pregled Faktura", "📝 Fakture (Unos)", "👥 Kupci & Analitika", "📦 Katalog Robe"])

# ==========================================
# 📊 PREGLED FAKTURA (PAGINACIJA & PRETRAGA)
# ==========================================
if meni == "📊 Pregled Faktura":
    st.title("Sve Fakture")
    
    col1, col2, col3 = st.columns(3)
    search_ime = col1.text_input("Pretraga po kupcu:")
    d_od = col2.date_input("Od datuma", date(2020, 1, 1))
    d_do = col3.date_input("Do datuma", date.today())
    
    # Glavni SQL za pregled faktura (Sumira stavke)
    upit = f"""
        SELECT f.id, f.datum, k.ime as kupac, f.prevoz_tip, f.broj_paketa, 
               SUM(s.komada) as ukupno_komada, SUM(s.neto) as ukupno_neto
        FROM fakture_glavno f
        JOIN kupci k ON f.kupac_id = k.id
        LEFT JOIN fakture_stavke s ON f.id = s.faktura_id
        WHERE f.datum >= '{d_od}' AND f.datum <= '{d_do}'
        {f"AND k.ime ILIKE '%%{search_ime}%%'" if search_ime else ""}
        GROUP BY f.id, f.datum, k.ime, f.prevoz_tip, f.broj_paketa
        ORDER BY f.id DESC
    """
    df_fakture = citaj(upit)
    
    if not df_fakture.empty:
        # Paginacija (15 po strani)
        per_page = 15
        if 'page' not in st.session_state: st.session_state.page = 0
        total_pages = len(df_fakture) // per_page + (1 if len(df_fakture) % per_page > 0 else 0)
        
        c1, c2, c3 = st.columns([1, 2, 1])
        if c1.button("⬅️ Prethodna") and st.session_state.page > 0:
            st.session_state.page -= 1; st.rerun()
        c2.write(f"Strana {st.session_state.page + 1} od {total_pages}")
        if c3.button("Sledeća ➡️") and st.session_state.page < total_pages - 1:
            st.session_state.page += 1; st.rerun()
            
        start_idx = st.session_state.page * per_page
        st.dataframe(df_fakture.iloc[start_idx : start_idx + per_page], use_container_width=True)
    else:
        st.info("Nema faktura za ovaj kriterijum.")

# ==========================================
# 📝 FAKTURE (VIŠE STAVKI)
# ==========================================
elif meni == "📝 Fakture (Unos)":
    st.title("Nova Faktura / Više Stavki")
    df_k = citaj("SELECT * FROM kupci")
    df_r = citaj("SELECT * FROM tipovi_robe")
    
    if "nove_stavke" not in st.session_state: st.session_state.nove_stavke = []
    
    if not df_k.empty and not df_r.empty:
        c1, c2, c3 = st.columns(3)
        kupac_sel = c1.selectbox("Kupac:", [f"{r['id']} | {r['ime']}" for _, r in df_k.iterrows()])
        kid = int(kupac_sel.split(" | ")[0])
        def_rabat = df_k[df_k['id'] == kid]['rabat'].values[0]
        
        dat = c2.date_input("Datum fakture", date.today())
        pt = c3.selectbox("Prevoz", ["Lično", "Kurir"])
        br_pak = c3.text_input("Broj paketa (Tracking)") if pt == "Kurir" else ""
        
        st.subheader("Dodaj robu na fakturu")
        sa1, sa2, sa3, sa4, sa5 = st.columns(5)
        roba_sel = sa1.selectbox("Artikal", [f"{r['id']} | {r['naziv']}" for _, r in df_r.iterrows()])
        kom = sa2.number_input("Komada", 1, min_value=1)
        bruto = sa3.number_input("Ukupno Bruto (za ovu stavku)", 0.0)
        rab = sa4.number_input("Rabat % (Custom)", value=float(def_rabat))
        
        if sa5.button("➕ Dodaj stavku"):
            rid = int(roba_sel.split(" | ")[0])
            r_ime = roba_sel.split(" | ")[1]
            st.session_state.nove_stavke.append({
                "roba_id": rid, "naziv": r_ime, "komada": kom, 
                "bruto": bruto, "rabat": rab, "neto": bruto * (1 - rab/100)
            })
            st.rerun()
            
        if st.session_state.nove_stavke:
            st.write("### Stavke na trenutnoj fakturi:")
            df_stavke = pd.DataFrame(st.session_state.nove_stavke)
            st.dataframe(df_stavke[['naziv', 'komada', 'bruto', 'rabat', 'neto']])
            
            if st.button("💾 SAČUVAJ FAKTURU"):
                # Prvo upiši zaglavlje
                izvrsi("INSERT INTO fakture_glavno (datum, kupac_id, prevoz_tip, kurir_id, broj_paketa) VALUES (:d, :k, :p, 0, :bp)",
                       {"d": dat, "k": kid, "p": pt, "bp": br_pak})
                # Uzmi ID te fakture
                fid = citaj("SELECT MAX(id) as last_id FROM fakture_glavno")['last_id'][0]
                # Upiši stavke
                for stv in st.session_state.nove_stavke:
                    izvrsi("INSERT INTO fakture_stavke (faktura_id, roba_id, komada, rabat, neto) VALUES (:f, :r, :k, :rab, :n)",
                           {"f": int(fid), "r": int(stv['roba_id']), "k": int(stv['komada']), "rab": float(stv['rabat']), "n": float(stv['neto'])})
                st.session_state.nove_stavke = []
                st.success("Faktura uspešno knjižena!")
                st.rerun()

# ==========================================
# 👥 KUPCI & ANALITIKA
# ==========================================
elif meni == "👥 Kupci & Analitika":
    tab1, tab2, tab3, tab4 = st.tabs(["📝 Unos i Izmena", "🗺️ Mapa i Pokrivenost", "📈 Detaljna Analitika", "📉 Trendovi (3 Meseca)"])
    
    with tab1:
        st.subheader("Unos i pregled kupaca")
        with st.form("nk"):
            c1, c2, c3 = st.columns(3)
            i = c1.text_input("Ime firme")
            g = c2.text_input("Grad (Ako nema na listi, upiši ovde)")
            g_sel = c2.selectbox("Ili izaberi Grad", [""] + SVI_GRADOVI)
            okr_man = c3.text_input("Okrug (Samo ako unosiš ručno grad)")
            r = c3.number_input("Rabat %", 0.0)
            
            if st.form_submit_button("Dodaj Kupca"):
                final_grad = g if g else g_sel
                final_okr = okr_man if okr_man else next((o for o, gradovi in SRBIJA_MAPA.items() if final_grad in gradovi), "Ostalo")
                izvrsi("INSERT INTO kupci (ime, grad, okrug, rabat) VALUES (:i, :g, :o, :r)", 
                       {"i": i, "g": final_grad, "o": final_okr, "r": r})
                st.rerun()
                
        st.dataframe(citaj("SELECT * FROM kupci ORDER BY ime ASC"), use_container_width=True)

    with tab2:
        st.subheader("Pokrivenost i Promet po Oblastima")
        df_okruzi = citaj("""
            SELECT k.okrug, COUNT(DISTINCT k.id) as broj_kupaca, SUM(s.neto) as promet 
            FROM kupci k 
            LEFT JOIN fakture_glavno f ON k.id = f.kupac_id 
            LEFT JOIN fakture_stavke s ON f.id = s.faktura_id 
            GROUP BY k.okrug
        """)
        if not df_okruzi.empty:
            c1, c2 = st.columns(2)
            c1.write("**Pokrivenost kupcima po okruzima**")
            c1.bar_chart(df_okruzi.set_index('okrug')['broj_kupaca'])
            c2.write("**Najveći promet po okruzima (RSD)**")
            c2.bar_chart(df_okruzi.set_index('okrug')['promet'])

    with tab3:
        st.subheader("Lična karta kupca")
        df_k_list = citaj("SELECT id, ime, grad FROM kupci")
        if not df_k_list.empty:
            odabran = st.selectbox("Izaberi kupca za analizu:", [f"{r['id']} | {r['ime']} ({r['grad']})" for _, r in df_k_list.iterrows()])
            od_id = int(odabran.split(" | ")[0])
            
            stat = citaj(f"""
                SELECT COUNT(DISTINCT f.id) as br_faktura, SUM(s.komada) as komada_robe, SUM(s.neto) as zarada
                FROM fakture_glavno f JOIN fakture_stavke s ON f.id = s.faktura_id WHERE f.kupac_id = {od_id}
            """)
            st.write(f"**Ukupno faktura:** {stat['br_faktura'][0]} | **Ukupno komada:** {stat['komada_robe'][0]} | **Ukupna zarada:** {stat['zarada'][0]:,.2f} RSD")
            
            st.write("### Šta najviše kupuje (%) i Šta NE kupuje (0%)")
            roba_kupca = citaj(f"""
                SELECT r.naziv, COALESCE(SUM(s.komada), 0) as kolicina
                FROM tipovi_robe r
                LEFT JOIN fakture_stavke s ON r.id = s.roba_id 
                LEFT JOIN fakture_glavno f ON s.faktura_id = f.id AND f.kupac_id = {od_id}
                GROUP BY r.naziv ORDER BY kolicina DESC
            """)
            ukupno_robe = roba_kupca['kolicina'].sum()
            roba_kupca['procenat'] = (roba_kupca['kolicina'] / ukupno_robe * 100).fillna(0).round(1)
            
            c1, c2 = st.columns(2)
            c1.dataframe(roba_kupca[roba_kupca['kolicina'] > 0])
            nule = roba_kupca[roba_kupca['kolicina'] == 0]
            if not nule.empty:
                c2.error("**Ovo nikada nije kupio (Potencijal za prodaju):**")
                c2.dataframe(nule[['naziv']])
            
            if st.button("🖨️ Pripremi za PDF štampu"):
                st.info("Pritisni Ctrl+P (ili Cmd+P) na tastaturi i izaberi 'Save as PDF'. Ovo je najčistiji prikaz za štampanje klijenta.")

    with tab4:
        st.subheader("Trendovi Prometa (Poslednja 3 meseca vs Prethodna 3 meseca)")
        today = date.today()
        m3_ago = today - timedelta(days=90)
        m6_ago = today - timedelta(days=180)
        
        upit_trend = f"""
            WITH T_Now AS (
                SELECT f.kupac_id, SUM(s.neto) as zarada_sada FROM fakture_glavno f 
                JOIN fakture_stavke s ON f.id = s.faktura_id 
                WHERE f.datum >= '{m3_ago}' GROUP BY f.kupac_id
            ), T_Old AS (
                SELECT f.kupac_id, SUM(s.neto) as zarada_pre FROM fakture_glavno f 
                JOIN fakture_stavke s ON f.id = s.faktura_id 
                WHERE f.datum >= '{m6_ago}' AND f.datum < '{m3_ago}' GROUP BY f.kupac_id
            )
            SELECT k.ime, k.grad, COALESCE(n.zarada_sada, 0) as period_sada, COALESCE(o.zarada_pre, 0) as period_pre
            FROM kupci k
            LEFT JOIN T_Now n ON k.id = n.kupac_id
            LEFT JOIN T_Old o ON k.id = o.kupac_id
            WHERE COALESCE(n.zarada_sada, 0) > 0 OR COALESCE(o.zarada_pre, 0) > 0
        """
        df_trend = citaj(upit_trend)
        if not df_trend.empty:
            def oceni_trend(row):
                ako = row['period_sada']
                pre = row['period_pre']
                if pre == 0: return "Rast"
                promena = (ako - pre) / pre * 100
                if promena > 3: return "Rast"
                elif promena < -3: return "Pad"
                else: return "Isto"
                
            df_trend['Status'] = df_trend.apply(oceni_trend, axis=1)
            
            def color_status(val):
                if val == 'Pad': return 'background-color: #ffcccc; color: red;'
                if val == 'Rast': return 'background-color: #ccffcc; color: green;'
                return ''
                
            st.dataframe(df_trend.style.applymap(color_status, subset=['Status']), use_container_width=True)

# ==========================================
# 📦 KATALOG ROBE
# ==========================================
elif meni == "📦 Katalog Robe":
    st.title("Katalog Robe")
    with st.form("nr"):
        n = st.text_input("Naziv artikla")
        if st.form_submit_button("Dodaj u katalog"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n})
            st.rerun()
            
    df_t = citaj("SELECT * FROM tipovi_robe")
    st.dataframe(df_t, use_container_width=True)
    
    st.subheader("Analitika Robe")
    t1, t2 = st.tabs(["Najviše komada prodato", "Najveća zarada"])
    
    df_roba_stat = citaj("""
        SELECT r.naziv, SUM(s.komada) as komada, SUM(s.neto) as zarada
        FROM tipovi_robe r JOIN fakture_stavke s ON r.id = s.roba_id GROUP BY r.naziv
    """)
    if not df_roba_stat.empty:
        with t1:
            st.altair_chart(alt.Chart(df_roba_stat).mark_arc().encode(theta="komada", color="naziv"), use_container_width=True)
        with t2:
            st.altair_chart(alt.Chart(df_roba_stat).mark_arc().encode(theta="zarada", color="naziv"), use_container_width=True)
