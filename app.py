
import math
from io import BytesIO

import pandas as pd
import requests
import streamlit as st


st.set_page_config(
    page_title="Football Analytics AI V2.1",
    page_icon="⚽",
    layout="wide",
)

st.title("⚽ Football Analytics AI V2.1")
st.write(
    "Analyse statistique du football : historique, "
    "forme récente et probabilités estimées."
)

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

    colonnes_requises = [
        "HomeTeam", "AwayTeam", "FTHG", "FTAG"
    ]

    if not all(c in donnees.columns for c in colonnes_requises):
        raise ValueError(
            "Le fichier ne contient pas les colonnes attendues."
        )

    colonnes = colonnes_requises.copy()
    if "Date" in donnees.columns:
        colonnes.append("Date")

    donnees = donnees[colonnes].copy()

    donnees["FTHG"] = pd.to_numeric(
        donnees["FTHG"], errors="coerce"
    )
    donnees["FTAG"] = pd.to_numeric(
        donnees["FTAG"], errors="coerce"
    )

    donnees = donnees.dropna(
        subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"]
    ).copy()

    donnees["FTHG"] = donnees["FTHG"].astype(int)
    donnees["FTAG"] = donnees["FTAG"].astype(int)

    if "Date" in donnees.columns:
        donnees["Date"] = pd.to_datetime(
            donnees["Date"],
            dayfirst=True,
            errors="coerce",
        )
        donnees = donnees.sort_values(
            "Date", na_position="first"
        ).reset_index(drop=True)
    else:
        donnees["Date"] = pd.NaT

    return donnees


def moyenne_buts(equipe, matchs):
    domicile = matchs[matchs["HomeTeam"] == equipe]
    exterieur = matchs[matchs["AwayTeam"] == equipe]

    return {
        "dom": len(domicile),
        "ext": len(exterieur),
        "buts_dom": domicile["FTHG"].mean(),
        "encaisses_dom": domicile["FTAG"].mean(),
        "buts_ext": exterieur["FTAG"].mean(),
        "encaisses_ext": exterieur["FTHG"].mean(),
    }


def derniers_matchs(equipe, matchs, nombre=5):
    domicile = matchs[matchs["HomeTeam"] == equipe].copy()
    exterieur = matchs[matchs["AwayTeam"] == equipe].copy()

    domicile["ButsPour"] = domicile["FTHG"]
    domicile["ButsContre"] = domicile["FTAG"]
    domicile["Lieu"] = "Domicile"

    exterieur["ButsPour"] = exterieur["FTAG"]
    exterieur["ButsContre"] = exterieur["FTHG"]
    exterieur["Lieu"] = "Extérieur"

    colonnes = [
        "Date", "HomeTeam", "AwayTeam",
        "ButsPour", "ButsContre", "Lieu"
    ]

    historique = pd.concat(
        [domicile[colonnes], exterieur[colonnes]],
        ignore_index=True,
    )

    if historique.empty:
        return historique

    # On utilise uniquement les dates disponibles.
    # Si une date manque, l'ordre du fichier est conservé.
    historique = historique.sort_values(
        "Date", na_position="first"
    )

    return historique.tail(nombre).iloc[::-1].reset_index(drop=True)


def calculer_forme(equipe, matchs, nombre=5):
    recents = derniers_matchs(equipe, matchs, nombre)

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


