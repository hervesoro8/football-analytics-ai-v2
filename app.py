
import streamlit as st
import requests
from datetime import date, timedelta
import math
from collections import defaultdict
# -----------------------------
# 1. CONFIGURATION
# -----------------------------
st.set_page_config(
    page_title="Football Analytics AI V2",
    page_icon="⚽",
    layout="wide"
)

BASE_URL = "https://api.football-data.org/v4"
TIMEOUT = 20

st.title("⚽ Football Analytics AI V2")
st.write("Consulte les matchs de football à venir.")

# -----------------------------
# 2. CONNEXION A L'API
# -----------------------------
try:
    token = str(st.secrets["FOOTBALL_DATA_TOKEN"]).strip()
except Exception:
    st.error("Le secret FOOTBALL_DATA_TOKEN est introuvable dans Streamlit.")
    st.stop()

if not token:
    st.error("Le token API est vide. Vérifie les Secrets de Streamlit.")
    st.stop()

HEADERS = {"X-Auth-Token": token}



def api_get(endpoint, params=None):
    """Interroge l'API et affiche les erreurs detaillees."""
    try:
        url = BASE_URL.rstrip("/") + "/" + endpoint.lstrip("/")

        response = requests.get(
            url,
            headers=HEADERS,
            params=params,
            timeout=TIMEOUT
        )

        if response.status_code == 200:
            return response.json()

        st.error("Erreur API : HTTP " + str(response.status_code))

        # Afficher le detail de l'erreur renvoyee par l'API
        detail = response.text[:500]
        if detail:
            st.code(detail)

        return None

    except requests.exceptions.Timeout:
        st.error("Le serveur met trop de temps a repondre.")
    except requests.exceptions.RequestException as erreur:
        st.error("Erreur de connexion : " + str(erreur))
    except ValueError:
        st.error("La reponse de l'API n'est pas un JSON valide.")

    return None


# 
# -----------------------------
# MOTEUR D'ANALYSE STATISTIQUE
# -----------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def charger_historique(code_competition, debut, fin):
    """Charge les matchs terminés d'une compétition."""
    endpoint = "/competitions/" + code_competition + "/matches"

    try:
        response = requests.get(
            BASE_URL + endpoint,
            headers=HEADERS,
            params={
                "dateFrom": debut,
                "dateTo": fin,
                "status": "FINISHED",
                "limit": 500
            },
            timeout=TIMEOUT
        )

        if response.status_code != 200:
            return []

        return response.json().get("matches", [])

    except requests.exceptions.RequestException:
        return []


def calculer_moyennes(equipe, historique):
    """Calcule les buts marqués et encaissés."""
    stats = {
        "domicile": {"marques": 0, "encaisses": 0, "matchs": 0},
        "exterieur": {"marques": 0, "encaisses": 0, "matchs": 0}
    }

    for match in historique:
        if match.get("status") != "FINISHED":
            continue

        domicile = (match.get("homeTeam") or {}).get("name")
        exterieur = (match.get("awayTeam") or {}).get("name")
        score = match.get("score", {}).get("fullTime", {})

        buts_dom = score.get("home")
        buts_ext = score.get("away")

        if buts_dom is None or buts_ext is None:
            continue

        if domicile == equipe:
            bloc = stats["domicile"]
            bloc["marques"] += buts_dom
            bloc["encaisses"] += buts_ext
            bloc["matchs"] += 1

        if exterieur == equipe:
            bloc = stats["exterieur"]
            bloc["marques"] += buts_ext
            bloc["encaisses"] += buts_dom
            bloc["matchs"] += 1

    return stats


def probabilite_poisson(k, lam):
    """Estime la probabilité de k buts."""
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def analyser_match(equipe_dom, equipe_ext, historique):
    """Calcule les probabilités principales."""
    stats_dom = calculer_moyennes(equipe_dom, historique)
    stats_ext = calculer_moyennes(equipe_ext, historique)

    dom = stats_dom["domicile"]
    ext = stats_ext["exterieur"]

    if dom["matchs"] < 3 or ext["matchs"] < 3:
        return {
            "erreur": (
                "Historique insuffisant : au moins 3 matchs "
                "à domicile et 3 à l'extérieur sont nécessaires."
            )
        }

    moyenne_dom = dom["marques"] / dom["matchs"]
    defense_dom = dom["encaisses"] / dom["matchs"]
    moyenne_ext = ext["marques"] / ext["matchs"]
    defense_ext = ext["encaisses"] / ext["matchs"]

    lambda_dom = (moyenne_dom + defense_ext) / 2
    lambda_ext = (moyenne_ext + defense_dom) / 2

    scores = []

    for b1 in range(11):
        for b2 in range(11):
            p1 = probabilite_poisson(b1, lambda_dom)
            p2 = probabilite_poisson(b2, lambda_ext)
            scores.append((b1, b2, p1 * p2))

    total = sum(p for _, _, p in scores)

    scores = [
        (b1, b2, p / total)
        for b1, b2, p in scores
    ]

    victoire_dom = sum(p for b1, b2, p in scores if b1 > b2)
    nul = sum(p for b1, b2, p in scores if b1 == b2)
    victoire_ext = sum(p for b1, b2, p in scores if b1 < b2)
    over25 = sum(p for b1, b2, p in scores if b1 + b2 >= 3)
    btts = sum(p for b1, b2, p in scores if b1 >= 1 and b2 >= 1)

    return {
        "erreur": None,
        "1": victoire_dom,
        "N": nul,
        "2": victoire_ext,
        "over25": over25,
        "under25": 1 - over25,
        "btts": btts,
        "lambda_dom": lambda_dom,
        "lambda_ext": lambda_ext,
        "scores": sorted(
            scores, key=lambda x: x[2], reverse=True
        )[:5]
    }
