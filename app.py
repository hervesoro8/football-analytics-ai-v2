
import streamlit as st
import requests
import math
from datetime import date, timedelta

st.set_page_config(page_title="Football Analytics AI V2", page_icon="⚽")
st.title("⚽ Football Analytics AI V2")
st.caption("Calendrier, forme récente et probabilités statistiques")

try:
    API_KEY = st.secrets["API_FOOTBALL_KEY"]
except Exception:
    st.error("Clé API absente. Vérifie les Secrets de Streamlit.")
    st.stop()

BASE = "https://v3.football.api-sports.io"

@st.cache_data(ttl=3600, show_spinner=False)
def api_get(endpoint, params_tuple):
    response = requests.get(
        BASE + "/" + endpoint,
        headers={"x-apisports-key": API_KEY},
        params=dict(params_tuple),
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise ValueError(str(payload["errors"]))
    return payload.get("response", [])

def fetch(endpoint, params):
    return api_get(endpoint, tuple(sorted(params.items())))

def recent_matches(team_id, league_id, season):
    return fetch("fixtures", {
        "team": team_id,
        "league": league_id,
        "season": season,
        "last": 5,
        "status": "FT",
    })

def poisson(k, mean):
    if mean <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-mean) * mean**k / math.factorial(k)

def probabilities(home_avg, away_avg):
    home = draw = away = over25 = 0.0
    limit = 10
    total = 0.0
    for h in range(limit + 1):
        for a in range(limit + 1):
            p = poisson(h, home_avg) * poisson(a, away_avg)
            total += p
            if h > a:
                home += p
            elif h == a:
                draw += p
            else:
                away += p
            if h + a >= 3:
                over25 += p
    if total:
        return [100 * x / total for x in (home, draw, away, over25)]
    return [0.0, 0.0, 0.0, 0.0]

def summarize(matches, team_id):
    scored = []
    conceded = []
    for match in matches:
        teams = match.get("teams", {})
        goals = match.get("goals", {})
        hg, ag = goals.get("home"), goals.get("away")
        if hg is None or ag is None:
            continue
        if teams.get("home", {}).get("id") == team_id:
            scored.append(hg)
            conceded.append(ag)
        else:
            scored.append(ag)
            conceded.append(hg)
    if not scored:
        return None
    return {
        "played": len(scored),
        "scored": sum(scored) / len(scored),
        "conceded": sum(conceded) / len(conceded),
    }

st.header("1. Calendrier")
match_date = st.date_input("Date des matchs", value=date.today())

if st.button("Charger les matchs", type="primary"):
    try:
        matches = fetch("fixtures", {"date": match_date.isoformat()})
        if not matches:
            st.warning("Aucun match trouvé pour cette date.")
        else:
            st.session_state["matches"] = matches
            st.success(f"{len(matches)} matchs trouvés.")
    except Exception as exc:
        st.error(f"Erreur API : {exc}")

matches = st.session_state.get("matches", [])

if matches:
    options = {}
    for m in matches:
        fx = m.get("fixture", {})
        teams = m.get("teams", {})
        league = m.get("league", {})
        home = teams.get("home", {})
        away = teams.get("away", {})
        hg, ag = m.get("goals", {}).get("home"), m.get("goals", {}).get("away")
        score = f"{hg}-{ag}" if hg is not None and ag is not None else "à jouer"
        label = (
            f"{home.get('name', '?')} - {away.get('name', '?')} "
            f"| {score} | {league.get('name', '?')}"
        )
        options[label] = m

    selected_label = st.selectbox("Choisir un match", list(options.keys()))
    selected = options[selected_label]

    fx = selected.get("fixture", {})
    league = selected.get("league", {})
    teams = selected.get("teams", {})
    home = teams.get("home", {})
    away = teams.get("away", {})
    league_id = league.get("id")
    season = league.get("season")
    home_id = home.get("id")
    away_id = away.get("id")

    st.header("2. Forme récente")
    st.caption(
        "Le modèle utilise les 5 derniers matchs terminés de chaque équipe "
        "dans la compétition sélectionnée."
    )

    if st.button("Analyser les équipes"):
        if not league_id or not season or not home_id or not away_id:
            st.error("Informations de compétition ou d'équipe indisponibles.")
        else:
            try:
                with st.spinner("Chargement des derniers matchs..."):
                    hm = recent_matches(home_id, league_id, season)
                    am = recent_matches(away_id, league_id, season)
                    hs = summarize(hm, home_id)
                    aws = summarize(am, away_id)

                if not hs or not aws:
                    st.warning(
                        "Historique insuffisant pour une ou deux équipes "
                        "dans cette compétition."
                    )
                else:
                    st.subheader(home.get("name", "Domicile"))
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Matchs", hs["played"])
                    c2.metric("Buts marqués/match", f'{hs["scored"]:.2f}')
                    c3.metric("Buts encaissés/match", f'{hs["conceded"]:.2f}')

                    st.subheader(away.get("name", "Extérieur"))
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Matchs", aws["played"])
                    c2.metric("Buts marqués/match", f'{aws["scored"]:.2f}')
                    c3.metric("Buts encaissés/match", f'{aws["conceded"]:.2f}')

                    # Estimation simple : attaque d'une équipe et défense adverse.
                    home_avg = max(
                        0.1, (hs["scored"] + aws["conceded"]) / 2 * 1.08
                    )
                    away_avg = max(
                        0.1, (aws["scored"] + hs["conceded"]) / 2
                    )
                    p1, pn, p2, over25 = probabilities(home_avg, away_avg)

                    st.header("3. Probabilités estimées")
                    st.caption(
                        "Modèle exploratoire non calibré, basé sur un petit "
                        "historique. Ce n'est pas une garantie de résultat."
                    )
                    st.metric(f'Victoire {home.get("name")}', f"{p1:.1f}%")
                    st.metric("Match nul", f"{pn:.1f}%")
                    st.metric(f'Victoire {away.get("name")}', f"{p2:.1f}%")
                    st.metric("Plus de 2,5 buts", f"{over25:.1f}%")

                    st.info(
                        "Ces estimations ne tiennent pas encore compte des "
                        "compositions, blessures, xG ou cotes des bookmakers."
                    )
            except Exception as exc:
                st.error(f"Impossible d'analyser ce match : {exc}")

st.divider()
st.caption("Football Analytics AI V2 — version expérimentale.")
