
import streamlit as st
import requests
import pandas as pd
import math
from datetime import date, timedelta

st.set_page_config(
    page_title="Football Analytics AI V2",
    page_icon="⚽",
    layout="wide"
)

BASE_URL = "https://api.football-data.org/v4"
HEADERS = {}
TIMEOUT = 20

st.title("⚽ Football Analytics AI V2")
st.caption("Analyse statistique, probabilités et aide à la décision")

# -------------------------------
# TOKEN
# -------------------------------

try:
    token = st.secrets["FOOTBALL_DATA_TOKEN"].strip()
except Exception:
    st.error("Token introuvable dans les Secrets de Streamlit.")
    st.stop()

if not token:
    st.error("Le token API est vide.")
    st.stop()

HEADERS = {"X-Auth-Token": token}


# -------------------------------
# API
# -------------------------------

def appeler_api(endpoint, params=None):
    try:
        response = requests.get(
            f"{BASE_URL}/{endpoint.lstrip('/')}",
            headers=HEADERS,
            params=params,
            timeout=TIMEOUT
        )

        if response.status_code == 200:
            return response.json()

        if response.status_code in (400, 401, 403, 429):
            st.error(f"Erreur API {response.status_code}")
            st.code(response.text[:500])
        else:
            st.error(f"Erreur API : {response.status_code}")
            st.code(response.text[:300])

    except requests.exceptions.RequestException as erreur:
        st.error("Problème de connexion à l'API.")
        st.code(str(erreur))

    return None


@st.cache_data(ttl=1800)
def charger_competitions():
    data = appeler_api("competitions")
    return data.get("competitions", []) if data else []


@st.cache_data(ttl=900)
def charger_matchs(code, debut, fin):
    data = appeler_api(
        f"competitions/{code}/matches",
        params={
            "dateFrom": debut,
            "dateTo": fin
        }
    )
    return data.get("matches", []) if data else []


# -------------------------------
# OUTILS STATISTIQUES
# -------------------------------

def poisson(k, moyenne):
    if moyenne < 0:
        return 0.0
    return math.exp(-moyenne) * moyenne**k / math.factorial(k)


def preparer_matchs(matchs):
    lignes = []

    for m in matchs:
        domicile = m.get("homeTeam") or {}
        exterieur = m.get("awayTeam") or {}
        score = m.get("score") or {}
        final = score.get("fullTime") or {}

        buts_dom = final.get("home")
        buts_ext = final.get("away")

        if (
            m.get("status") != "FINISHED"
            or buts_dom is None
            or buts_ext is None
        ):
            continue

        if not domicile.get("name") or not exterieur.get("name"):
            continue

        lignes.append({
            "domicile": domicile["name"],
            "exterieur": exterieur["name"],
            "buts_dom": int(buts_dom),
            "buts_ext": int(buts_ext)
        })

    return pd.DataFrame(lignes)


def calculer_probabilites(historique, equipe_dom, equipe_ext):
    if historique.empty:
        return None

    stats = {}

    for _, m in historique.iterrows():
        dom = m["domicile"]
        ext = m["exterieur"]
        bd = m["buts_dom"]
        be = m["buts_ext"]

        for equipe in (dom, ext):
            if equipe not in stats:
                stats[equipe] = {
                    "joues": 0,
                    "marques": 0,
                    "encaisses": 0
                }

        stats[dom]["joues"] += 1
        stats[dom]["marques"] += bd
        stats[dom]["encaisses"] += be

        stats[ext]["joues"] += 1
        stats[ext]["marques"] += be
        stats[ext]["encaisses"] += bd

    if equipe_dom not in stats or equipe_ext not in stats:
        return None

    # Eviter les estimations sur trop peu de matchs
    if (
        stats[equipe_dom]["joues"] < 3
        or stats[equipe_ext]["joues"] < 3
    ):
        return None

    moyenne_dom = historique["buts_dom"].mean()
    moyenne_ext = historique["buts_ext"].mean()
    moyenne_generale = (
        historique["buts_dom"].sum()
        + historique["buts_ext"].sum()
    ) / (2 * len(historique))

    if moyenne_generale <= 0:
        return None

    dom_stats = stats[equipe_dom]
    ext_stats = stats[equipe_ext]

    attaque_dom = (
        dom_stats["marques"] / dom_stats["joues"]
    )
    defense_dom = (
        dom_stats["encaisses"] / dom_stats["joues"]
    )
    attaque_ext = (
        ext_stats["marques"] / ext_stats["joues"]
    )
    defense_ext = (
        ext_stats["encaisses"] / ext_stats["joues"]
    )

    buts_attendus_dom = moyenne_dom * (
        attaque_dom / moyenne_generale
    ) * (defense_ext / moyenne_generale)

    buts_attendus_ext = moyenne_ext * (
        attaque_ext / moyenne_generale
    ) * (defense_dom / moyenne_generale)

    # Limite de prudence pour stabiliser le calcul
    buts_attendus_dom = max(0.05, min(5, buts_attendus_dom))
    buts_attendus_ext = max(0.05, min(5, buts_attendus_ext))

    p_dom = [poisson(k, buts_attendus_dom) for k in range(9)]
    p_ext = [poisson(k, buts_attendus_ext) for k in range(9)]

    victoire = 0.0
    nul = 0.0
    defaite = 0.0
    plus_25 = 0.0
    deux_marquent = 0.0

    for buts1 in range(9):
        for buts2 in range(9):
            p = p_dom[buts1] * p_ext[buts2]

            if buts1 > buts2:
                victoire += p
            elif buts1 == buts2:
                nul += p
            else:
                defaite += p

            if buts1 + buts2 >= 3:
                plus_25 += p

            if buts1 >= 1 and buts2 >= 1:
                deux_marquent += p

    total = victoire + nul + defaite

    if total <= 0:
        return None

    return {
        "victoire": victoire / total,
        "nul": nul / total,
        "defaite": defaite / total,
        "plus_25": plus_25,
        "deux_marquent": deux_marquent,
        "xg_dom": buts_attendus_dom,
        "xg_ext": buts_attendus_ext,
        "matchs_dom": dom_stats["joues"],
        "matchs_ext": ext_stats["joues"]
    }