-----------------------------
# 3. CHOIX DES DATES
# -----------------------------
aujourd_hui = date.today()

colonne1, colonne2 = st.columns(2)

with colonne1:
    date_debut = st.date_input(
        "Date de début",
        value=aujourd_hui
    )

with colonne2:
    date_fin = st.date_input(
        "Date de fin",
        value=aujourd_hui + timedelta(days=7)
    )

if date_fin < date_debut:
    st.error("La date de fin doit être égale ou postérieure à la date de début.")
    st.stop()

# -----------------------------
# 4. CHARGEMENT DES COMPETITIONS
# -----------------------------
with st.spinner("Chargement des compétitions..."):
    donnees_competitions = api_get("/competitions")

if donnees_competitions is None:
    st.warning("Impossible de charger les compétitions.")
    st.stop()

competitions = donnees_competitions.get("competitions", [])

options_competitions = {"Toutes les compétitions accessibles": ""}

for competition in competitions:
    code = competition.get("code")
    nom = competition.get("name", "Compétition inconnue")
    pays = (competition.get("area") or {}).get("name", "")

    if code:
        if pays:
            libelle = nom + " - " + pays
        else:
            libelle = nom

        options_competitions[libelle] = code

if len(options_competitions) == 1:
    st.warning("Aucune compétition exploitable n'a été trouvée.")
    st.stop()

choix_competition = st.selectbox(
    "Choisir une compétition",
    list(options_competitions.keys())
)

code_competition = options_competitions[choix_competition]

# -----------------------------
# 5. RECHERCHE DES MATCHS
# -----------------------------
parametres = {
    "dateFrom": date_debut.isoformat(),
    "dateTo": date_fin.isoformat()
}

if code_competition:
    endpoint_matchs = "/competitions/" + code_competition + "/matches"
else:
    endpoint_matchs = "/matches"

with st.spinner("Recherche des matchs..."):
    donnees_matchs = api_get(endpoint_matchs, parametres)

if donnees_matchs is None:
    st.info("Essaie une autre compétition ou une autre période.")
    st.stop()

matchs = donnees_matchs.get("matches", [])

matchs_a_venir = []

for match in matchs:
    statut = match.get("status", "")

    if statut in ["SCHEDULED", "TIMED"]:
        matchs_a_venir.append(match)

matchs_a_venir.sort(key=lambda match: match.get("utcDate", ""))

# -----------------------------
# 6. RESUME
# -----------------------------
st.divider()

colonne1, colonne2, colonne3 = st.columns(3)

colonne1.metric("Matchs trouvés", len(matchs))
colonne2.metric("Matchs à venir", len(matchs_a_venir))
colonne3.metric("Compétitions accessibles", len(competitions))

# -----------------------------
# 7. AFFICHAGE DES MATCHS
# -----------------------------
st.subheader("📅 Calendrier des matchs")

if not matchs_a_venir:
    st.info("Aucun match à venir trouvé pour ces dates.")
else:
    for match in matchs_a_venir:
        competition = (match.get("competition") or {}).get(
            "name", "Compétition inconnue"
        )

        equipe_domicile = (match.get("homeTeam") or {}).get(
            "name", "Équipe inconnue"
        )

        equipe_exterieure = (match.get("awayTeam") or {}).get(
            "name", "Équipe inconnue"
        )

        date_utc = match.get("utcDate", "")

        if date_utc:
            date_affichee = date_utc[:10]
            heure_affichee = date_utc[11:16] + " UTC"
        else:
            date_affichee = "Date inconnue"
            heure_affichee = "Heure inconnue"

        with st.container(border=True):
            st.caption(
                competition + " | " + date_affichee + " | " + heure_affichee
            )

            st.markdown(
                "**" + equipe_domicile + " - " + equipe_exterieure + "**"
            )

            st.caption("Match à venir")

# -----------------------------
# 8. FIN DE PAGE
# -----------------------------
st.divider()

st.caption(
    "Football Analytics AI V2 | Données fournies par football-data.org"
)

st.divider()

st.caption("Football Analytics AI V2 - Donnees fournies par football-data.org")

st.caption("Les matchs et les donnees dependent des competitions accessibles avec ton compte API. Aucun pari n'est garanti.")
