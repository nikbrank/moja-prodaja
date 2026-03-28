import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
import urllib.parse

# --- 1. PODEŠAVANJE STRANICE ---
st.set_page_config(page_title="Poslovni Panel v4.7 - FULL", layout="wide")

# --- 2. POVEZIVANJE (Secrets) ---
try:
    db_pass = st.secrets["DB_PASSWORD"]
    p_ref = st.secrets["PROJECT_REF"]
    app_pass = st.secrets["APP_LOGIN_SIFRA"]
    safe_pass = urllib.parse.quote_plus(db_pass)
    DB_URL = f"postgresql://postgres.{p_ref}:{safe_pass}@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    engine = create_engine(DB_URL, connect_args={"sslmode": "require"})
except KeyError as e:
    st.error(f"Greška u Secrets: {e}")
    st.stop()

# --- 3. LOGIN SISTEM ---
if "auth" not in st.session_state:
    st.session_state["auth"] = False

if not st.session_state["auth"]:
    st.title("🔐 Privatni Cloud Panel")
    lozinka = st.text_input("Lozinka za pristup:", type="password")
    if st.button("Prijavi se"):
        if lozinka == app_pass:
            st.session_state["auth"] = True
            st.rerun()
        else:
            st.error("Netačna lozinka!")
    st.stop()

# --- 4. GEOGRAFIJA SRBIJE (KOMPLETNA LISTA) ---
SRBIJA_MAPA = {
    "Severnobački": ["Subotica", "Bačka Topola", "Mali Iđoš"],
    "Srednjebanatski": ["Zrenjanin", "Novi Bečej", "Sečanj", "Žitište", "Nova Crnja"],
    "Severnobanatski": ["Kikinda", "Senta", "Ada", "Kanjiža", "Novi Kneževac", "Čoka"],
    "Južnobanatski": ["Pančevo", "Vršac", "Bela Crkva", "Alibunar", "Kovačica", "Kovin", "Opovo", "Plandište"],
    "Zapadnobački": ["Sombor", "Apatin", "Kula", "Odžaci"],
    "Južnobački": ["Novi Sad", "Bačka Palanka", "Bački Petrovac", "Bečej", "Beočin", "Temerin", "Titel", "Vrbas", "Žabalj", "Srbobran"],
    "Sremski": ["Sremska Mitrovica", "Inđija", "Irig", "Ruma", "Stara Pazova", "Šid", "Pećinci"],
    "Mačvanski": ["Šabac", "Loznica", "Bogatić", "Vladimirci", "Koceljeva", "Mali Zvornik", "Krupanj", "Ljubovija"],
    "Kolubarski": ["Valjevo", "Lajkovac", "Ljig", "Mionica", "Osečina", "Ub"],
    "Podunavski": ["Smederevo", "Smederevska Palanka", "Velika Plana"],
    "Braničevski": ["Požarevac", "Veliko Gradište", "Golubac", "Kučevo", "Petrovac na Mlavi", "Žabari", "Žagubica", "Malo Crniće"],
    "Šumadijski": ["Kragujevac", "Aranđelovac", "Batočina", "Knić", "Lapovo", "Rača", "Topola"],
    "Pomoravski": ["Jagodina", "Ćuprija", "Paraćin", "Svilajnac", "Despotovac", "Rekovac"],
    "Borski": ["Bor", "Majdanpek", "Negotin", "Kladovo"],
    "Zaječarski": ["Zaječar", "Boljevac", "Knjaževac", "Sokobanja"],
    "Zlatiborski": ["Užice", "Bajina Bašta", "Kosjerić", "Nova Varoš", "Požega", "Priboj", "Prijepolje", "Sjenica", "Čajetina", "Arilje"],
    "Moravički": ["Čačak", "Gornji Milanovac", "Ivanjica", "Lučani"],
    "Raški": ["Kraljevo", "Novi Pazar", "Raška", "Vrnjačka Banja", "Tutin"],
    "Rasinski": ["Kruševac", "Aleksandrovac", "Brus", "Varvarin", "Trstenik", "Ćićevac"],
    "Nišavski": ["Niš", "Aleksinac", "Svrljig", "Merošina", "Ražanj", "Doljevac", "Gadžin Han"],
    "Toplički": ["Prokuplje", "Blace", "Kuršumlija", "Žitorađa"],
    "Pirotski": ["Pirot", "Bela Palanka", "Dimitrovgrad", "Babušnica"],
    "Jablanički": ["Leskovac", "Vlasotince", "Lebane", "Bojnik", "Medveđa", "Crna Trava"],
    "Pčinjski": ["Vranje", "Bujanovac", "Preševo", "Surdulica", "Vladičin Han", "Trgovište", "Bosilegrad"],
    "Kosovski/Metohijski": ["Priština", "Prizren", "Peć", "Kosovska Mitrovica", "Gnjilane", "Đakovica", "Uroševac"],
    "Grad Beograd": ["Beograd", "Mladenovac", "Lazarevac", "Obrenovac", "Barajevo", "Grocka", "Sopot", "Surčin"]
}
SVI_GRADOVI = sorted(list(set([g for lista in SRBIJA_MAPA.values() for g in lista])))

