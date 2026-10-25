
import math
from io import BytesIO

import pandas as pd
import requests
import streamlit as st


st.set_page_config(
    page_title="Football Analytics AI V2.3",
    page_icon="⚽",
    layout="wide",
)

st.title("⚽ Football Analytics AI V2.3")
st.write(
    "Analyse statistique des équipes, forme récente et "
    "probabilités estimées."
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

    if "Date" not in donnees.columns:
        donnees["Date"] = pd.NaT
    else:
        donnees["Date"] = pd.to_datetime(
            donnees["Date"], dayfirst=True, errors="coerce"
        )

    donnees["FTHG"] = pd.to_numeric(
        donnees["FTHG"], errors="coerce"
    )
    donnees["FTAG"] = pd.to_numeric(
        donnees["FTAG"], errors="coerce"
    )

    donnees = donnees.dropna(
        subset=obligatoires + ["Date"]
    ).copy()

    donnees["FTHG"] = donnees["FTHG"].astype(int)
    donnees["FTAG"] = donnees["FTAG"].astype(int)

    # Les rencontres sans date fiable sont exclues.
    donnees = donnees.sort_values("Date").reset_index(drop=True)

    return donnees




def poids_recence(matchs, demi_vie_jours=180, date_reference=None):
    """Donne plus de poids aux matchs récents."""
    if matchs.empty:
        return pd.Series(dtype=float, index=matchs.index)

    dates = pd.to_datetime(matchs["Date"], errors="coerce")

    if date_reference is None:
        date_reference = dates.max()
    else:
        date_reference = pd.Timestamp(date_reference)

    age_jours = (date_reference - dates).dt.days.clip(lower=0)

    return 0.5 ** (age_jours / demi_vie_jours)



def moyenne_ponderee(valeurs, poids):
    valeurs = pd.to_numeric(valeurs, errors="coerce")
    masque = valeurs.notna() & poids.notna()

    if not masque.any() or poids[masque].sum() <= 0:
        return float("nan")

    return float(
        (valeurs[masque] * poids[masque]).sum()
        / poids[masque].sum()
    )



def moyenne_buts(equipe, matchs, date_reference=None):
    dom = matchs[matchs["HomeTeam"] == equipe].copy()
    ext = matchs[matchs["AwayTeam"] == equipe].copy()

    poids_dom = poids_recence(
        dom, date_reference=date_reference
    )
    poids_ext = poids_recence(
        ext, date_reference=date_reference
    )

    return {
        "dom": len(dom),
        "ext": len(ext),
        "buts_dom": moyenne_ponderee(dom["FTHG"], poids_dom),
        "encaisses_dom": moyenne_ponderee(dom["FTAG"], poids_dom),
        "buts_ext": moyenne_ponderee(ext["FTAG"], poids_ext),
        "encaisses_ext": moyenne_ponderee(ext["FTHG"], poids_ext),
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
        "ButsPour", "ButsContre", "Lieu",
    ]

    historique = pd.concat(
        [dom[colonnes], ext[colonnes]], ignore_index=True
    )

    historique = historique.dropna(
        subset=["Date", "ButsPour", "ButsContre"]
    )

    historique = historique.sort_values(
        "Date", ascending=False
    )

    return historique.head(nombre).reset_index(drop=True)



def calculer_forme(equipe, matchs, date_reference=None, afficher_diagnostics=True):
    matchs_avant = matchs.copy()

    # Ne garder que les matchs antérieurs à la date de référence.
    if date_reference is not None:
        matchs_avant = matchs_avant[
            pd.to_datetime(matchs_avant["Date"], errors="coerce")
            < pd.Timestamp(date_reference)
        ].copy()

    recents = derniers_matchs(equipe, matchs_avant, 5)

    if recents.empty:
        return None, recents

    poids = poids_recence(recents, demi_vie_jours=60)

    if afficher_diagnostics:
        st.write("Diagnostic des pondérations")
        st.dataframe(
            recents[
                ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]
            ].assign(Poids=poids.values)
        )

    stats = {
        "nombre": len(recents),
        "buts_pour": moyenne_ponderee(recents["ButsPour"], poids),
        "buts_contre": moyenne_ponderee(recents["ButsContre"], poids),
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


def analyser(
    equipe_dom,
    equipe_ext,
    historique,
    saison_courante,
    afficher_diagnostics=True,
    minimum_matchs=5,
):
    
    date_reference = historique["Date"].max()

    stats_dom = moyenne_buts(
    equipe_dom, historique, date_reference
)
    stats_ext = moyenne_buts(
    equipe_ext, historique, date_reference
)


    if (
    stats_dom["dom"] < minimum_matchs
    or stats_ext["ext"] < minimum_matchs
):
        return None, (
            "Historique insuffisant : il faut au moins 5 matchs "
            "à domicile pour l'équipe qui reçoit et 5 matchs "
            "à l'extérieur pour l'équipe visiteuse."
        )

    
    poids_ligue = poids_recence(
    historique,
    date_reference=date_reference
)

    moy_dom_ligue = moyenne_ponderee(
    historique["FTHG"], poids_ligue
)

    moy_ext_ligue = moyenne_ponderee(
    historique["FTAG"], poids_ligue
)


    valeurs = [
        stats_dom["buts_dom"],
        stats_dom["encaisses_dom"],
        stats_ext["buts_ext"],
        stats_ext["encaisses_ext"],
        moy_dom_ligue,
        moy_ext_ligue,
    ]

    if any(pd.isna(v) for v in valeurs):
        return None, "Certaines moyennes sont indisponibles."

    # Estimation historique pondérée par la récence.
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

    forme_dom, recents_dom = calculer_forme(
    equipe_dom,
    saison_courante,
    date_reference=date_reference,
    afficher_diagnostics=afficher_diagnostics,
)

    forme_ext, recents_ext = calculer_forme(
    equipe_ext,
    saison_courante,
    date_reference=date_reference,
    afficher_diagnostics=afficher_diagnostics,
)
    if afficher_diagnostics:
         st.subheader("Vérification des 5 derniers matchs")
         st.write("Matchs de l'équipe à domicile")
         st.dataframe(recents_dom)
         st.write("Matchs de l'équipe à l'extérieur")
         st.dataframe(recents_ext)
    

    lambda_dom = lambda_dom_hist
    lambda_ext = lambda_ext_hist
    forme_utilisee = False

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

        # La forme récente compte pour 35 %.
        lambda_dom = 0.65 * lambda_dom_hist + 0.35 * recent_dom
        lambda_ext = 0.65 * lambda_ext_hist + 0.35 * recent_ext

        lambda_dom = max(0.05, min(lambda_dom, 5.0))
        lambda_ext = max(0.05, min(lambda_ext, 5.0))
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

    scores = [(a, b, p / total) for a, b, p in scores]

    p1 = sum(p for a, b, p in scores if a > b)
    pn = sum(p for a, b, p in scores if a == b)
    p2 = sum(p for a, b, p in scores if a < b)
    over25 = sum(p for a, b, p in scores if a + b >= 3)
    btts = sum(p for a, b, p in scores if a >= 1 and b >= 1)

    # Indicateur de quantité de données, pas une garantie d'exactitude.
    nombre_donnees = min(stats_dom["dom"], stats_ext["ext"])
    if nombre_donnees >= 15:
        fiabilite = "Historique fourni"
    elif nombre_donnees >= 8:
        fiabilite = "Historique moyen"
    else:
        fiabilite = "Historique limité"

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
        "fiabilite": fiabilite,
        "scores": sorted(scores, key=lambda x: x[2], reverse=True)[:5],
    }, None





