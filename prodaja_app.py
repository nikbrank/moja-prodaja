import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
import urllib.parse

# --- 1. PODEŠAVANJE ---
st.set_page_config(page_title="Poslovni Panel v6.4", layout="wide")

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
    upit = f"SELECT * FROM {tabela}"
    if order_by: upit += f" ORDER BY {order_by}"
    return pd.read_sql(upit, engine)

# --- 4. BAZA AUTO-FIX (Dodavanje kolona koje fale) ---
izvrsi("CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL)")
izvrsi("CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
izvrsi("CREATE TABLE IF NOT EXISTS kuriri (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE, cena REAL)")
izvrsi("CREATE TABLE IF NOT EXISTS prodaja (id SERIAL PRIMARY KEY, datum TEXT)")

# Provera i dodavanje kolona u 'prodaja' ako ne postoje
kolone_za_dodavanje = {
    "kupac_info": "TEXT",
    "roba": "TEXT",
    "komada": "INTEGER",
    "bruto": "REAL",
    "neto": "REAL",
    "okrug": "TEXT",
    "prevoz": "TEXT",
    "kurir": "TEXT"
}

for kolona, tip in kolone_za_dodavanje.items():
    try:
        izvrsi(f"ALTER TABLE prodaja ADD COLUMN {kolona} {tip}")
    except Exception:
        pass # Kolona već postoji, idemo dalje

# --- 5. GEOGRAFIJA ---
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

# --- 6. DIJALOZI ---
@st.dialog("Izmeni Kupca")
def izmeni_kupca_dialog(row):
    novo_ime = st.text_input("Ime firme", value=row['ime'])
    novi_grad = st.selectbox("Grad", SVI_GRADOVI, index=SVI_GRADOVI.index(row['grad']))
    novi_rabat = st.number_input("Rabat (%)", value=float(row['rabat']))
    if st.button("Sačuvaj izmene"):
        n_okrug = next((o for o, g in SRBIJA_MAPA.items() if novi_grad in g), "Ostalo")
        izvrsi("UPDATE kupci SET ime=:i, grad=:g, okrug=:o, rabat=:r WHERE id=:id",
               {"i": novo_ime, "g": novi_grad, "o": n_okrug, "r": novi_rabat, "id": row['id']})
        st.rerun()

@st.dialog("Izmeni Kurira")
def izmeni_kurira_dialog(row):
    n_naziv = st.text_input("Služba", value=row['naziv'])
    n_cena = st.number_input("Cena", value=float(row['cena']))
    if st.button("Sačuvaj"):
        izvrsi("UPDATE kuriri SET naziv=:n, cena=:c WHERE id=:id", {"n": n_naziv, "c": n_cena, "id": row['id']})
        st.rerun()

# --- 7. LOGIN ---
if "auth" not in st.session_state: st.session_state["auth"] = False
if not st.session_state["auth"]:
    st.title("🔐 Ulaz")
    lozinka = st.text_input("Lozinka:", type="password")
    if st.button("Prijavi se"):
        if lozinka == app_pass: st.session_state["auth"] = True; st.rerun()
        else: st.error("Pogrešna lozinka!")
    st.stop()

# --- 8. NAVIGACIJA ---
meni = st.sidebar.radio("Navigacija:", ["📊 Pregled", "📝 Nova Faktura", "👥 Kupci", "📦 Katalog Robe", "🚚 Brza Pošta"])

# --- MODUL: PREGLED ---
if meni == "📊 Pregled":
    st.title("📊 Pregled Poslovanja")
    df_p = citaj("prodaja", "id DESC")
    if not df_p.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Ukupno Neto", f"{df_p['neto'].sum():,.2f} RSD")
        c2.metric("Broj Faktura", len(df_p))
        c3.metric("Prodato Komada", int(df_p['komada'].sum()))
        st.subheader("📜 Zadnje Fakture")
        st.dataframe(df_p[['datum', 'kupac_info', 'roba', 'komada', 'neto', 'prevoz', 'kurir']], width='stretch')
    else: st.info("Nema podataka. Unesite prvu fakturu.")

# --- MODUL: NOVA FAKTURA ---
elif meni == "📝 Nova Faktura":
    st.title("📝 Nova Faktura")
    df_k = citaj("kupci", "ime ASC"); df_t = citaj("tipovi_robe", "naziv ASC"); df_s = citaj("kuriri", "naziv ASC")
    if not df_k.empty and not df_t.empty:
        with st.form("faktura_forma"):
            c1, c2 = st.columns(2)
            dat = c1.date_input("Datum", date.today())
            k_izbor = c1.selectbox("Kupac", [f"{r['ime']} | {r['grad']}" for _, r in df_k.iterrows()])
            artikal = c2.selectbox("Roba", df_t['naziv'])
            kol = c2.number_input("Količina", min_value=1)
            iznos = c1.number_input("Bruto (RSD)", min_value=0.0)
            tip_prevoza = c2.selectbox("Vrsta prevoza (Obavezno):", ["--- Izaberi ---", "Lično preuzimanje", "Njihov prevoz (Kurir)"])
            
            kurir_ime = "N/A"
            if tip_prevoza == "Njihov prevoz (Kurir)":
                if not df_s.empty: kurir_ime = c2.selectbox("Izaberi kurirsku službu:", df_s['naziv'])
                else: st.warning("Prvo unesi kurire u meni 'Brza Pošta'!")

            if st.form_submit_button("✅ Sačuvaj"):
                if tip_prevoza == "--- Izaberi ---":
                    st.error("Morate izabrati vrstu prevoza!")
                else:
                    f_ime, f_grad = k_izbor.split(" | ")
                    k_data = df_k[(df_k['ime'] == f_ime) & (df_k['grad'] == f_grad)].iloc[0]
                    neto = iznos * (1 - k_data['rabat']/100)
                    izvrsi("INSERT INTO prodaja (datum, kupac_info, roba, komada, bruto, neto, okrug, prevoz, kurir) VALUES (:d, :k, :r, :ko, :b, :n, :o, :p, :ku)",
                           {"d": str(dat), "k": k_izbor, "r": artikal, "ko": kol, "b": iznos, "n": neto, "o": k_data['okrug'], "p": tip_prevoza, "ku": kurir_ime})
                    st.success("Faktura uneta!"); st.rerun()
    else: st.warning("Unesite kupce i robu prvo.")

# --- MODUL: KUPCI ---
elif meni == "👥 Kupci":
    st.title("👥 Kupci")
    tab1, tab2, tab3 = st.tabs(["➕ Dodaj", "📋 Lista", "📊 Grafikoni"])
    with tab1:
        with st.form("n_k"):
            ime = st.text_input("Ime Firme")
            grad = st.selectbox("Grad", ["--- Izaberite grad ---"] + SVI_GRADOVI)
            rabat = st.number_input("Rabat %", min_value=0.0)
            if st.form_submit_button("Dodaj"):
                if grad != "--- Izaberite grad ---" and ime:
                    okr = next((o for o, g in SRBIJA_MAPA.items() if grad in g), "Ostalo")
                    izvrsi("INSERT INTO kupci (ime, grad, okrug, rabat) VALUES (:i, :g, :o, :r)", {"i": ime, "g": grad, "o": okr, "r": rabat})
                    st.rerun()
    with tab2:
        df_k = citaj("kupci", "ime ASC")
        for _, row in df_k.iterrows():
            c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 1, 0.5, 0.5])
            c1.write(row['ime']); c2.write(row['grad']); c3.write(row['okrug']); c4.write(f"{row['rabat']}%")
            if c5.button("✏️", key=f"ek_{row['id']}"): izmeni_kupca_dialog(row)
            if c6.button("🗑️", key=f"dk_{row['id']}"): izvrsi("DELETE FROM kupci WHERE id=:id", {"id": row['id']}); st.rerun()
            st.divider()
    with tab3:
        df_k_stat = citaj("kupci"); df_p_stat = citaj("prodaja")
        col1, col2 = st.columns(2)
        if not df_k_stat.empty:
            with col1:
                st.write("**Udeo kupaca po okrugu (%)**")
                k_dist = df_k_stat['okrug'].value_counts(normalize=True).reset_index()
                k_dist.columns = ['Okrug', 'Udeo']; k_dist['Udeo'] *= 100
                st.bar_chart(k_dist.set_index('Okrug'))
        if not df_p_stat.empty:
            with col2:
                st.write("**Udeo robe po okrugu (%)**")
                r_dist = df_p_stat.groupby('okrug')['komada'].sum().reset_index()
                r_dist['Udeo'] = (r_dist['komada'] / r_dist['komada'].sum()) * 100
                st.bar_chart(r_dist.set_index('okrug')['Udeo'])

