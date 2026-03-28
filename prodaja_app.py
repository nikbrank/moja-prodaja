import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
import urllib.parse

# --- 1. PODEŠAVANJE ---
st.set_page_config(page_title="Poslovni Panel v6.2", layout="wide")

# --- 2. POVEZIVANJE ---
try:
    db_pass = st.secrets["DB_PASSWORD"]
    p_ref = st.secrets["PROJECT_REF"]
    app_pass = st.secrets["APP_LOGIN_SIFRA"]
    safe_pass = urllib.parse.quote_plus(db_pass)
    DB_URL = f"postgresql://postgres.{p_ref}:{safe_pass}@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    engine = create_engine(DB_URL, connect_args={"sslmode": "require"})
except Exception as e:
    st.error(f"Greška sa konekcijom: {e}"); st.stop()

# --- 3. POMOĆNE FUNKCIJE ---
def izvrsi(upit, params=None):
    with engine.begin() as conn:
        conn.execute(text(upit), params or {})

def citaj(tabela, order_by=None):
    upit = f"SELECT * FROM {tabela}"
    if order_by: upit += f" ORDER BY {order_by}"
    return pd.read_sql(upit, engine)

# Inicijalizacija tabela (Dodata tabela za kurire i kolone u prodaji)
izvrsi("CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL)")
izvrsi("CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
izvrsi("CREATE TABLE IF NOT EXISTS kuriri (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE, cena REAL)")
izvrsi("CREATE TABLE IF NOT EXISTS prodaja (id SERIAL PRIMARY KEY, datum TEXT, kupac_info TEXT, roba TEXT, komada INTEGER, bruto REAL, neto REAL, okrug TEXT, prevoz TEXT, kurir TEXT)")

# --- 4. GEOGRAFIJA ---
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
SVI_GRADOVI = sorted([g for lista in SRBIJA_MAPA.values() for g in lista])

# --- 5. DIJALOZI ---
@st.dialog("Izmeni Kurira")
def izmeni_kurira_dialog(row):
    n_naziv = st.text_input("Služba", value=row['naziv'])
    n_cena = st.number_input("Cena paketa", value=float(row['cena']))
    if st.button("Sačuvaj"):
        izvrsi("UPDATE kuriri SET naziv=:n, cena=:c WHERE id=:id", {"n": n_naziv, "c": n_cena, "id": row['id']})
        st.rerun()

# --- 6. LOGIN ---
if "auth" not in st.session_state: st.session_state["auth"] = False
if not st.session_state["auth"]:
    st.title("🔐 Pristup")
    lozinka = st.text_input("Šifra:", type="password")
    if st.button("Ulaz"):
        if lozinka == app_pass: st.session_state["auth"] = True; st.rerun()
        else: st.error("Pogrešna šifra!")
    st.stop()

# --- 7. NAVIGACIJA ---
meni = st.sidebar.radio("Navigacija:", ["📊 Pregled", "📝 Nova Faktura", "👥 Kupci", "📦 Katalog Robe"])

# --- MODUL: PREGLED (DASHBOARD) ---
if meni == "📊 Pregled":
    st.title("📊 Pregled Poslovanja")
    df_p = citaj("prodaja", "id DESC")
    if not df_p.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Ukupan Neto (RSD)", f"{df_p['neto'].sum():,.2f}")
        c2.metric("Broj Faktura", len(df_p))
        c3.metric("Prodatih Komada", int(df_p['komada'].sum()))
        
        st.subheader("📜 Istorija Faktura")
        st.dataframe(df_p[['datum', 'kupac_info', 'roba', 'komada', 'neto', 'prevoz', 'kurir']], use_container_width=True)
    else: st.info("Baza je prazna. Unesite fakturu.")

# --- MODUL: NOVA FAKTURA ---
elif meni == "📝 Nova Faktura":
    st.title("📝 Nova Faktura")
    df_k = citaj("kupci", "ime ASC")
    df_t = citaj("tipovi_robe", "naziv ASC")
    df_s = citaj("kuriri", "naziv ASC")
    
    if not df_k.empty and not df_t.empty:
        with st.form("faktura_form"):
            c1, c2 = st.columns(2)
            dat = c1.date_input("Datum", date.today())
            k_izbor = c1.selectbox("Kupac", [f"{r['ime']} | {r['grad']}" for _, r in df_k.iterrows()])
            artikal = c2.selectbox("Roba", df_t['naziv'])
            kol = c2.number_input("Količina", min_value=1)
            iznos = c1.number_input("Bruto (RSD)", min_value=0.0)
            
            # Logistika
            tip_prevoza = c2.radio("Vrsta prevoza:", ["Lično preuzimanje", "Njihov prevoz (Kurir)"])
            kurir_ime = "N/A"
            if tip_prevoza == "Njihov prevoz (Kurir)":
                if not df_s.empty:
                    kurir_ime = c2.selectbox("Izaberi kurirsku službu:", df_s['naziv'])
                else:
                    st.warning("Niste uneli nijednu kurirsku službu u Katalogu!")

            if st.form_submit_button("✅ Proknjiži Fakturu"):
                f_ime, f_grad = k_izbor.split(" | ")
                k_data = df_k[(df_k['ime'] == f_ime) & (df_k['grad'] == f_grad)].iloc[0]
                neto = iznos * (1 - k_data['rabat']/100)
                
                izvrsi("""INSERT INTO prodaja (datum, kupac_info, roba, komada, bruto, neto, okrug, prevoz, kurir) 
                          VALUES (:d, :k, :r, :ko, :b, :n, :o, :p, :ku)""",
                       {"d": str(dat), "k": k_izbor, "r": artikal, "ko": kol, "b": iznos, "n": neto, 
                        "o": k_data['okrug'], "p": tip_prevoza, "ku": kurir_ime})
                st.success("Faktura je uspešno sačuvana!")
                st.rerun()
    else: st.warning("Prvo popunite kupce i katalog robe.")

# --- MODUL: KUPCI ---
elif meni == "👥 Kupci":
    st.title("👥 Kupci")
    tab1, tab2, tab3, tab4 = st.tabs(["➕ Dodaj", "📋 Lista", "📊 Grafikoni", "🗺️ Mapa"])
    # ... (Ostatak koda za kupce ostaje isti kao v6.1)
    with tab2:
        df_k = citaj("kupci", "ime ASC")
        for _, row in df_k.iterrows():
            c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 1, 0.5, 0.5])
            c1.write(row['ime']); c2.write(row['grad']); c3.write(row['okrug']); c4.write(f"{row['rabat']}%")
            if c5.button("✏️", key=f"ek_{row['id']}"): pass # Ovde ide dijalog
            if c6.button("🗑️", key=f"dk_{row['id']}"): izvrsi("DELETE FROM kupci WHERE id=:id", {"id": row['id']}); st.rerun()
            st.divider()
    # (Za tab3 i tab4 važi isto iz v6.1)

