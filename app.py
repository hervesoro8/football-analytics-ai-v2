
import math
from io import BytesIO

import pandas as pd
import requests
import streamlit as st


st.set_page_config(
    page_title="Football Analytics AI V2.2",
    page_icon="⚽",
    layout="wide",
)

st.title("⚽ Football Analytics AI V2.2")
st.write("Historique combiné, forme récente et probabilités estimées.")

LIGUES = {
    "Angleterre - Premier League": "E0",
    "Angleterre - Championship": "E1",
    "Allemagne - Bundesliga": "D1",
    "Italie - Serie A": "I1",
    "Espagne - La Liga": "SP1",
    "France - Ligue 1": "F1",
    "Pays-Bas - Eredivisie": "N1",
    "Portugal - Primeira Liga": "P1",
}

SAISONS = {
    "2026-2027": "2627",
    "2025-2026": "2526",
    "2024-2025": "2425",
}

SAISON_PRECEDENTE = {
    "2026-2027": "2025-2026",
    "2025-2026": "2024-2025",
    "2024-2025": None,
}


@st.cache_data(ttl=3600, show_spinner=False)
def charger_donnees(code_ligue, code_saison):
    url = (
        "https://www.football-data.co.uk/mmz4281/"
        + code_saison + "/" + code_ligue + ".csv"
    )

    reponse = requests.get(url, timeout=25)
    reponse.raise_for_status()

    donnees = pd.read_csv(
        BytesIO(reponse.content),
        encoding="latin1",
        on_bad_lines="skip",
    )

    obligatoires = ["HomeTeam", "AwayTeam", "FTHG", "FTAG"]
    if not all(c in donnees.columns for c in obligatoires):
        raise ValueError("Colonnes de résultats manquantes.")

    colonnes = obligatoires.copy()
    if "Date" in donnees.columns:
        colonnes.append("Date")

    donnees = donnees[colonnes].copy()
    donnees["FTHG"] = pd.to_numeric(donnees["FTHG"], errors="coerce")
    donnees["FTAG"] = pd.to_numeric(donnees["FTAG"], errors="coerce")
    donnees = donnees.dropna(subset=obligatoires).copy()
    donnees["FTHG"] = donnees["FTHG"].astype(int)
    donnees["FTAG"] = donnees["FTAG"].astype(int)

    if "Date" in donnees.columns:
        donnees["Date"] = pd.to_datetime(
            donnees["Date"], dayfirst=True, errors="coerce"
        )
    else:
        donnees["Date"] = pd.NaT

    donnees = donnees.sort_values(
        "Date", na_position="first"
    ).reset_index(drop=True)

    return donnees


def moyenne_buts(equipe, matchs):
    dom = matchs[matchs["HomeTeam"] == equipe]
    ext = matchs[matchs["AwayTeam"] == equipe]

    return {
        "dom": len(dom),
        "ext": len(ext),
        "buts_dom": dom["FTHG"].mean(),
        "encaisses_dom": dom["FTAG"].mean(),
        "buts_ext": ext["FTAG"].mean(),
        "encaisses_ext": ext["FTHG"].mean(),
    }


def derniers_matchs(equipe, matchs, nombre=5):
    dom = matchs[matchs["HomeTeam"] == equipe].copy()
    ext = matchs[matchs["AwayTeam"] == equipe].copy()

    dom["ButsPour"] = dom["FTHG"]
    dom["ButsContre"] = dom["FTAG"]
    dom["Lieu"] = "Domicile"

    ext["ButsPour"] = ext["FTAG"]
    ext["ButsContre"] = ext["FTHG"]
    ext["Lieu"] = "Extérieur"

    colonnes = [
        "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG",
        "ButsPour", "ButsContre", "Lieu"
    ]

    historique = pd.concat(
        [dom[colonnes], ext[colonnes]], ignore_index=True
    )

    historique = historique.dropna(subset=["ButsPour", "ButsContre"])
    historique = historique.sort_values(
        "Date", na_position="first"
    )

    return historique.tail(nombre).iloc[::-1].reset_index(drop=True)