def analyser(equipe_dom, equipe_ext, matchs):
    stats_dom = moyenne_buts(equipe_dom, matchs)
    stats_ext = moyenne_buts(equipe_ext, matchs)

    if stats_dom["dom"] < 3 or stats_ext["ext"] < 3:
        return None, (
            "Historique insuffisant : il faut au moins "
            "3 matchs à domicile pour la première équipe "
            "et 3 matchs à l'extérieur pour la seconde."
        )

    moyenne_ligue_dom = matchs["FTHG"].mean()
    moyenne_ligue_ext = matchs["FTAG"].mean()

    if (
        pd.isna(moyenne_ligue_dom)
        or pd.isna(moyenne_ligue_ext)
    ):
        return None, "Les moyennes de buts ne sont pas disponibles."

    attaque_dom = stats_dom["buts_dom"] / max(moyenne_ligue_dom, 0.1)
    defense_ext = (
        stats_ext["encaisses_ext"] / max(moyenne_ligue_dom, 0.1)
    )

    attaque_ext = stats_ext["buts_ext"] / max(moyenne_ligue_ext, 0.1)
    defense_dom = (
        stats_dom["encaisses_dom"] / max(moyenne_ligue_ext, 0.1)
    )

    lambda_dom_historique = max(
        0.05,
        moyenne_ligue_dom * (attaque_dom + defense_ext) / 2,
    )

    lambda_ext_historique = max(
        0.05,
        moyenne_ligue_ext * (attaque_ext + defense_dom) / 2,
    )

    forme_dom, recents_dom = calculer_forme(equipe_dom, matchs)
    forme_ext, recents_ext = calculer_forme(equipe_ext, matchs)

    # Prévisions de forme récente :
    # attaque d'une équipe combinée aux buts encaissés par l'adversaire.
    lambda_dom = lambda_dom_historique
    lambda_ext = lambda_ext_historique
    poids_forme = 0.35

    forme_utilisee = False

    if (
        forme_dom is not None
        and forme_ext is not None
        and forme_dom["nombre"] >= 3
        and forme_ext["nombre"] >= 3
    ):
        lambda_dom_recent = (
            forme_dom["buts_pour"] + forme_ext["buts_contre"]
        ) / 2

        lambda_ext_recent = (
            forme_ext["buts_pour"] + forme_dom["buts_contre"]
        ) / 2

        lambda_dom = (
            (1 - poids_forme) * lambda_dom_historique
            + poids_forme * lambda_dom_recent
        )

        lambda_ext = (
            (1 - poids_forme) * lambda_ext_historique
            + poids_forme * lambda_ext_recent
        )

        lambda_dom = max(0.05, lambda_dom)
        lambda_ext = max(0.05, lambda_ext)
        forme_utilisee = True

    scores = []

    for buts_dom in range(11):
        for buts_ext in range(11):
            probabilite = (
                poisson(buts_dom, lambda_dom)
                * poisson(buts_ext, lambda_ext)
            )
            scores.append((buts_dom, buts_ext, probabilite))

    total = sum(p for _, _, p in scores)

    if total <= 0:
        return None, "Impossible de calculer les probabilités."

    scores = [
        (a, b, p / total)
        for a, b, p in scores
    ]

    p1 = sum(p for a, b, p in scores if a > b)
    pn = sum(p for a, b, p in scores if a == b)
    p2 = sum(p for a, b, p in scores if a < b)

    over25 = sum(
        p for a, b, p in scores if a + b >= 3
    )

    btts = sum(
        p for a, b, p in scores if a >= 1 and b >= 1
    )

    return {
        "1": p1,
        "N": pn,
        "2": p2,
        "over25": over25,
        "under25": 1 - over25,
        "btts": btts,
        "lambda_dom": lambda_dom,
        "lambda_ext": lambda_ext,
        "lambda_dom_historique": lambda_dom_historique,
        "lambda_ext_historique": lambda_ext_historique,
        "forme_utilisee": forme_utilisee,
        "forme_dom": forme_dom,
        "forme_ext": forme_ext,
        "recents_dom": recents_dom,
        "recents_ext": recents_ext,
        "scores": sorted(
            scores, key=lambda x: x[2], reverse=True
        )[:5],
        "stats_dom": stats_dom,
        "stats_ext": stats_ext,
    }, None


st.divider()
st.subheader("1. Choisir les données")

col1, col2 = st.columns(2)

with col1:
    ligue = st.selectbox("Championnat", list(LIGUES.keys()))

with col2:
    saison = st.selectbox(
        "Saison historique", list(SAISONS.keys())
    )

if st.button("📥 Actualiser les résultats"):
    charger_donnees.clear()

try:
    with st.spinner("Chargement des résultats historiques..."):
        matchs = charger_donnees(
            LIGUES[ligue],
            SAISONS[saison],
        )
except Exception as erreur:
    st.error(
        "Impossible de récupérer le fichier. "
        "Vérifie ta connexion ou essaie une autre saison."
    )
    st.caption("Détail technique : " + str(erreur))
    st.stop()

if matchs.empty:
    st.warning("Aucun résultat terminé disponible dans ce fichier.")
    st.stop()

st.success("Résultats historiques chargés.")

c1, c2, c3 = st.columns(3)
c1.metric("Matchs historiques", len(matchs))
c2.metric(
    "Équipes trouvées",
    len(set(matchs["HomeTeam"]) | set(matchs["AwayTeam"]))
)
c3.metric("Saison", saison)

dates_valides = matchs["Date"].dropna()
if not dates_valides.empty:
    st.caption(
        "Période couverte par les données : "
        f"{dates_valides.min().strftime('%d/%m/%Y')} "
        "au "
        f"{dates_valides.max().strftime('%d/%m/%Y')}."
    )
else:
    st.warning(
        "Les dates des matchs ne sont pas disponibles. "
        "La forme récente peut suivre l'ordre du fichier, "
        "sans garantie de chronologie."
    )

st.divider()
st.subheader("2. Analyser un match")

equipes = sorted(
    set(matchs["HomeTeam"].dropna())
    | set(matchs["AwayTeam"].dropna())
)

if len(equipes) < 2:
    st.warning("Pas assez d'équipes dans les données.")
    st.stop()

col1, col2 = st.columns(2)

with col1:
    equipe_dom = st.selectbox(
        "Équipe à domicile", equipes, index=0
    )

with col2:
    equipe_ext = st.selectbox(
        "Équipe à l'extérieur",
        equipes,
        index=1 if len(equipes) > 1 else 0,
    )

if equipe_dom == equipe_ext:
    st.warning("Choisis deux équipes différentes.")

