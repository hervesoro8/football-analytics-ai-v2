
import streamlit as st
import requests
import math
from datetime import date

st.set_page_config(
    page_title="Football Analytics AI V2",
    page_icon="⚽",
    layout="wide"
)

st.title("⚽ Football Analytics AI V2")
st.caption("Matchs, résultats et probabilités statistiques")

# Connexion sécurisée à football-data.org
try:
    TOKEN = st.secrets["FOOTBALL_DATA_TOKEN"]
except Exception:
    st.error(
        "Clé absente. Ajoute FOOTBALL_DATA_TOKEN "
        "dans les Secrets de Streamlit."
    )
    st.stop()

BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": TOKEN}
try:
    test = requests.get(
        f"{BASE_URL}/competitions",
        headers=HEADERS,
        timeout=15
    )
    st.write("TEST API :", test.status_code)

    if test.status_code != 200:
        st.write("Réponse :", test.text[:300])

except Exception as e:
    st.write("Erreur de connexion :", str(e))

def api_get(path, params=None):
    """Récupère les données et affiche les erreurs de l'API."""
    try:
        response = requests.get(
            BASE_URL + path,
            headers=HEADERS,
            params=params,
            timeout=20
        )

        if response.status_code != 200:
            st.error(
                f"Erreur API {response.status_code} : "
                f"{response.text[:1000]}"
            )
            return None

        return response.json()

    except requests.exceptions.RequestException as error:
        st.error(f"Erreur de connexion : {error}")
        return None

    except ValueError:
        st.error("Le serveur a renvoyé une réponse illisible.")
        return None


@st.cache_data(ttl=1800)
def get_competitions():
    result = api_get("/competitions")

    if result is None:
        return []

    return result.get("competitions", [])


def get_recent(team_id):
    result = api_get(
        f"/teams/{team_id}/matches",
        {"status": "FINISHED", "limit": 5}
    )

    if result is None:
        return []

    return result.get("matches", [])


def goals_summary(matches, team_id):
    scored = []
    conceded = []

    for match in matches:
        home_id = match.get("homeTeam", {}).get("id")
        away_id = match.get("awayTeam", {}).get("id")
        score = match.get("score", {}).get("fullTime", {})

        home_goals = score.get("home")
        away_goals = score.get("away")

        if home_goals is None or away_goals is None:
            continue

        if home_id == team_id:
            scored.append(home_goals)
            conceded.append(away_goals)

        elif away_id == team_id:
            scored.append(away_goals)
            conceded.append(home_goals)

    if not scored:
        return None

    return (
        sum(scored) / len(scored),
        sum(conceded) / len(conceded)
    )


def poisson(lam, goals):
    return math.exp(-lam) * (lam ** goals) / math.factorial(goals)


def calculate_probabilities(home_lambda, away_lambda):
    # Calcul sur les scores possibles de 0 à 10 buts
    home_win = 0.0
    draw = 0.0
    away_win = 0.0
    over_25 = 0.0
    total = 0.0

    for home_goals in range(11):
        p_home_goals = poisson(home_lambda, home_goals)

        for away_goals in range(11):
            p_away_goals = poisson(away_lambda, away_goals)
            probability = p_home_goals * p_away_goals

            total += probability

            if home_goals > away_goals:
                home_win += probability
            elif home_goals == away_goals:
                draw += probability
            else:
                away_win += probability

            if home_goals + away_goals > 2:
                over_25 += probability

    if total > 0:
        home_win /= total
        draw /= total
        away_win /= total
        over_25 /= total

    return home_win, draw, away_win, over_25


# Affichage des compétitions accessibles
st.subheader("1. Choisir une compétition")

competitions = get_competitions()

if not competitions:
    st.warning(
        "Aucune compétition reçue. Vérifie le message d'erreur "
        "ci-dessus, ta clé et les accès de ton offre."
    )
    st.stop()

available = {
    f"{item['name']} ({item['code']})": item
    for item in competitions
    if item.get("code")
}

if not available:
    st.warning("Aucune compétition utilisable n'a été reçue.")
    st.stop()