def calculer_forme(equipe, matchs):
    recents = derniers_matchs(equipe, matchs, 5)

    if recents.empty:
        return None, recents

    stats = {
        "nombre": len(recents),
        "buts_pour": recents["ButsPour"].mean(),
        "buts_contre": recents["ButsContre"].mean(),
        "victoires": int(
            (recents["ButsPour"] > recents["ButsContre"]).sum()
        ),
        "nuls": int(
            (recents["ButsPour"] == recents["ButsContre"]).sum()
        ),
        "defaites": int(
            (recents["ButsPour"] < recents["ButsContre"]).sum()
        ),
    }

    return stats, recents


def poisson(k, moyenne):
    if moyenne <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-moyenne) * moyenne**k / math.factorial(k)


def analyser(equipe_dom, equipe_ext, historique, saison_courante):
    stats_dom = moyenne_buts(equipe_dom, historique)
    stats_ext = moyenne_buts(equipe_ext, historique)

    if stats_dom["dom"] < 5 or stats_ext["ext"] < 5:
        return None, (
            "Historique insuffisant : il faut au moins 5 matchs "
            "à domicile pour l'équipe qui reçoit et 5 matchs "
            "à l'extérieur pour l'équipe visiteuse."
        )

    moy_dom_ligue = historique["FTHG"].mean()
    moy_ext_ligue = historique["FTAG"].mean()

    if pd.isna(moy_dom_ligue) or pd.isna(moy_ext_ligue):
        return None, "Moyennes de buts indisponibles."

    # Prévision de référence fondée sur les données combinées.
    attaque_dom = stats_dom["buts_dom"] / max(moy_dom_ligue, 0.1)
    defense_ext = stats_ext["encaisses_ext"] / max(moy_dom_ligue, 0.1)
    attaque_ext = stats_ext["buts_ext"] / max(moy_ext_ligue, 0.1)
    defense_dom = stats_dom["encaisses_dom"] / max(moy_ext_ligue, 0.1)

    lambda_dom_hist = max(
        0.05, moy_dom_ligue * (attaque_dom + defense_ext) / 2
    )
    lambda_ext_hist = max(
        0.05, moy_ext_ligue * (attaque_ext + defense_dom) / 2
    )

    # La forme récente vient uniquement de la saison sélectionnée.
    forme_dom, recents_dom = calculer_forme(equipe_dom, saison_courante)
    forme_ext, recents_ext = calculer_forme(equipe_ext, saison_courante)

    lambda_dom = lambda_dom_hist
    lambda_ext = lambda_ext_hist
    forme_utilisee = False
    poids_forme = 0.30

    if (
        forme_dom is not None
        and forme_ext is not None
        and forme_dom["nombre"] >= 3
        and forme_ext["nombre"] >= 3
    ):
        recent_dom = (
            forme_dom["buts_pour"] + forme_ext["buts_contre"]
        ) / 2
        recent_ext = (
            forme_ext["buts_pour"] + forme_dom["buts_contre"]
        ) / 2

        lambda_dom = (
            (1 - poids_forme) * lambda_dom_hist
            + poids_forme * recent_dom
        )
        lambda_ext = (
            (1 - poids_forme) * lambda_ext_hist
            + poids_forme * recent_ext
        )

        lambda_dom = max(0.05, lambda_dom)
        lambda_ext = max(0.05, lambda_ext)
        forme_utilisee = True

    scores = []
    for buts_dom in range(11):
        for buts_ext in range(11):
            p = (
                poisson(buts_dom, lambda_dom)
                * poisson(buts_ext, lambda_ext)
            )
            scores.append((buts_dom, buts_ext, p))

    total = sum(p for _, _, p in scores)
    if total <= 0:
        return None, "Impossible de calculer les probabilités."

    scores = [(a, b, p / total) for a, b, p in scores]

    p1 = sum(p for a, b, p in scores if a > b)
    pn = sum(p for a, b, p in scores if a == b)
    p2 = sum(p for a, b, p in scores if a < b)
    over25 = sum(p for a, b, p in scores if a + b >= 3)
    btts = sum(p for a, b, p in scores if a >= 1 and b >= 1)

    return {
        "1": p1,
        "N": pn,
        "2": p2,
        "over25": over25,
        "under25": 1 - over25,
        "btts": btts,
        "lambda_dom": lambda_dom,
        "lambda_ext": lambda_ext,
        "forme_utilisee": forme_utilisee,
        "forme_dom": forme_dom,
        "forme_ext": forme_ext,
        "recents_dom": recents_dom,
        "recents_ext": recents_ext,
        "stats_dom": stats_dom,
        "stats_ext": stats_ext,
        "scores": sorted(scores, key=lambda x: x[2], reverse=True)[:5],
    }, None


