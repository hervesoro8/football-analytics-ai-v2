
import streamlit as st
import requests
from datetime import date, timedelta

# -----------------------------
# 1. CONFIGURATION
# -----------------------------
st.set_page_config(
    page_title="Football Analytics AI V2",
    page_icon="⚽",
    layout="wide"
)

BASE_URL = "https://api.football-data.org/v4"
TIMEOUT = 20

st.title("⚽ Football Analytics AI V2")
st.write("Consulte les matchs de football à venir.")

# -----------------------------
# 2. CONNEXION A L'API
# -----------------------------
try:
    token = str(st.secrets["FOOTBALL_DATA_TOKEN"]).strip()
except Exception:
    st.error("Le secret FOOTBALL_DATA_TOKEN est introuvable dans Streamlit.")
    st.stop()

if not token:
    st.error("Le token API est vide. Vérifie les Secrets de Streamlit.")
    st.stop()

HEADERS = {"X-Auth-Token": token}


def api_get(endpoint, params=None):
    """Interroge l'API et retourne les données reçues."""
    try:
        response = requests.get(
            BASE_URL + endpoint,
            headers=HEADERS,
            params=params,
            timeout=TIMEOUT
        )

        if response.status_code == 200:
            return response.json()

        if response.status_code == 400:
            st.error("Requête incorrecte envoyée à l'API.")
        elif response.status_code == 401:
            st.error("Token refusé. Vérifie le secret dans Streamlit.")
        elif response.status_code == 403:
            st.error("Accès refusé pour cette donnée ou compétition.")
        elif response.status_code == 429:
            st.warning("Limite de requêtes atteinte. Réessaie plus tard.")
        else:
            st.error("Erreur de l'API : HTTP " + str(response.status_code))

        return None

    except requests.exceptions.Timeout:
        st.error("Le serveur met trop de temps à répondre.")
    except requests.exceptions.RequestException:
        st.error("Connexion impossible. Vérifie Internet.")

    return None


# -----------------------------
# 3. CHOIX DES DATES
# -----------------------------
aujourd_hui = date.today()

colonne1, colonne2 = st.columns(2)

with colonne1:
    date_debut = st.date_input(
        "Date de début",
        value=aujourd_hui
    )

with colonne2:
    date_fin = st.date_input(
        "Date de fin",
        value=aujourd_hui + timedelta(days=7)
    )

if date_fin < date_debut:
    st.error("La date de fin doit être égale ou postérieure à la date de début.")
    st.stop()

# -----------------------------
# 4. CHARGEMENT DES COMPETITIONS
# -----------------------------
with st.spinner("Chargement des compétitions..."):
    donnees_competitions = api_get("/competitions")

if donnees_competitions is None:
    st.warning("Impossible de charger les compétitions.")
    st.stop()

competitions = donnees_competitions.get("competitions", [])

options_competitions = {"Toutes les compétitions accessibles": ""}

for competition in competitions:
    code = competition.get("code")
    nom = competition.get("name", "Compétition inconnue")
    pays = (competition.get("area") or {}).get("name", "")

    if code:
        if pays:
            libelle = nom + " - " + pays
        else:
            libelle = nom

        options_competitions[libelle] = code

if len(options_competitions) == 1:
    st.warning("Aucune compétition exploitable n'a été trouvée.")
    st.stop()

choix_competition = st.selectbox(
    "Choisir une compétition",
    list(options_competitions.keys())
)

code_competition = options_competitions[choix_competition]

# -----------------------------
# 5. RECHERCHE DES MATCHS
# -----------------------------
parametres = {
    "dateFrom": date_debut.isoformat(),
    "dateTo": date_fin.isoformat()
}

if code_competition:
    endpoint_matchs = "/competitions/" + code_competition + "/matches"
else:
    endpoint_matchs = "/matches"

with st.spinner("Recherche des matchs..."):
    donnees_matchs = api_get(endpoint_matchs, parametres)

if donnees_matchs is None:
    st.info("Essaie une autre compétition ou une autre période.")
    st.stop()

matchs = donnees_matchs.get("matches", [])

matchs_a_venir = []

for match in matchs:
    statut = match.get("status", "")

    if statut in ["SCHEDULED", "TIMED"]:
        matchs_a_venir.append(match)

matchs_a_venir.sort(key=lambda match: match.get("utcDate", ""))

# -----------------------------
# 6. RESUME
# -----------------------------
st.divider()

colonne1, colonne2, colonne3 = st.columns(3)

colonne1.metric("Matchs trouvés", len(matchs))
colonne2.metric("Matchs à venir", len(matchs_a_venir))
colonne3.metric("Compétitions accessibles", len(competitions))

# -----------------------------
# 7. AFFICHAGE DES MATCHS
# -----------------------------
st.subheader("📅 Calendrier des matchs")

if not matchs_a_venir:
    st.info("Aucun match à venir trouvé pour ces dates.")
else:
    for match in matchs_a_venir:
        competition = (match.get("competition") or {}).get(
            "name", "Compétition inconnue"
        )

        equipe_domicile = (match.get("homeTeam") or {}).get(
            "name", "Équipe inconnue"
        )

        equipe_exterieure = (match.get("awayTeam") or {}).get(
            "name", "Équipe inconnue"
        )

        date_utc = match.get("utcDate", "")

        if date_utc:
            date_affichee = date_utc[:10]
            heure_affichee = date_utc[11:16] + " UTC"
        else:
            date_affichee = "Date inconnue"
            heure_affichee = "Heure inconnue"

        with st.container(border=True):
            st.caption(
                competition + " | " + date_affichee + " | " + heure_affichee
            )

            st.markdown(
                "**" + equipe_domicile + " - " + equipe_exterieure + "**"
            )

            st.caption("Match à venir")

# -----------------------------
# 8. FIN DE PAGE
# -----------------------------
st.divider()

st.caption(
    "Football Analytics AI V2 | Données fournies par football-data.org"
)

st.caption(
    "Les matchs et les données dépendent des compétitions accessibles "
    avec ton compte API. Aucun pari n'est garanti."
)