competition_name = st.selectbox(
    "Compétition",
    list(available.keys())
)

competition = available[competition_name]

match_date = st.date_input(
    "Date des matchs",
    value=date.today()
)

if st.button("Rechercher les matchs", type="primary"):
    st.session_state["selected_competition"] = competition["code"]
    st.session_state["selected_date"] = match_date

# Recherche et analyse
if "selected_competition" in st.session_state:
    code = st.session_state["selected_competition"]
    selected_date = st.session_state["selected_date"]

    result = api_get(
        f"/competitions/{code}/matches",
        {
            "dateFrom": selected_date.isoformat(),
            "dateTo": selected_date.isoformat()
        }
    )

    if result is not None:
        matches = result.get("matches", [])

        if not matches:
            st.info(
                "Aucun match trouvé à cette date. "
                "Essaie une autre date ou compétition."
            )
        else:
            match_options = {}

            for item in matches:
                home_name = item.get("homeTeam", {}).get(
                    "name", "Équipe domicile"
                )
                away_name = item.get("awayTeam", {}).get(
                    "name", "Équipe extérieure"
                )

                label = f"{home_name} - {away_name}"
                match_options[label] = item

            st.subheader("2. Choisir un match")

            match_label = st.selectbox(
                "Match",
                list(match_options.keys())
            )

            match = match_options[match_label]

            st.write("**Statut :**", match.get("status", "Inconnu"))

            score = match.get("score", {}).get("fullTime", {})
            home_score = score.get("home")
            away_score = score.get("away")

            if home_score is not None and away_score is not None:
                st.metric(
                    "Score final",
                    f"{home_score} - {away_score}"
                )
            else:
                st.info("Le score final n'est pas encore disponible.")

            home_team = match.get("homeTeam", {})
            away_team = match.get("awayTeam", {})

            home_id = home_team.get("id")
            away_id = away_team.get("id")

            st.subheader("3. Forme récente des équipes")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown(
                    f"**{home_team.get('name', 'Domicile')}**"
                )

                home_matches = get_recent(home_id) if home_id else []
                home_stats = (
                    goals_summary(home_matches, home_id)
                    if home_id else None
                )

                if home_stats:
                    st.write(
                        f"Buts marqués en moyenne : {home_stats[0]:.2f}"
                    )
                    st.write(
                        f"Buts encaissés en moyenne : {home_stats[1]:.2f}"
                    )
                else:
                    st.write("Statistiques récentes indisponibles.")

            with col2:
                st.markdown(
                    f"**{away_team.get('name', 'Extérieur')}**"
                )

                away_matches = get_recent(away_id) if away_id else []
                away_stats = (
                    goals_summary(away_matches, away_id)
                    if away_id else None
                )

                if away_stats:
                    st.write(
                        f"Buts marqués en moyenne : {away_stats[0]:.2f}"
                    )
                    st.write(
                        f"Buts encaissés en moyenne : {away_stats[1]:.2f}"
                    )
                else:
                    st.write("Statistiques récentes indisponibles.")

            # Estimation des probabilités
            if home_stats and away_stats:
                home_lambda = (
                    home_stats[0] + away_stats[1]
                ) / 2

                away_lambda = (
                    away_stats[0] + home_stats[1]
                ) / 2

                probabilities = calculate_probabilities(
                    home_lambda,
                    away_lambda
                )

                st.subheader("4. Probabilités indicatives")

                p_home, p_draw, p_away, p_over = probabilities

                c1, c2, c3 = st.columns(3)

                c1.metric("Victoire domicile", f"{p_home:.1%}")
                c2.metric("Match nul", f"{p_draw:.1%}")
                c3.metric("Victoire extérieur", f"{p_away:.1%}")

                st.metric("Plus de 2,5 buts", f"{p_over:.1%}")

                st.caption(
                    "Estimations mathématiques simplifiées à partir "
                    "des buts récents. Les résultats ne sont pas garantis. "
                    "Les données disponibles dépendent de l'offre API."
                )
            else:
                st.info(
                    "Les probabilités ne peuvent pas être calculées "
                    "sans les statistiques récentes des deux équipes."
                )