st.subheader("1. Choisir les données")
col1, col2 = st.columns(2)

with col1:
    ligue = st.selectbox("Championnat", list(LIGUES.keys()))

with col2:
    saison = st.selectbox("Saison à analyser", list(SAISONS.keys()))

if st.button("🔄 Actualiser les données"):
    charger_donnees.clear()

try:
    with st.spinner("Chargement des résultats..."):
        matchs_saison = charger_donnees(
            LIGUES[ligue], SAISONS[saison]
        )

        saison_prec = SAISON_PRECEDENTE[saison]
        historique = matchs_saison.copy()

        if saison_prec:
            try:
                matchs_prec = charger_donnees(
                    LIGUES[ligue], SAISONS[saison_prec]
                )
                historique = pd.concat(
                    [matchs_prec, matchs_saison],
                    ignore_index=True,
                )
            except Exception:
                st.warning(
                    "La saison précédente n'a pas pu être chargée. "
                    "Les calculs utiliseront uniquement la saison choisie."
                )

except Exception as erreur:
    st.error("Impossible de charger les données historiques.")
    st.caption("Détail technique : " + str(erreur))
    st.stop()

if matchs_saison.empty:
    st.warning("Aucun résultat terminé dans la saison choisie.")
    st.stop()

st.success("Données chargées.")

c1, c2, c3 = st.columns(3)
c1.metric("Matchs de la saison", len(matchs_saison))
c2.metric(
    "Équipes trouvées",
    len(set(matchs_saison["HomeTeam"]) | set(matchs_saison["AwayTeam"]))
)
c3.metric("Matchs pour l'historique", len(historique))

dates = matchs_saison["Date"].dropna()
if not dates.empty:
    st.caption(
        "Saison sélectionnée : "
        + dates.min().strftime("%d/%m/%Y")
        + " au "
        + dates.max().strftime("%d/%m/%Y")
    )

st.caption(
    "Les moyennes de référence utilisent la saison sélectionnée "
    "et, si disponible, la saison précédente. La forme récente "
    "utilise uniquement la saison sélectionnée."
)

st.divider()
st.subheader("2. Analyser un match")

equipes = sorted(
    set(matchs_saison["HomeTeam"].dropna())
    | set(matchs_saison["AwayTeam"].dropna())
)

if len(equipes) < 2:
    st.warning("Pas assez d'équipes.")
    st.stop()

c1, c2 = st.columns(2)
with c1:
    equipe_dom = st.selectbox("Équipe à domicile", equipes, index=0)
with c2:
    equipe_ext = st.selectbox(
        "Équipe à l'extérieur", equipes,
        index=1 if len(equipes) > 1 else 0
    )

if equipe_dom == equipe_ext:
    st.warning("Choisis deux équipes différentes.")

