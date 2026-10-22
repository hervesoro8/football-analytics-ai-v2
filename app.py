
import streamlit as st
import math

st.set_page_config(
    page_title="Football Analytics AI V2",
    page_icon="⚽",
    layout="centered"
)

st.title("⚽ Football Analytics AI V2")
st.caption("Analyse statistique de football — version de démarrage")

st.info(
    "Cette première version permet d'explorer un modèle "
    "statistique simple. Elle ne garantit aucun résultat de pari."
)

st.header("1. Informations du match")

home_team = st.text_input("Équipe à domicile", "Côte d'Ivoire")
away_team = st.text_input("Équipe à l'extérieur", "Ghana")

st.header("2. Statistiques à saisir")

col1, col2 = st.columns(2)

with col1:
    home_goals = st.number_input(
        "Buts moyens à domicile",
        min_value=0.0,
        max_value=10.0,
        value=1.5,
        step=0.1
    )

with col2:
    away_goals = st.number_input(
        "Buts moyens à l'extérieur",
        min_value=0.0,
        max_value=10.0,
        value=1.0,
        step=0.1
    )

max_goals = st.slider(
    "Nombre maximal de buts calculés par équipe",
    min_value=5,
    max_value=10,
    value=7
)

def poisson_probability(goals, average):
    if average == 0:
        return 1.0 if goals == 0 else 0.0
    return (math.exp(-average) * average**goals) / math.factorial(goals)

if st.button("Analyser le match", type="primary"):
    if not home_team.strip() or not away_team.strip():
        st.error("Entre le nom des deux équipes.")
    else:
        home_win = 0.0
        draw = 0.0
        away_win = 0.0
        over_25 = 0.0
        total_probability = 0.0

        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                probability = (
                    poisson_probability(h, home_goals)
                    * poisson_probability(a, away_goals)
                )

                total_probability += probability

                if h > a:
                    home_win += probability
                elif h == a:
                    draw += probability
                else:
                    away_win += probability

                if h + a >= 3:
                    over_25 += probability

        if total_probability > 0:
            home_win /= total_probability
            draw /= total_probability
            away_win /= total_probability
            over_25 /= total_probability

        st.header("3. Résultats du modèle")

        results = {
            f"Victoire {home_team} (1)": home_win,
            "Match nul (N)": draw,
            f"Victoire {away_team} (2)": away_win,
            "Plus de 2,5 buts": over_25,
        }

        for label, probability in results.items():
            st.metric(label, f"{probability:.1%}")

        st.caption(
            "Estimations théoriques basées uniquement sur les moyennes "
            "de buts saisies. Ce ne sont pas des prédictions vérifiées "
            "à partir de données réelles."
        )