def executer_backtest(matchs_saison, historique, minimum_matchs=5):
    resultats = []
    details_erreurs = []

    non_testes = {
        "historique_insuffisant": 0,
        "analyse_impossible": 0,
        "historique_equipes_insuffisant": 0,
        "donnees_manquantes": 0,
    }

    matchs_a_tester = (
        matchs_saison.sort_values("Date")
        .reset_index(drop=True)
    )

    historique = historique.copy()
    historique["Date"] = pd.to_datetime(
        historique["Date"], errors="coerce"
    )

    for _, match in matchs_a_tester.iterrows():
        date_match = pd.to_datetime(
            match["Date"], errors="coerce"
        )

        if pd.isna(date_match):
            non_testes["donnees_manquantes"] += 1
            continue

        if pd.isna(match["FTHG"]) or pd.isna(match["FTAG"]):
            non_testes["donnees_manquantes"] += 1
            continue

        # Utiliser uniquement les matchs antérieurs à celui prédit.
        historique_avant = historique[
            historique["Date"] < date_match
        ].copy()

        if historique_avant.empty:
            non_testes["historique_insuffisant"] += 1
            continue

        resultat, erreur = analyser(
            match["HomeTeam"],
            match["AwayTeam"],
            historique_avant,
            historique_avant,
            afficher_diagnostics=False,
            minimum_matchs=3,
        )

        if erreur or resultat is None:
            non_testes["analyse_impossible"] += 1
            details_erreurs.append({
                "Date": date_match,
                "Domicile": match["HomeTeam"],
                "Extérieur": match["AwayTeam"],
                "Erreur": str(erreur) if erreur else "Résultat vide",
            })
            continue

        stats_dom = resultat["stats_dom"]
        stats_ext = resultat["stats_ext"]

        if (
            stats_dom["dom"] < minimum_matchs
            or stats_ext["ext"] < minimum_matchs
        ):
            non_testes["historique_equipes_insuffisant"] += 1
            continue

        buts_dom = int(match["FTHG"])
        buts_ext = int(match["FTAG"])

        if buts_dom > buts_ext:
            issue_reelle = "1"
        elif buts_dom == buts_ext:
            issue_reelle = "N"
        else:
            issue_reelle = "2"

        # Référence simple : fréquences historiques avant le match.
        hist = historique_avant.dropna(
            subset=["FTHG", "FTAG"]
        ).copy()

        if hist.empty:
            non_testes["historique_insuffisant"] += 1
            continue

        victoires_dom = (hist["FTHG"] > hist["FTAG"]).sum()
        nuls = (hist["FTHG"] == hist["FTAG"]).sum()
        victoires_ext = (hist["FTHG"] < hist["FTAG"]).sum()

        # Lissage pour éviter les probabilités égales à zéro.
        n_hist = len(hist)
        ref_1 = (victoires_dom + 1) / (n_hist + 3)
        ref_n = (nuls + 1) / (n_hist + 3)
        ref_2 = (victoires_ext + 1) / (n_hist + 3)

        prediction_ref = max(
            [("1", ref_1), ("N", ref_n), ("2", ref_2)],
            key=lambda element: element[1],
        )[0]

        y1 = 1 if issue_reelle == "1" else 0
        yn = 1 if issue_reelle == "N" else 0
        y2 = 1 if issue_reelle == "2" else 0

        brier_ref = (
            (ref_1 - y1) ** 2
            + (ref_n - yn) ** 2
            + (ref_2 - y2) ** 2
        )

        epsilon = 1e-15
        prob_ref_reelle = {
            "1": ref_1,
            "N": ref_n,
            "2": ref_2,
        }[issue_reelle]

        log_loss_ref = -math.log(
            max(epsilon, prob_ref_reelle)
        )

        # Les probabilités affichées par l'application sont en pourcentage.
        p1 = float(resultat["1"]) / 100
        pn = float(resultat["N"]) / 100
        p2 = float(resultat["2"]) / 100

        # Vérifier que les probabilités sont utilisables.
        probabilites = [p1, pn, p2]

        if (
            any(not math.isfinite(p) or p < 0 or p > 1
                for p in probabilites)
            or sum(probabilites) <= 0
        ):
            non_testes["analyse_impossible"] += 1
            continue

        # Normaliser pour que les trois probabilités totalisent 1.
        total = sum(probabilites)
        p1, pn, p2 = [p / total for p in probabilites]

        prediction = max(
            ["1", "N", "2"],
            key=lambda cle: resultat[cle],
        )

        y1 = 1 if issue_reelle == "1" else 0
        yn = 1 if issue_reelle == "N" else 0
        y2 = 1 if issue_reelle == "2" else 0

        # Score de Brier multicatégorie : plus bas = meilleur.
        brier = (
            (p1 - y1) ** 2
            + (pn - yn) ** 2
            + (p2 - y2) ** 2
        )

        # Log loss : plus bas = meilleur.
        epsilon = 1e-15
        probabilite_issue_reelle = {
            "1": p1,
            "N": pn,
            "2": p2,
        }[issue_reelle]

        log_loss = -math.log(
            max(epsilon, probabilite_issue_reelle)
        )

        resultats.append({
            "Date": date_match,
            "Domicile": match["HomeTeam"],
            "Extérieur": match["AwayTeam"],
            "Score réel": f"{buts_dom}-{buts_ext}",
            "Issue réelle": issue_reelle,
            "Prédiction": prediction,
            "Probabilité 1 (%)": round(p1 * 100, 1),
            "Probabilité N (%)": round(pn * 100, 1),
            "Probabilité 2 (%)": round(p2 * 100, 1),
            "Correct": prediction == issue_reelle,
            "Brier": brier,
            "Log loss": log_loss,
        })

    df_resultats = pd.DataFrame(resultats)

    st.write("### Diagnostic du backtest")
    st.write("Matchs examinés :", len(matchs_a_tester))
    st.write("Matchs testés :", len(df_resultats))

    st.write(
        "Exclus — historique vide :",
        non_testes["historique_insuffisant"],
    )
    st.write(
        "Exclus — analyse impossible :",
        non_testes["analyse_impossible"],
    )
    st.write(
        "Exclus — historique des équipes insuffisant :",
        non_testes["historique_equipes_insuffisant"],
    )
    st.write(
        "Exclus — date ou score manquant :",
        non_testes["donnees_manquantes"],
    )

    if details_erreurs:
        st.write("### Détail des erreurs d'analyse")
        st.dataframe(
            pd.DataFrame(details_erreurs).head(10),
            hide_index=True,
            use_container_width=True,
        )

    if not df_resultats.empty:
        taux_reussite = df_resultats["Correct"].mean() * 100
        score_brier = df_resultats["Brier"].mean()
        score_log_loss = df_resultats["Log loss"].mean()

        st.write("### Mesure des performances")
        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Bonnes prédictions 1N2",
            f"{taux_reussite:.1f} %",
        )
        col2.metric(
            "Score de Brier",
            f"{score_brier:.4f}",
        )
        col3.metric(
            "Log loss",
            f"{score_log_loss:.4f}",
        )

        st.caption(
            "Pour le Brier et le log loss, plus le score est bas, "
            "meilleure est la qualité probabiliste. Compare les scores "
            "sur les mêmes matchs et avec une référence simple."
        )

        st.write("### Détail des matchs testés")
        st.dataframe(
            df_resultats,
            hide_index=True,
            use_container_width=True,
        )

    return df_resultats




