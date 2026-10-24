
import streamlit as st
import requests
from datetime import date, timedelta

st.set_page_config(
    page_title="Football Analytics AI V2",
    page_icon="⚽",
    layout="centered"
)

st.title("⚽ Football Analytics AI V2")
st.write("Calendrier et résultats du football en direct depuis API-Football.")

try:
    api_key = st.secrets["API_FOOTBALL_KEY"]
except Exception:
    api_key = ""

if not api_key:
    st.error("Clé API absente. Vérifie les Secrets de Streamlit.")
    st.stop()

BASE_URL = "https://v3.football.api-sports.io"

def api_get(endpoint, params=None):
    headers = {"x-apisports-key": api_key}
    response = requests.get(
        f"{BASE_URL}/{endpoint}",
        headers=headers,
        params=params or {},
        timeout=25
    )
    response.raise_for_status()
    data = response.json()

    if data.get("errors"):
        raise ValueError(str(data["errors"]))

    return data.get("response", [])

st.header("Rechercher les matchs")

match_date = st.date_input("Date des matchs", value=date.today())

if st.button("Charger les matchs", type="primary"):
    with st.spinner("Recherche des matchs en cours..."):
        try:
            matches = api_get(
                "fixtures",
                {"date": match_date.isoformat()}
            )

            if not matches:
                st.warning(
                    "Aucun match trouvé pour cette date "
                    "avec les données disponibles."
                )
            else:
                st.success(f"{len(matches)} match(s) trouvé(s).")

                for match in matches:
                    fixture = match.get("fixture", {})
                    teams = match.get("teams", {})
                    league = match.get("league", {})
                    goals = match.get("goals", {})

                    home = teams.get("home", {}).get("name", "?")
                    away = teams.get("away", {}).get("name", "?")
                    league_name = league.get("name", "Compétition")
                    country = league.get("country", "")
                    status = fixture.get("status", {}).get("long", "")
                    home_goals = goals.get("home")
                    away_goals = goals.get("away")

                    with st.container(border=True):
                        st.subheader(f"{home} - {away}")
                        st.caption(f"{league_name} · {country}")
                        if home_goals is not None and away_goals is not None:
                            st.write(
                                f"**Score : {home_goals} - {away_goals}**"
                            )
                        else:
                            st.write("Score : pas encore disponible")
                        st.caption(f"État du match : {status}")

            st.caption(
                "La couverture et les statistiques disponibles "
                "dépendent de la compétition et du forfait API."
            )

        except requests.exceptions.HTTPError as exc:
            st.error(f"Erreur HTTP de l'API : {exc}")
        except requests.exceptions.RequestException:
            st.error(
                "Impossible de contacter l'API. Vérifie ta connexion "
                "Internet et réessaie."
            )
        except Exception as exc:
            st.error(f"Erreur : {exc}")

st.divider()
st.caption(
    "Version initiale connectée aux données de calendrier. "
    "Les probabilités avancées seront ajoutées après vérification "
    "du bon fonctionnement de la connexion."
)