elif st.button("📊 Calculer les probabilités", type="primary"):
    resultat, erreur = analyser(
        equipe_dom, equipe_ext, matchs
    )

    if erreur:
        st.warning(erreur)
    else:
        st.subheader("3. Probabilités estimées")

        c1, c2, c3 = st.columns(3)
        c1.metric(
            "1 - Victoire domicile",
            f'{resultat["1"]:.1%}'
        )
        c2.metric("N - Match nul", f'{resultat["N"]:.1%}')
        c3.metric(
            "2 - Victoire extérieur",
            f'{resultat["2"]:.1%}'
        )

        c1, c2, c3 = st.columns(3)
        c1.metric(
            "Plus de 2,5 buts",
            f'{resultat["over25"]:.1%}'
        )
        c2.metric(
            "Moins de 2,5 buts",
            f'{resultat["under25"]:.1%}'
        )
        c3.metric(
            "Les deux équipes marquent",
            f'{resultat["btts"]:.1%}'
        )

        st.subheader("4. Scores les plus probables")

        for buts_dom, buts_ext, proba in resultat["scores"]:
            st.write(
                f"**{equipe_dom} {buts_dom} - {buts_ext} "
                f"{equipe_ext}** — {proba:.1%}"
            )

        st.subheader("5. Forme récente : 5 derniers matchs")

        if resultat["forme_utilisee"]:
            st.success(
                "La forme récente a été intégrée au calcul "
                "avec une pondération de 35 %. Les statistiques "
                "historiques représentent les 65 % restants."
            )
        else:
            st.warning(
                "Forme récente insuffisante pour les deux équipes : "
                "les probabilités utilisent uniquement les moyennes "
                "historiques."
            )

        c1, c2 = st.columns(2)

        for colonne, equipe, cle_forme, cle_recents in [
            (
                c1, equipe_dom,
                "forme_dom", "recents_dom"
            ),
            (
                c2, equipe_ext,
                "forme_ext", "recents_ext"
            ),
        ]:
            colonne.markdown(f"**{equipe}**")
            forme = resultat[cle_forme]
            recents = resultat[cle_recents]

            if forme is None:
                colonne.write("Aucun résultat récent disponible.")
                continue

            colonne.write(
                f"Victoires : {forme['victoires']} | "
                f"Nuls : {forme['nuls']} | "
                f"Défaites : {forme['defaites']}"
            )
            colonne.write(
                f"Buts marqués par match : "
                f"{forme['buts_pour']:.2f}"
            )
            colonne.write(
                f"Buts encaissés par match : "
                f"{forme['buts_contre']:.2f}"
            )

            affichage = recents.copy()
            affichage["Match"] = (
                affichage["HomeTeam"]
                + " - "
                + affichage["AwayTeam"]
            )
            affichage["Score"] = (
                affichage["FTHG"].astype(int).astype(str)
                if "FTHG" in affichage.columns
                else ""
            )

            # Construire le tableau avec le score réel.
            affichage["Score"] = recents.apply(
                lambda ligne: (
                    f"{int(matchs.loc[ligne.name, 'FTHG'])} - "
                    f"{int(matchs.loc[ligne.name, 'FTAG'])}"
                ) if ligne.name in matchs.index else
                f"{int(ligne['ButsPour'])} - "
                f"{int(ligne['ButsContre'])}",
                axis=1,
            )

            affichage["Lieu"] = recents["Lieu"]
            affichage["Date"] = recents["Date"].apply(
                lambda d: d.strftime("%d/%m/%Y")
                if pd.notna(d) else "Date inconnue"
            )

            colonne.dataframe(
                affichage[["Date", "Match", "Score", "Lieu"]],
                hide_index=True,
                use_container_width=True,
            )

        st.subheader("6. Moyennes historiques utilisées")

        c1, c2 = st.columns(2)

        c1.markdown(f"**{equipe_dom} à domicile**")
        c1.write(f"Matchs : {resultat['stats_dom']['dom']}")
        c1.write(
            f"Buts marqués par match : "
            f"{resultat['stats_dom']['buts_dom']:.2f}"
        )
        c1.write(
            f"Buts encaissés par match : "
            f"{resultat['stats_dom']['encaisses_dom']:.2f}"
        )

        c2.markdown(f"**{equipe_ext} à l'extérieur**")
        c2.write(f"Matchs : {resultat['stats_ext']['ext']}")
        c2.write(
            f"Buts marqués par match : "
            f"{resultat['stats_ext']['buts_ext']:.2f}"
        )
        c2.write(
            f"Buts encaissés par match : "
            f"{resultat['stats_ext']['encaisses_ext']:.2f}"
        )

        st.subheader("7. Fiabilité et limites")

        st.write(
            "Le modèle utilise une loi de Poisson et des moyennes "
            "de buts historiques. Il ne prend pas en compte les "
            "blessures, les compositions, les cartons rouges, "
            "les changements d'entraîneur ni les cotes du marché."
        )

        st.info(
            "Les probabilités sont des estimations mathématiques, "
            "pas des garanties. Vérifie que la période des données "
            "correspond bien à la période que tu veux analyser."
        )

st.divider()
st.caption(
    "Football Analytics AI V2.1 | "
    "Données historiques Football-Data.co.uk | "
    "Aucun résultat n'est garanti."
)
