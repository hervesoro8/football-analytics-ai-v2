
import streamlit as st
import requests
import pandas as pd
from datetime import date, timedelta

# ----------------------------------
# CONFIGURATION DE L'APPLICATION
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
# RECUPERATION DU TOKEN SECRET
# ----------------------------------

try:
    TOKEN = st.secrets["FOOTBALL_DATA_TOKEN"]
except Exception:
    st.error(
        "Le token API est introuvable. "
        "Vérifie FOOTBALL_DATA_TOKEN dans les Secrets de Streamlit."
    )
    st.stop()

if not TOKEN or not TOKEN.strip():
    st.error("Le token API est vide. Vérifie les Secrets de Streamlit.")
    st.stop()

HEADERS = {"X-Auth-Token": TOKEN.strip()}


# ----------------------------------
# FONCTION POUR CONTACTER L'API
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

        if response.status_code == 400:
            st.error(
                "Erreur 400 : la demande a été refusée. "
                "Vérifie le token et les paramètres."
            )
        elif response.status_code == 401:
            st.error(
                "Erreur 401 : le token API n'est pas accepté. "
                "Vérifie FOOTBALL_DATA_TOKEN dans Streamlit Secrets."
            )
        elif response.status_code == 403:
            st.error(
                "Erreur 403 : ton compte n'a peut-être pas accès "
                "à cette compétition ou à cette fonctionnalité."
            )
        elif response.status_code == 429:
            st.warning(
                "Limite de requêtes atteinte. "
                "Attends un peu avant de réessayer."
            )
        else:
            st.error(f"Erreur API : code {response.status_code}.")

        return None

    except requests.exceptions.Timeout:
        st.error("La connexion a pris trop de temps. Réessaie.")
    except requests.exceptions.RequestException:
        st.error("Impossible de contacter le service de football.")
    except ValueError:
        st.error("La réponse du service est illisible.")

    return None


# ----------------------------------
# CHARGEMENT DES COMPETITIONS
# ----------------------------------

@st.cache_data(ttl=1800)
def charger_competitions():
    data = appeler_api("competitions")

    if not data:
        return []

    return data.get("competitions", [])


competitions = charger_competitions()

if not competitions:
    st.warning(
        "Aucune compétition reçue. Vérifie le token, "
        "les accès de ton compte et réessaie."
    )
    st.stop()

# ----------------------------------
# CHOIX DE LA COMPETITION
# ----------------------------------

competitions_valides = [
    c for c in competitions if c.get("code")
]

if not competitions_valides:
    st.warning("Aucune compétition avec un code disponible.")
    st.stop()

noms_competitions = {
    f"{c['name']} ({c.get('area', {}).get('name', 'Pays inconnu')})":
        c["code"]
    for c in competitions_valides
}

nom_choisi = st.selectbox(
    "1. Choisis une compétition",
    options=list(noms_competitions.keys())
)

code_competition = noms_competitions[nom_choisi]

# ----------------------------------
# CHOIX DES DATES
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

    with st.spinner("Recherche des matchs en cours..."):
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
        equipe_domicile = match.get("homeTeam") or {}
        equipe_exterieure = match.get("awayTeam") or {}
        score = match.get("score") or {}
        resultat = score.get("fullTime") or {}

        buts_domicile = resultat.get("home")
        buts_exterieur = resultat.get("away")

        if buts_domicile is None or buts_exterieur is None:
            score_affiche = "À jouer"
        else:
            score_affiche = (
                f"{buts_domicile} - {buts_exterieur}"
            )

        lignes.append({
            "Date": match.get("utcDate", "")[:10],
            "Domicile": equipe_domicile.get("name", "Inconnu"),
            "Score": score_affiche,
            "Extérieur": equipe_exterieure.get("name", "Inconnu"),
            "Statut": match.get("status", "Inconnu"),
            "Journée": match.get("matchday") or "-"
        })

    tableau = pd.DataFrame(lignes)

    st.subheader(f"📋 Matchs : {nom_choisi}")
    st.write(f"Nombre de matchs trouvés : {len(tableau)}")
    st.dataframe(tableau, use_container_width=True, hide_index=True)

    fichier_csv = tableau.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label="📥 Télécharger les matchs (CSV)",
        data=fichier_csv,
        file_name="matchs_football.csv",
        mime="text/csv"
    )

st.divider()
st.caption(
    "Les données dépendent des compétitions accessibles avec ton compte "
    "football-data.org. Les scores et résultats ne sont pas des prédictions."
)
