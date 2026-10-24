
import streamlit as st
import requests
from datetime import date, timedelta

st.set_page_config(
    page_title="Football Analytics AI V2",
    page_icon="⚽",
    layout="wide"
)

BASE_URL = "https://api.football-data.org/v4"
TIMEOUT = 20

st.title("⚽ Football Analytics AI V2")
st.caption("Les matchs à venir et les premières données d'analyse")

# Connexion API
try:
    token = str(st.secrets["FOOTBALL_DATA_TOKEN"]).strip()
except Exception:
    st.error(
        "Token introuvable. Vérifie FOOTBALL_DATA_TOKEN "
        "dans les Secrets de Streamlit."
    )
    st.stop()

HEADERS = {"X-Auth-Token": token}


def api_get(endpoint, params=None):
    try:
        response = requests.get(
            f"{BASE_URL}{endpoint}",
            headers=HEADERS,
            params=params,
            timeout=TIMEOUT
        )

        if response.status_code == 200:
            return response.json()

        if response.status_code == 403:
            st.error(
                "Accès refusé : cette donnée peut être limitée "
                "par ton abonnement football-data.org."
            )
        elif response.status_code == 429:
            st.warning(
                "Limite de requêtes atteinte. Réessaie plus tard."
            )
        elif response.status_code == 400:
            st.error("Requête refusée par l'API. Vérifie les paramètres.")
        else:
            st.error(f"Erreur API : HTTP {response.status_code}")

    except requests.exceptions.Timeout:
        st.error("Le serveur met trop de temps à répondre.")
    except requests.exceptions.RequestException:
        st.error("Connexion impossible. Vérifie Internet.")

    return None


# Période de recherche
aujourd_hui = date.today()
date_debut = st.date_input("Du", value=aujourd_hui)
date_fin = st.date_input(
    "Au",
    value=aujourd_hui + timedelta(days=7),
    min_value=date_debut
)

# Chargement des compétitions
with st.spinner("Chargement des compétitions..."):
    data = api_get("/competitions")

if not data:
    st.stop()

competitions = data.get("competitions", [])
competitions = sorted(
    competitions,
    key=lambda c: (
        c.get("name", ""),
        (c.get("area") or {}).get("name", "")
    )
)

if not competitions:
    st.warning("Aucune compétition disponible.")
    st.stop()

options = {"Toutes les compétitions": None}

for competition in competitions:
    code = competition.get("code")
    nom = competition.get("name", "Compétition inconnue")
    pays = (competition.get("area") or {}).get("name", "")
    label = f"{nom} — {pays}" if pays else nom

    if code:
        options[label] = code

choix = st.selectbox(
    "Choisis une compétition",
    list(options.keys())
)

if date_fin < date_debut:
    st.error("La date de fin doit être après la date de début.")
    st.stop()

params = {
    "dateFrom": date_debut.isoformat(),
    "dateTo": date_fin.isoformat()
}

# Récupération des matchs
with st.spinner("Recherche des matchs..."):
    code_competition = options[choix]

    if code_competition:
        resultats = api_get(
            f"/competitions/{code_competition}/matches",
            params=params
        )
    else:
        resultats = api_get("/matches", params=params)

if resultats is None:
    st.info(
        "Si l'accès est limité, choisis une compétition disponible "
        dans ton compte football-data.org."
    )
    st.stop()

matchs = resultats.get("matches", [])

# Ne conserver que les matchs qui n'ont pas encore commencé
matchs_a_venir = [
    match for match in matchs
    if match.get("status") in ("SCHEDULED", "TIMED")
]

matchs_a_venir.sort(key=lambda m: m.get("utcDate", ""))

st.divider()
col1, col2, col3 = st.columns(3)

col1.metric("Matchs trouvés", len(matchs))
col2.metric("À venir", len(matchs_a_venir))
col3.metric("Compétitions accessibles", len(competitions))

st.subheader("📅 Calendrier des matchs")

if not matchs_a_venir:
    st.info(
        "Aucun match à venir trouvé pour cette période. "
        "Essaie d'élargir les dates."
    )

for match in matchs_a_venir:
    competition = (match.get("competition") or {}).get(
        "name", "Compétition"
    )
    domicile = (match.get("homeTeam") or {}).get(
        "name", "Équipe domicile"
    )
    exterieur = (match.get("awayTeam") or {}).get(
        "name", "Équipe extérieure"
    )
    date_match = match.get("utcDate", "")
    jour = date_match[:10] if date_match else "Date inconnue"
    heure = date_match[11:16] if len(date_match) >= 16 else "--:--"

    with st.container(border=True):
        st.caption(f"{competition} · {jour} · {heure} UTC")
        st.markdown(f"### {domicile}  —  {exterieur}")
        st.caption("Match à venir · Aucun pronostic automatique pour le moment")

st.divider()
st.caption(
    "Football Analytics AI V2 · Les données dépendent des accès API. "
    "Les matchs affichés ne constituent pas des conseils de pari."
)