# --- MODUL: KATALOG ROBE ---
elif meni == "📦 Katalog Robe":
    st.title("📦 Katalog")
    with st.form("n_r"):
        n_art = st.text_input("Naziv artikla")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n_art.strip()})
            st.rerun()
    df_t = citaj("tipovi_robe", "naziv ASC")
    for _, row in df_t.iterrows():
        c1, c2, c3 = st.columns([5, 0.5, 0.5])
        c1.write(row['naziv'])
        if c3.button("🗑️", key=f"dr_{row['id']}"): izvrsi("DELETE FROM tipovi_robe WHERE id=:id", {"id": row['id']}); st.rerun()
        st.divider()

# --- MODUL: BRZA POŠTA ---
elif meni == "🚚 Brza Pošta":
    st.title("🚚 Brza Pošta")
    with st.form("n_kurir"):
        c_n = st.text_input("Naziv službe")
        c_c = st.number_input("Cena paketa (RSD)", min_value=0.0)
        if st.form_submit_button("Sačuvaj"):
            izvrsi("INSERT INTO kuriri (naziv, cena) VALUES (:n, :c) ON CONFLICT DO NOTHING", {"n": c_n.strip(), "c": c_c})
            st.rerun()
    df_s = citaj("kuriri", "naziv ASC")
    for _, row in df_s.iterrows():
        c1, c2, c3, c4 = st.columns([3, 2, 0.5, 0.5])
        c1.write(row['naziv']); c2.write(f"{row['cena']} RSD")
        if c3.button("✏️", key=f"es_{row['id']}"): izmeni_kurira_dialog(row)
        if c4.button("🗑️", key=f"ds_{row['id']}"): izvrsi("DELETE FROM kuriri WHERE id=:id", {"id": row['id']}); st.rerun()
        st.divider()