elif st.button("📊 Calculer les probabilités", type="primary"):
    resultat, erreur = analyser(
        equipe_dom, equipe_ext, historique, matchs_saison
    )

    if erreur:
        st.warning(erreur)
    else:
        st.subheader("3. Probabilités estimées")
        c1, c2, c3 = st.columns(3)
        c1.metric("1 - Victoire domicile", f'{resultat["1"]:.1%}')
        c2.metric("N - Match nul", f'{resultat["N"]:.1%}')
        c3.metric("2 - Victoire extérieur", f'{resultat["2"]:.1%}')

        c1, c2, c3 = st.columns(3)
        c1.metric("Plus de 2,5 buts", f'{resultat["over25"]:.1%}')
        c2.metric("Moins de 2,5 buts", f'{resultat["under25"]:.1%}')
        c3.metric("Les deux équipes marquent", f'{resultat["btts"]:.1%}')

        st.subheader("4. Scores les plus probables")
        for a, b, p in resultat["scores"]:
            st.write(f"**{equipe_dom} {a} - {b} {equipe_ext}** — {p:.1%}")

        st.subheader("5. Forme récente de la saison sélectionnée")

        if resultat["forme_utilisee"]:
            st.success(
                "Forme récente intégrée à 30 % ; "
                "référence historique pondérée à 70 %."
            )
        else:
            st.warning(
                "Moins de 3 matchs disponibles pour au moins une équipe. "
                "La forme récente n'a pas été intégrée au calcul."
            )

        for equipe, cle_forme, cle_recents in [
            (equipe_dom, "forme_dom", "recents_dom"),
            (equipe_ext, "forme_ext", "recents_ext"),
        ]:
            st.markdown(f"**{equipe}**")
            forme = resultat[cle_forme]
            recents = resultat[cle_recents]

            if forme is None:
                st.write("Aucun résultat récent disponible.")
                continue

            st.write(
                f"Victoires : {forme['victoires']} | "
                f"Nuls : {forme['nuls']} | "
                f"Défaites : {forme['defaites']}"
            )
            st.write(
                f"Buts marqués par match : {forme['buts_pour']:.2f} | "
                f"Buts encaissés : {forme['buts_contre']:.2f}"
            )

            tableau = recents.copy()
            tableau["Match"] = (
                tableau["HomeTeam"] + " - " + tableau["AwayTeam"]
            )
            tableau["Score"] = (
                tableau["FTHG"].astype(str)
                + " - "
                + tableau["FTAG"].astype(str)
            )
            tableau["Date"] = tableau["Date"].apply(
                lambda d: d.strftime("%d/%m/%Y")
                if pd.notna(d) else "Date inconnue"
            )

            st.dataframe(
                tableau[["Date", "Match", "Score", "Lieu"]],
                hide_index=True,
                use_container_width=True,
            )

        st.subheader("6. Moyennes de référence")

        c1, c2 = st.columns(2)
        c1.markdown(f"**{equipe_dom} à domicile**")
        c1.write(f"Matchs dans l'historique : {resultat['stats_dom']['dom']}")
        c1.write(
            f"Buts marqués : {resultat['stats_dom']['buts_dom']:.2f} "
            "par match"
        )
        c1.write(
            f"Buts encaissés : {resultat['stats_dom']['encaisses_dom']:.2f} "
            "par match"
        )

        c2.markdown(f"**{equipe_ext} à l'extérieur**")
        c2.write(f"Matchs dans l'historique : {resultat['stats_ext']['ext']}")
        c2.write(
            f"Buts marqués : {resultat['stats_ext']['buts_ext']:.2f} "
            "par match"
        )
        c2.write(
            f"Buts encaissés : {resultat['stats_ext']['encaisses_ext']:.2f} "
            "par match"
        )

        st.subheader("7. Limites du modèle")
        st.info(
            "Les probabilités sont des estimations statistiques. "
            "Le modèle ne connaît pas automatiquement les blessures, "
            "les compositions, les suspensions ou les cotes. "
            "Une grande probabilité ne garantit pas un résultat."
        )

st.divider()
st.caption(
    "Football Analytics AI V2.2 | Données historiques Football-Data.co.uk"
)
