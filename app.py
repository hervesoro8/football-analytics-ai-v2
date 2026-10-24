
import streamlit as st
import requests
import pandas as pd
from datetime import date, timedelta

# ----------------------------------
# CONFIGURATION
# ----------------------------------

st.set_page_config(
    page_title="Football Analytics AI V2",
    page_icon="⚽",
    layout="wide"
)

BASE_URL = "https://api.football-data.org/v4"
TIMEOUT = 20

st.title("⚽ Football Analytics AI V2")
st.caption("Matchs, résultats et statistiques du football")


# ----------------------------------
# TOKEN SECRET
# ----------------------------------

try:
    TOKEN = st.secrets["FOOTBALL_DATA_TOKEN"]
except Exception:
    st.error(
        "Token introuvable. Vérifie FOOTBALL_DATA_TOKEN "
        "dans les Secrets de Streamlit."
    )
    st.stop()

if not TOKEN or not TOKEN.strip():
    st.error("Le token API est vide. Vérifie les Secrets.")
    st.stop()

HEADERS = {"X-Auth-Token": TOKEN.strip()}


# ----------------------------------
# FONCTION API
# ----------------------------------

def appeler_api(endpoint, params=None):
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            params=params,
            timeout=TIMEOUT
        )

        if response.status_code == 200:
            return response.json()

        elif response.status_code == 400:
            st.error("Erreur 400 : réponse exacte du serveur :")
            st.code(response.text[:500])

        elif response.status_code == 401:
            st.error("Erreur 401 : token non accepté.")
            st.code(response.text[:500])

        elif response.status_code == 403:
            st.error("Erreur 403 : accès refusé pour cette demande.")
            st.code(response.text[:500])

        elif response.status_code == 429:
            st.warning("Trop de requêtes. Attends un peu.")
            st.code(response.text[:500])

        else:
            st.error(f"Erreur API : code {response.status_code}.")
            st.code(response.text[:500])

        return None

    except requests.exceptions.Timeout:
        st.error("La connexion a pris trop de temps. Réessaie.")
    except requests.exceptions.RequestException as erreur:
        st.error("Impossible de contacter le service de football.")
        st.code(str(erreur))
    except ValueError:
        st.error("La réponse du serveur est illisible.")

    return None


# ----------------------------------
# CHARGEMENT DES COMPETITIONS
# ----------------------------------

@st.cache_data(ttl=1800)
def charger_competitions():
    data = appeler_api("competitions")

    if data is None:
        return None

    return data.get("competitions", [])


competitions = charger_competitions()

if competitions is None:
    st.warning(
        "Impossible de charger les compétitions. "
        "Lis le message d'erreur affiché au-dessus."
    )
    st.stop()

if not competitions:
    st.warning(
        "Aucune compétition disponible pour ce compte. "
        "Vérifie les accès de ton compte API."
    )
    st.stop()


# ----------------------------------
# CHOIX DE LA COMPETITION
# ----------------------------------

competitions_valides = [
    competition
    for competition in competitions
    if competition.get("code")
]

if not competitions_valides:
    st.warning("Aucune compétition avec un code disponible.")
    st.stop()

noms_competitions = {
    (
        f"{competition['name']} "
        f"({competition.get('area', {}).get('name', 'Pays inconnu')})"
    ): competition["code"]
    for competition in competitions_valides
}

nom_choisi = st.selectbox(
    "1. Choisis une compétition",
    options=list(noms_competitions.keys())
)

code_competition = noms_competitions[nom_choisi]


# ----------------------------------
# DATES DES MATCHS
# ----------------------------------

col1, col2 = st.columns(2)

with col1:
    date_debut = st.date_input(
        "Date de début",
        value=date.today()
    )

with col2:
    date_fin = st.date_input(
        "Date de fin",
        value=date.today() + timedelta(days=7)
    )


# ----------------------------------
# RECHERCHE DES MATCHS
# ----------------------------------

if st.button("🔎 Rechercher les matchs", type="primary"):

    if date_debut > date_fin:
        st.error("La date de début doit précéder la date de fin.")
        st.stop()

    with st.spinner("Recherche des matchs..."):
        donnees = appeler_api(
            f"competitions/{code_competition}/matches",
            params={
                "dateFrom": date_debut.isoformat(),
                "dateTo": date_fin.isoformat()
            }
        )

    if donnees is None:
        st.stop()

    matchs = donnees.get("matches", [])

    if not matchs:
        st.info(
            "Aucun match trouvé pour cette période. "
            "Essaie d'autres dates ou une autre compétition."
        )
        st.stop()

    lignes = []

    for match in matchs:
        domicile = match.get("homeTeam") or {}
        exterieur = match.get("awayTeam") or {}
        score = match.get("score") or {}
        score_final = score.get("fullTime") or {}

        buts_dom = score_final.get("home")
        buts_ext = score_final.get("away")

        if buts_dom is None or buts_ext is None:
            score_affiche = "À jouer"
        else:
            score_affiche = f"{buts_dom} - {buts_ext}"

        lignes.append({
            "Date": match.get("utcDate", "")[:10],
            "Domicile": domicile.get("name", "Inconnu"),
            "Score": score_affiche,
            "Extérieur": exterieur.get("name", "Inconnu"),
            "Statut": match.get("status", "Inconnu"),
            "Journée": match.get("matchday") or "-"
        })

    tableau = pd.DataFrame(lignes)

    st.subheader(f"📋 Matchs : {nom_choisi}")
    st.write(f"Nombre de matchs : {len(tableau)}")
    st.dataframe(
        tableau,
        use_container_width=True,
        hide_index=True
    )

    fichier_csv = tableau.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label="📥 Télécharger les matchs (CSV)",
        data=fichier_csv,
        file_name="matchs_football.csv",
        mime="text/csv"
    )


# ----------------------------------
# PIED DE PAGE
# ----------------------------------

st.divider()
st.caption(
    "Les données dépendent des compétitions accessibles "
    "avec ton compte football-data.org. "
    "Les résultats affichés ne sont pas des prédictions."
)
