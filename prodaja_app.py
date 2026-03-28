import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date
import urllib.parse

# --- 1. PODEŠAVANJE I STIL ---
st.set_page_config(page_title="Poslovni Panel v6.0", layout="wide")

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

# Inicijalizacija
izvrsi("CREATE TABLE IF NOT EXISTS kupci (id SERIAL PRIMARY KEY, ime TEXT, grad TEXT, okrug TEXT, rabat REAL)")
izvrsi("CREATE TABLE IF NOT EXISTS tipovi_robe (id SERIAL PRIMARY KEY, naziv TEXT UNIQUE)")
izvrsi("CREATE TABLE IF NOT EXISTS prodaja (id SERIAL PRIMARY KEY, datum TEXT, kupac_info TEXT, roba TEXT, komada INTEGER, bruto REAL, neto REAL, okrug TEXT)")

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

# --- 5. DIJALOZI ZA IZMENU ---
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

@st.dialog("Izmeni Artikal")
def izmeni_robu_dialog(row):
    novi_naziv = st.text_input("Naziv artikla", value=row['naziv'])
    if st.button("Sačuvaj"):
        izvrsi("UPDATE tipovi_robe SET naziv=:n WHERE id=:id", {"n": novi_naziv, "id": row['id']})
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
meni = st.sidebar.radio("Navigacija:", ["📊 Dashboard", "📝 Nova Faktura", "👥 Kupci", "📦 Katalog Robe"])

# --- MODUL: DASHBOARD ---
if meni == "📊 Dashboard":
    st.title("📊 Izveštaji i Distribucija")
    df_p = citaj("prodaja")
    if not df_p.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📍 Prodaja po okruzima (%)")
            dist = df_p.groupby('okrug')['komada'].sum().reset_index()
            dist['procenat'] = (dist['komada'] / dist['komada'].sum()) * 100
            st.dataframe(dist.style.format({'procenat': '{:.2f}%'}), use_container_width=True)
        with c2:
            st.bar_chart(dist.set_index('okrug')['procenat'])
    else: st.info("Nema podataka o prodaji.")

# --- MODUL: NOVA FAKTURA ---
elif meni == "📝 Nova Faktura":
    st.title("📝 Nova Faktura")
    df_k = citaj("kupci", "ime ASC")
    df_t = citaj("tipovi_robe", "naziv ASC")
    if not df_k.empty and not df_t.empty:
        with st.form("faktura"):
            c1, c2 = st.columns(2)
            dat = c1.date_input("Datum", date.today())
            k_izbor = c1.selectbox("Kupac", [f"{r['ime']} | {r['grad']}" for _, r in df_k.iterrows()])
            artikal = c2.selectbox("Roba", df_t['naziv'])
            kol = c2.number_input("Količina", min_value=1)
            iznos = c1.number_input("Bruto (RSD)", min_value=0.0)
            
            if st.form_submit_button("✅ Snimi"):
                f_ime, f_grad = k_izbor.split(" | ")
                k_data = df_k[(df_k['ime'] == f_ime) & (df_k['grad'] == f_grad)].iloc[0]
                neto = iznos * (1 - k_data['rabat']/100)
                izvrsi("INSERT INTO prodaja (datum, kupac_info, roba, komada, bruto, neto, okrug) VALUES (:d, :k, :r, :ko, :b, :n, :o)",
                       {"d": str(dat), "k": k_izbor, "r": artikal, "ko": kol, "b": iznos, "n": neto, "o": k_data['okrug']})
                st.success("Faktura proknjižena!")
    else: st.warning("Prvo unesi kupce i robu.")

# --- MODUL: KUPCI ---
elif meni == "👥 Kupci":
    st.title("👥 Kupci i Mapa")
    tab1, tab2, tab3 = st.tabs(["➕ Novi Kupac", "📋 Lista", "🗺️ Mapa Pokrivenosti"])
    
    with tab1:
        with st.form("n_k"):
            ime = st.text_input("Ime Firme")
            grad = st.selectbox("Grad", ["--- Izaberite grad ---"] + SVI_GRADOVI)
            rabat = st.number_input("Rabat %", min_value=0.0)
            if st.form_submit_button("Dodaj"):
                if grad != "--- Izaberite grad ---" and ime:
                    df_c = citaj("kupci")
                    if not df_c[(df_c['ime']==ime) & (df_c['grad']==grad)].empty:
                        st.error("Ova firma već postoji u tom gradu!")
                    else:
                        okr = next((o for o, g in SRBIJA_MAPA.items() if grad in g), "Ostalo")
                        izvrsi("INSERT INTO kupci (ime, grad, okrug, rabat) VALUES (:i, :g, :o, :r)", {"i": ime, "g": grad, "o": okr, "r": rabat})
                        st.rerun()

    with tab2:
        df_k = citaj("kupci", "ime ASC")
        for _, row in df_k.iterrows():
            c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 1, 0.5, 0.5])
            c1.write(row['ime'])
            c2.write(row['grad'])
            c3.write(row['okrug'])
            c4.write(f"{row['rabat']}%")
            if c5.button("✏️", key=f"ed_{row['id']}"): izmeni_kupca_dialog(row)
            if c6.button("🗑️", key=f"del_{row['id']}"): 
                izvrsi("DELETE FROM kupci WHERE id=:id", {"id": row['id']})
                st.rerun()
            st.divider()

    with tab3:
        df_k = citaj("kupci")
        pokriveni = set(df_k['okrug'].unique())
        svi_okruzi = set(SRBIJA_MAPA.keys())
        nepokriveni = svi_okruzi - pokriveni
        
        col_a, col_b = st.columns(2)
        col_a.success(f"✅ Pokriveni okruzi ({len(pokriveni)}):")
        for o in sorted(list(pokriveni)): col_a.write(f"- {o}")
        col_b.error(f"❌ Nisu pokriveni ({len(nepokriveni)}):")
        for o in sorted(list(nepokriveni)): col_b.write(f"- {o}")

# --- MODUL: KATALOG ROBE ---
elif meni == "📦 Katalog Robe":
    st.title("📦 Katalog")
    with st.form("n_r"):
        n_art = st.text_input("Novi artikal")
        if st.form_submit_button("Dodaj"):
            izvrsi("INSERT INTO tipovi_robe (naziv) VALUES (:n) ON CONFLICT DO NOTHING", {"n": n_art})
            st.rerun()
    
    df_t = citaj("tipovi_robe", "naziv ASC")
    for _, row in df_t.iterrows():
        c1, c2, c3 = st.columns([5, 0.5, 0.5])
        c1.write(row['naziv'])
        if c2.button("✏️", key=f"re_{row['id']}"): izmeni_robu_dialog(row)
        if c3.button("🗑️", key=f"rd_{row['id']}"):
            izvrsi("DELETE FROM tipovi_robe WHERE id=:id", {"id": row['id']})
            st.rerun()
        st.divider()