# -------------------------------
# COMPETITIONS
# -------------------------------

competitions = charger_competitions()

if not competitions:
    st.warning("Aucune compétition disponible.")
    st.stop()

valides = [c for c in competitions if c.get("code")]

if not valides:
    st.warning("Aucun code de compétition disponible.")
    st.stop()

options = {
    f"{c['name']} ({c.get('area', {}).get('name', 'Pays')})": c["code"]
    for c in valides
}

nom = st.selectbox("1. Choisir une compétition", list(options.keys()))
code = options[nom]


# -------------------------------
# DATES
# -------------------------------

col1, col2 = st.columns(2)

with col1:
    debut = st.date_input("Date de début", value=date.today())

with col2:
    fin = st.date_input(
        "Date de fin",
        value=date.today() + timedelta(days=7)
    )

if debut > fin:
    st.error("La date de début doit précéder la date de fin.")
    st.stop()


# -------------------------------
# MATCHS A ANALYSER
# -------------------------------

if st.button("🔎 Charger les matchs et analyser", type="primary"):
    with st.spinner("Chargement des matchs..."):
        matchs_futurs = charger_matchs(
            code, debut.isoformat(), fin.isoformat()
        )

    if not matchs_futurs:
        st.info("Aucun match reçu pour cette période.")
        st.stop()

    matchs_a_jouer = [
        m for m in matchs_futurs
        if m.get("status") in ("SCHEDULED", "TIMED")
    ]

    if not matchs_a_jouer:
        st.info("Aucun match à venir dans cette période.")
        st.stop()

    # Historique des six derniers mois précédant la date de début
    debut_historique = debut - timedelta(days=180)
    fin_historique = debut - timedelta(days=1)

    with st.spinner("Analyse de l'historique disponible..."):
        historique_brut = charger_matchs(
            code,
            debut_historique.isoformat(),
            fin_historique.isoformat()
        )

    historique = preparer_matchs(historique_brut)

    st.subheader(f"📊 Analyse : {nom}")
    st.write(f"Matchs à analyser : {len(matchs_a_jouer)}")
    st.write(f"Matchs historiques terminés disponibles : {len(historique)}")

    if historique.empty:
        st.warning(
            "Aucun historique terminé disponible pour cette période. "
            "Aucune probabilité ne sera inventée."
        )
        st.stop()

    resultats = []

    for match in matchs_a_jouer:
        dom = (match.get("homeTeam") or {}).get("name")
        ext = (match.get("awayTeam") or {}).get("name")

        if not dom or not ext:
            continue

        pred = calculer_probabilites(historique, dom, ext)

        if pred is None:
            resultats.append({
                "Date": match.get("utcDate", "")[:10],
                "Domicile": dom,
                "Extérieur": ext,
                "Analyse": "Historique insuffisant",
                "Victoire dom.": "—",
                "Nul": "—",
                "Victoire ext.": "—",
                "Plus de 2,5 buts": "—",
                "Deux équipes marquent": "—"
            })
            continue

        resultats.append({
            "Date": match.get("utcDate", "")[:10],
            "Domicile": dom,
            "Extérieur": ext,
            "Analyse": "Estimation statistique",
            "Victoire dom.": f"{pred['victoire']:.1%}",
            "Nul": f"{pred['nul']:.1%}",
            "Victoire ext.": f"{pred['defaite']:.1%}",
            "Plus de 2,5 buts": f"{pred['plus_25']:.1%}",
            "Deux équipes marquent": f"{pred['deux_marquent']:.1%}"
        })

    tableau = pd.DataFrame(resultats)
    st.dataframe(tableau, use_container_width=True, hide_index=True)

    st.download_button(
        "📥 Télécharger les analyses CSV",
        data=tableau.to_csv(index=False).encode("utf-8-sig"),
        file_name="analyses_football.csv",
        mime="text/csv"
    )

    st.warning(
        "Ces estimations reposent sur les matchs disponibles dans la "
        "compétition sélectionnée. Elles ne garantissent aucun gain. "
        "Le modèle ne tient pas encore compte des blessures, des compositions "
        "officielles, des cotes ni de la marge du bookmaker."
    )

st.divider()
st.caption("Football Analytics AI V2 — version statistique expérimentale")
