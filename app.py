
import streamlit as st
import requests
from datetime import date, timedelta
import math

st.set_page_config(page_title="Football Analytics AI V2", page_icon="⚽")
st.title("⚽ Football Analytics AI V2")
st.caption("Matchs, résultats et analyse statistique")

try:
    TOKEN = st.secrets["FOOTBALL_DATA_TOKEN"]
except Exception:
    st.error("Clé API absente. Configure FOOTBALL_DATA_TOKEN dans les secrets Streamlit.")
    st.stop()

BASE = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": TOKEN}

def api_get(path, params=None):
    try:
        response = requests.get(
            BASE + path,
            headers=HEADERS,
            params=params,
            timeout=20
        )
        if response.status_code == 403:
            st.error("Accès refusé. Vérifie les compétitions autorisées par ton offre gratuite.")
            return None
        if response.status_code == 429:
            st.error("Limite de requêtes atteinte. Réessaie plus tard.")
            return None
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Erreur de connexion : {e}")
        return None

@st.cache_data(ttl=1800)
def get_competitions():
    data = api_get("/competitions")
    return data.get("competitions", []) if data else []

def get_recent(team_id):
    data = api_get(
        f"/teams/{team_id}/matches",
        {"status": "FINISHED", "limit": 5}
    )
    return data.get("matches", []) if data else []

def goals_summary(matches, team_id):
    scored = []
    conceded = []
    for match in matches:
        home = match.get("homeTeam", {}).get("id")
        away = match.get("awayTeam", {}).get("id")
        score = match.get("score", {}).get("fullTime", {})
        hg, ag = score.get("home"), score.get("away")
        if hg is None or ag is None:
            continue
        if home == team_id:
            scored.append(hg)
            conceded.append(ag)
        elif away == team_id:
            scored.append(ag)
            conceded.append(hg)
    if not scored:
        return None
    return sum(scored) / len(scored), sum(conceded) / len(conceded)

def poisson(lam, k):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

competitions = get_competitions()

if not competitions:
    st.warning("Aucune compétition reçue. Vérifie ta clé API et ton accès.")
    st.stop()

options = {
    f"{c['name']} ({c['code']})": c
    for c in competitions
    if c.get("code")
}

selected_name = st.selectbox("Choisir une compétition", list(options.keys()))
comp = options[selected_name]

match_date = st.date_input("Date des matchs", value=date.today())

if st.button("Rechercher les matchs", type="primary"):
    st.session_state["search_date"] = match_date
    st.session_state["search_comp"] = comp["code"]

if "search_date" in st.session_state:
    day = st.session_state["search_date"]
    code = st.session_state["search_comp"]

    data = api_get(
        f"/competitions/{code}/matches",
        {"dateFrom": day.isoformat(), "dateTo": day.isoformat()}
    )

    matches = data.get("matches", []) if data else []

    if not matches:
        st.info("Aucun match trouvé pour cette compétition à cette date.")
    else:
        labels = {}
        for m in matches:
            home = m.get("homeTeam", {}).get("name", "Équipe domicile")
            away = m.get("awayTeam", {}).get("name", "Équipe extérieure")
            labels[f"{home} - {away} ({m.get('utcDate', '')[:10]})"] = m

        choice = st.selectbox("Choisir un match", list(labels.keys()))
        match = labels[choice]

        st.subheader(choice)
        st.write("Statut :", match.get("status", "Inconnu"))

        score = match.get("score", {}).get("fullTime", {})
        if score.get("home") is not None:
            st.metric("Score final", f"{score['home']} - {score['away']}")
        else:
            st.info("Le score n'est pas encore disponible.")

        home_team = match.get("homeTeam", {})
        away_team = match.get("awayTeam", {})

        st.subheader("Forme récente")
        cols = st.columns(2)

        for col, team in zip(cols, [home_team, away_team]):
            with col:
                st.write("**" + team.get("name", "Équipe") + "**")
                team_id = team.get("id")
                recent = get_recent(team_id) if team_id else []
                summary = goals_summary(recent, team_id) if team_id else None

                if summary:
                    avg_for, avg_against = summary
                    st.write(f"Buts marqués en moyenne : {avg_for:.2f}")
                    st.write(f"Buts encaissés en moyenne : {avg_against:.2f}")
                    st.write(f"Matchs analysés : {len(recent)}")
                else:
                    st.write("Pas assez de résultats disponibles.")

        home_id = home_team.get("id")
        away_id = away_team.get("id")
        home_recent = get_recent(home_id) if home_id else []
        away_recent = get_recent(away_id) if away_id else []
        hs = goals_summary(home_recent, home_id) if home_id else None
        aws = goals_summary(away_recent, away_id) if away_id else None

        if hs and aws:
            home_lambda = (hs[0] + aws[1]) / 2
            away_lambda = (aws[0] + hs[1]) / 2

            p_home = sum(
                poisson(home_lambda, i) * sum(poisson(away_lambda, j) for j in range(i))
                for i in range(1, 11)
            )
            p_draw = sum(
                poisson(home_lambda, i) * poisson(away_lambda, i)
                for i in range(10)
            )
            p_away = max(0, 1 - p_home - p_draw)

            st.subheader("Probabilités indicatives")
            st.write(f"Victoire domicile : {p_home * 100:.1f} %")
            st.write(f"Match nul : {p_draw * 100:.1f} %")
            st.write(f"Victoire extérieur : {p_away * 100:.1f} %")

            over25 = 1 - sum(
                poisson(home_lambda, i) * poisson(away_lambda, j)
                for i in range(3)
                for j in range(3 - i)
            )
            st.write(f"Plus de 2,5 buts : {over25 * 100:.1f} %")

            st.caption(
                "Estimations simplifiées à partir des résultats récents. "
                "Ce ne sont ni des certitudes ni des conseils de pari."
            )