# --- 5. POMOĆNE FUNKCIJE ZA BAZU ---
def izvrsi(upit, params=None):
    with engine.begin() as conn:
        conn.execute(text(upit), params or {})

def citaj(tabela, order_by=None):
    upit = f"SELECT * FROM {tabela}"
    if order_by: upit += f" ORDER BY {order_by}"
    return pd.read_sql(upit, engine)

# Inicijalizacija tabela
izvrsi("CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL)")
izvrsi("CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
izvrsi("CREATE TABLE IF NOT EXISTS prodaja (id SERIAL PRIMARY KEY, datum TEXT, kupac TEXT, roba TEXT, komada INTEGER, bruto REAL, neto REAL)")

# --- 6. NAVIGACIJA ---
st.sidebar.title("🏢 Cloud Panel v4.7")
meni = st.sidebar.radio("Meni:", ["📊 Dashboard", "📝 Nova Faktura", "👥 Kupci", "📦 Katalog Robe"])

# --- MODUL: DASHBOARD ---
if meni == "📊 Dashboard":
    st.title("📊 Izveštaji i Analitika")
    df_p = citaj("prodaja", "datum DESC")
    if not df_p.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Ukupan Neto (RSD)", f"{df_p['neto'].sum():,.2f}")
        c2.metric("Broj Faktura", len(df_p))
        c3.metric("Prodatih Komada", int(df_p['komada'].sum()))
        
        st.markdown("---")
        st.subheader("📦 Prodaja po artiklima (Sumarno)")
        analitika_robe = df_p.groupby('roba').agg({'komada': 'sum', 'neto': 'sum'}).reset_index().sort_values(by='neto', ascending=False)
        analitika_robe.columns = ['Naziv Artikla', 'Ukupno Komada', 'Ukupna Vrednost (Neto)']
        st.table(analitika_robe)
        
        st.markdown("---")
        st.subheader("📜 Istorija svih prodaja")
        st.dataframe(df_p, use_container_width=True)
    else:
        st.info("Baza je trenutno prazna. Unesite prvu prodaju.")

# --- MODUL: NOVA FAKTURA ---
elif meni == "📝 Nova Faktura":
    st.title("📝 Unos nove prodaje")
    df_k = citaj("kupci", "ime ASC")
    df_t = citaj("tipovi_robe", "naziv ASC")
    
    if not df_k.empty and not df_t.empty:
        with st.form("faktura_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            dat = c1.date_input("Datum", date.today())
            lista_k = [f"{r['ime']} ({r['grad']})" for i, r in df_k.iterrows()]
            izabran_k_pun = c1.selectbox("Izaberi Kupca", lista_k)
            
            ime_firme = izabran_k_pun.rsplit(" (", 1)[0]
            tip = c2.selectbox("Roba / Artikal", df_t['naziv'])
            kom = c2.number_input("Količina (komada)", min_value=1)
            izn = c1.number_input("Bruto Iznos (RSD)", min_value=0.0)
            
            r_val = df_k[df_k['ime'] == ime_firme]['rabat'].values[0]
            
            if st.form_submit_button("✅ Sačuvaj Prodaju"):
                neto_v = izn * (1 - r_val/100)
                izvrsi("INSERT INTO prodaja (datum, kupac, roba, komada, bruto, neto) VALUES (:d, :k, :r, :ko, :b, :n)",
                       {"d": str(dat), "k": ime_firme, "r": tip, "ko": kom, "b": izn, "n": neto_v})
                st.success(f"Snimljeno! Neto iznos: {neto_v:,.2f} RSD")
    else:
        st.warning("Prvo popunite kupce i katalog robe.")

# --- MODUL: KUPCI (SA TRI TABA) ---
elif meni == "👥 Kupci":
    st.title("👥 Baza Kupaca i Geografija")
    t1, t2, t3 = st.tabs(["➕ Dodaj Kupca", "🔍 Lista i Brisanje", "🗺️ Distribucija po okruzima"])
    
    with t1:
        with st.form("novi_k_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            ime_k = c1.text_input("Naziv Firme / Kupca")
            grad_k = c2.selectbox("Grad", SVI_GRADOVI)
            rabat_k = c1.number_input("Rabat (%)", min_value=0.0)
            okrug_k = next((o for o, g in SRBIJA_MAPA.items() if grad_k in g), "Ostalo")
            
            if st.form_submit_button("Sačuvaj Kupca"):
                izvrsi("INSERT INTO kupci (ime, grad, okrug, rabat) VALUES (:i, :g, :o, :r)", 
                       {"i": ime_k, "g": grad_k, "o": okrug_k, "r": rabat_k})
                st.success(f"Kupac dodat u {okrug_k} okrug!")
                st.rerun()

    with t2:
        df_k = citaj("kupci", "ime ASC")
        if not df_k.empty:
            st.subheader("Kompletna lista")
            st.dataframe(df_k[['ime', 'grad', 'okrug', 'rabat']], use_container_width=True)
            
            st.markdown("---")
            k_bris = st.selectbox("Izaberi kupca za brisanje:", df_k['ime'])
            if st.button("❌ Obriši kupca"):
                izvrsi("DELETE FROM kupci WHERE ime = :i", {"i": k_bris})
                st.rerun()
        else:
            st.info("Nema unetih kupaca.")

    with t3:
        df_k_mapa = citaj("kupci")
        if not df_k_mapa.empty:
            st.subheader("Statistika po okruzima")
            okruzi_count = df_k_mapa['okrug'].value_counts()
            st.bar_chart(okruzi_count)
            st.write("Broj kupaca po regionima:")
            st.write(okruzi_count)
        else:
            st.info("Nema podataka za prikaz distribucije.")

# --- MODUL: KATALOG ROBE ---
elif meni == "📦 Katalog Robe":
    st.title("📦 Katalog")
    with st.form("katalog_form", clear_on_submit=True):
        n_a = st.text_input("Naziv artikla (Bočna fioka, Džambo šina, Korpa za veš...)")
        if st.form_submit_button("Dodaj u Katalog"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n_a.strip()})
            st.rerun()
    
    df_t = citaj("tipovi_robe", "naziv ASC")
    st.dataframe(df_t, use_container_width=True)
    if not df_t.empty:
        r_bris = st.selectbox("Izaberi artikal za uklanjanje:", df_t['naziv'])
        if st.button("🗑️ Obriši artikal"):
            izvrsi("DELETE FROM tipovi_robe WHERE naziv = :n", {"n": r_bris})
            st.rerun()