st.subheader("1. Choisir les données")
col1, col2 = st.columns(2)

with col1:
    ligue = st.selectbox("Championnat", list(LIGUES.keys()))

with col2:
    saison = st.selectbox("Saison à analyser", list(SAISONS.keys()))

if st.button("🔄 Actualiser les données"):
    charger_donnees.clear()

try:
    with st.spinner("Chargement des résultats historiques..."):
        matchs_saison = charger_donnees(
            LIGUES[ligue], SAISONS[saison]
        )

        historique = matchs_saison.copy()
        saison_prec = SAISON_PRECEDENTE[saison]

        if saison_prec:
            try:
                matchs_prec = charger_donnees(
                    LIGUES[ligue], SAISONS[saison_prec]
                )
                historique = pd.concat(
                    [matchs_prec, matchs_saison],
                    ignore_index=True,
                ).sort_values("Date").reset_index(drop=True)

            except Exception:
                st.warning(
                    "La saison précédente n'a pas pu être chargée. "
                    "Les calculs utilisent la saison sélectionnée."
                )

except Exception as erreur:
    st.error("Impossible de charger les données historiques.")
    st.caption("Détail technique : " + str(erreur))
    st.stop()

if matchs_saison.empty:
    st.warning(
        "Aucun résultat terminé et daté dans cette saison. "
        "Essaie une autre saison ou actualise plus tard."
    )
    st.stop()