# --- MODUL: KATALOG ROBE ---
elif meni == "📦 Katalog Robe":
    st.title("📦 Katalog i Logistika")
    t_roba, t_kuriri = st.tabs(["📦 Artikli", "🚚 Brza Pošta"])
    
    with t_roba:
        with st.form("n_r"):
            n_art = st.text_input("Novi artikal")
            if st.form_submit_button("Dodaj"):
                izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n_art.strip()})
                st.rerun()
        df_t = citaj("tipovi_robe", "naziv ASC")
        for _, row in df_t.iterrows():
            c1, c2, c3 = st.columns([5, 0.5, 0.5])
            c1.write(row['naziv'])
            if c3.button("🗑️", key=f"dr_{row['id']}"): izvrsi("DELETE FROM tipovi_robe WHERE id=:id", {"id": row['id']}); st.rerun()
            st.divider()

    with t_kuriri:
        with st.form("n_kurir"):
            c_naziv = st.text_input("Naziv kurirske službe (npr. AKS)")
            c_cena = st.number_input("Cena po paketu (RSD)", min_value=0.0)
            if st.form_submit_button("Sačuvaj Službu"):
                izvrsi("INSERT INTO kuriri (naziv, cena) VALUES (:n, :c) ON CONFLICT DO NOTHING", {"n": c_naziv.strip(), "c": c_cena})
                st.rerun()
        
        df_s = citaj("kuriri", "naziv ASC")
        for _, row in df_s.iterrows():
            c1, c2, c3, c4 = st.columns([3, 2, 0.5, 0.5])
            c1.write(row['naziv'])
            c2.write(f"{row['cena']} RSD")
            if c3.button("✏️", key=f"es_{row['id']}"): izmeni_kurira_dialog(row)
            if c4.button("🗑️", key=f"ds_{row['id']}"): izvrsi("DELETE FROM kuriri WHERE id=:id", {"id": row['id']}); st.rerun()
            st.divider()