st.success("Données chargées.")

c1, c2, c3 = st.columns(3)
c1.metric("Matchs de la saison", len(matchs_saison))
c2.metric(
    "Équipes trouvées",
    len(set(matchs_saison["HomeTeam"]) | set(matchs_saison["AwayTeam"]))
)
c3.metric("Matchs historiques", len(historique))

dates = matchs_saison["Date"].dropna()
if not dates.empty:
    st.caption(
        "Dates disponibles : "
        + dates.min().strftime("%d/%m/%Y")
        + " au "
        + dates.max().strftime("%d/%m/%Y")
    )

st.info(
    "Les fichiers contiennent des résultats historiques. "
    "Ils ne confirment pas à eux seuls qu'un match est programmé demain. "
    "Les pondérations sont des choix de modèle, pas des preuves "
    "d'une meilleure précision."
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
    equipe_dom = st.selectbox(
        "Équipe à domicile", equipes, index=0
    )

with c2:
    equipe_ext = st.selectbox(
        "Équipe à l'extérieur",
        equipes,
        index=1,
    )

if equipe_dom == equipe_ext:
    st.warning("Choisis deux équipes différentes.")

if st.button("📊 Calculer les probabilités", type="primary"):
    if equipe_dom == equipe_ext:
        st.error("Les deux équipes doivent être différentes.")
        st.stop()

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
        c3.metric(
            "Les deux équipes marquent",
            f'{resultat["btts"]:.1%}'
        )

        st.write(
            f"Buts attendus par le modèle : "
            f"{equipe_dom} {resultat['lambda_dom']:.2f} — "
            f"{resultat['lambda_ext']:.2f} {equipe_ext}"
        )

        st.subheader("4. Scores les plus probables")
        for a, b, p in resultat["scores"]:
            st.write(
                f"**{equipe_dom} {a} - {b} {equipe_ext}** — {p:.1%}"
            )

        st.subheader("5. Forme récente")

        if resultat["forme_utilisee"]:
            st.success(
                "La forme récente a été intégrée à 35 % "
                "et la référence historique à 65 %."
            )
        else:
            st.warning(
                "Pas assez de matchs récents pour intégrer la forme "
                "des deux équipes."
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
            tableau["Date"] = tableau["Date"].dt.strftime("%d/%m/%Y")

            st.dataframe(
                tableau[["Date", "Match", "Score", "Lieu"]],
                hide_index=True,
                use_container_width=True,
            )

        st.subheader("6. Quantité de données historiques")

        c1, c2 = st.columns(2)
        c1.metric(
            f"{equipe_dom} à domicile",
            resultat["stats_dom"]["dom"]
        )
        c2.metric(
            f"{equipe_ext} à l'extérieur",
            resultat["stats_ext"]["ext"]
        )

        st.write(
            "Indicateur de données : " + resultat["fiabilite"]
        )
        st.caption(
            "Cet indicateur mesure seulement la quantité de rencontres "
            "disponibles. Il ne mesure pas la précision réelle du modèle."
        )

        st.subheader("7. Limites")
        st.subheader("7. Cotes du bookmaker et valeur théorique")

        st.caption(
            "Saisis les cotes décimales actuelles de ton bookmaker. "
            "Les cotes ne sont pas récupérées automatiquement."
        )

        col1, col2, col3 = st.columns(3)

        with col1:
             cote_1 = st.number_input(
                f"Cote victoire {equipe_dom}",
                min_value=1.01,
                value=2.10,
                step=0.05,
                key="cote_1",
            )

        with col2:
             cote_n = st.number_input(
                "Cote du match nul",
                min_value=1.01,
                value=3.50,
                step=0.05,
                key="cote_n",
            )

        with col3:
             cote_2 = st.number_input(
                f"Cote victoire {equipe_ext}",
                min_value=1.01,
                value=3.15,
                step=0.05,
                key="cote_2",
            )

        probabilites_modele = {
            "1": resultat["1"],
            "N": resultat["N"],
            "2": resultat["2"],
        }

        cotes = {
            "1": cote_1,
            "N": cote_n,
            "2": cote_2,
        }

        implicites = {
            issue: 1 / cote
            for issue, cote in cotes.items()
        }

        somme_implicites = sum(implicites.values())
        marge = somme_implicites - 1

        st.metric("Marge théorique du bookmaker", f"{marge:.2%}")

        lignes = []

        for issue, nom in [
            ("1", f"Victoire {equipe_dom}"),
            ("N", "Match nul"),
            ("2", f"Victoire {equipe_ext}"),
        ]:
            cote = cotes[issue]
            proba_modele = probabilites_modele[issue]
            proba_brute = implicites[issue]
            proba_marche = proba_brute / somme_implicites
            valeur_theorique = proba_modele * cote - 1

            lignes.append({
                "Résultat": nom,
                "Cote": round(cote, 2),
                "Modèle": f"{proba_modele:.1%}",
                "Marché corrigé": f"{proba_marche:.1%}",
                "Écart modèle-marché": (
                    f"{(proba_modele - proba_marche) * 100:+.1f} points"
                ),
                "Valeur théorique": f"{valeur_theorique:+.1%}",
            })

        st.dataframe(
            pd.DataFrame(lignes),
            hide_index=True,
            use_container_width=True,
        )

        st.caption(
            "Valeur théorique = probabilité du modèle × cote − 1. "
            "Elle n'est pertinente que si la probabilité du modèle "
            "est suffisamment fiable. Une valeur positive ne garantit "
            "ni un gain ni un avantage réel."
        )

        st.subheader("8. Vérification des absences et actualités")

        st.write(
            "Vérifie les informations récentes auprès de sources fiables "
            "avant de les saisir ici."
        )

        absences_dom = st.text_area(
            f"Absences vérifiées — {equipe_dom}",
            placeholder="Joueurs absents, suspendus ou incertains...",
            key="absences_dom",
        )

        absences_ext = st.text_area(
            f"Absences vérifiées — {equipe_ext}",
            placeholder="Joueurs absents, suspendus ou incertains...",
            key="absences_ext",
        )

        if absences_dom.strip() or absences_ext.strip():
            st.info(
                "Absences saisies manuellement. Elles ne modifient pas "
                "encore les probabilités calculées par le modèle."
        )
        st.warning(
            "Le modèle n'intègre pas automatiquement les blessures, "
            "les suspensions, les compositions officielles, les cotes "
            "ou les changements tactiques. Il n'a pas encore été validé "
            "sur un ensemble de prédictions historiques. Les probabilités "
            "ne garantissent aucun résultat et ne suffisent pas, seules, "
            "à justifier un pari."
        )

st.divider()
st.subheader("8. Test historique du modèle")

st.write(
    "Le test compare les prédictions aux résultats réels, "
    "en utilisant uniquement les matchs antérieurs à chaque rencontre."
)


if st.button("🧪 Lancer le backtest", type="primary"):
    with st.spinner("Test des matchs historiques en cours..."):
        try:
            resultats_test = executer_backtest(
                matchs_saison,
                historique,
            )

            if resultats_test.empty:
                st.warning(
                    "Aucun match n'a pu être testé. "
                    "Il faut davantage de résultats historiques."
                )
            else:
                nombre = len(resultats_test)
                taux = resultats_test["Correct"].mean()

                # Calcul du score de Brier multiclasses 1N2
                brier_scores = []

                for _, ligne in resultats_test.iterrows():
                    reel = ligne["Issue réelle"]

                    cible = {
                        "1": 1 if reel == "1" else 0,
                        "N": 1 if reel == "N" else 0,
                        "2": 1 if reel == "2" else 0,
                    }

                    brier = sum(
                        (
                            float(ligne[f"Probabilité {issue}"])
                            - cible[issue]
                        ) ** 2
                        for issue in ["1", "N", "2"]
                    )

                    brier_scores.append(brier)

                score_brier = sum(brier_scores) / len(brier_scores)

                # Référence : probabilités égales pour les 3 issues
                brier_reference = 2 / 3
                difference_brier = brier_reference - score_brier

                
                c1, c2, c3, c4 = st.columns(4)

                c1.metric("Matchs testés", nombre)
                c2.metric(
                    "Prédictions 1N2 correctes",
                    f"{taux:.1%}",
                )
                c3.metric(
                    "Brier du modèle",
                    f"{score_brier:.3f}",
                )
                c4.metric(
                    "Brier de référence",
                    f"{brier_reference:.3f}",
                )

                st.caption(
                    "La référence attribue 1/3 de probabilité à chaque "
                    "issue (1, N et 2). Un Brier inférieur est préférable, "
                    "mais cette comparaison seule ne prouve pas la fiabilité "
                    "du modèle."
                )


                c1.metric("Matchs testés", nombre)
                c2.metric(
                    "Prédictions 1N2 correctes",
                    f"{taux:.1%}",
                )
                c3.metric(
                    "Score de Brier 1N2",
                    f"{score_brier:.3f}",
                )

                st.caption(
                    "Pour le score de Brier multiclasses, plus le résultat "
                    "est proche de 0, meilleures sont les probabilités. "
                    "Le score doit aussi être comparé à une référence."
                )

                st.subheader("Résultats du test")
                st.dataframe(
                    resultats_test,
                    hide_index=True,
                    use_container_width=True,
                )

                csv = resultats_test.to_csv(index=False).encode("utf-8")

                st.download_button(
                    "📥 Télécharger les résultats CSV",
                    data=csv,
                    file_name="backtest_football.csv",
                    mime="text/csv",
                )

                st.caption(
                    "Un taux de réussite historique ne garantit pas "
                    "les performances futures. Ce premier test mesure "
                    "les prédictions 1N2 ; il ne constitue pas encore "
                    "une validation complète du modèle."
                )

        except Exception as erreur:
            st.error("Le backtest a rencontré une erreur.")
            st.caption("Détail technique : " + str(erreur))

st.divider()
st.caption(
    "Football Analytics AI V2.3 | Données historiques Football-Data.co.uk"
)
