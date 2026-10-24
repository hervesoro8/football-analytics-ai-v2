
import streamlit as st
import requests
import re

# --------------------------------
# CONFIGURATION
# --------------------------------

st.set_page_config(
    page_title="Football Analytics AI V2",
    page_icon="⚽",
    layout="wide"
)

BASE_URL = "https://api.football-data.org/v4"
TIMEOUT = 20

st.title("⚽ Football Analytics AI V2")
st.caption("Vérification de l'API et chargement des compétitions")

# --------------------------------
# LECTURE DU TOKEN SECRET
# --------------------------------

try:
    token = st.secrets["FOOTBALL_DATA_TOKEN"]
    token = str(token).strip()
except Exception:
    st.error(
        "Le secret FOOTBALL_DATA_TOKEN est introuvable. "
        "Vérifie les Secrets dans les paramètres de Streamlit."
    )
    st.stop()

if not token:
    st.error("Le token est vide. Vérifie les Secrets de Streamlit.")
    st.stop()

# --------------------------------
# DIAGNOSTIC SANS AFFICHER LE TOKEN
# --------------------------------

format_correct = bool(re.fullmatch(r"[a-z1-9]+", token))

st.subheader("🔐 Diagnostic du token")
st.write("Token chargé :", bool(token))
st.write("Longueur du token :", len(token))
st.write("Format du token correct :", format_correct)

if not format_correct:
    st.warning(
        "Le token ne correspond pas au format attendu. "
        "Vérifie que tu as copié le token complet, sans espace, "
        "guillemet supplémentaire ni caractère manquant."
    )

# --------------------------------
# TEST DE CONNEXION A L'API
# --------------------------------

HEADERS = {"X-Auth-Token": token}

st.subheader("🌐 Test de connexion")

try:
    response = requests.get(
        f"{BASE_URL}/competitions",
        headers=HEADERS,
        timeout=TIMEOUT
    )

    st.write("Code de réponse API :", response.status_code)

    if response.status_code == 200:
        st.success("Connexion réussie ! Le token est accepté.")

        data = response.json()
        competitions = data.get("competitions", [])

        if competitions:
            st.subheader("🏆 Compétitions disponibles")

            for competition in competitions:
                nom = competition.get("name", "Nom inconnu")
                pays = (
                    competition.get("area") or {}
                ).get("name", "Pays inconnu")

                st.write(f"⚽ {nom} — {pays}")

        else:
            st.info("Connexion réussie, mais aucune compétition reçue.")

    else:
        st.error("Le serveur a refusé la demande.")
        try:
            detail = response.json()
            # Afficher uniquement le message d'erreur du serveur.
            message = detail.get("message", "Aucun détail fourni.")
            code_erreur = detail.get("errorCode")
            st.write("Message :", message)
            if code_erreur is not None:
                st.write("Code d'erreur :", code_erreur)
        except ValueError:
            st.write("Réponse :", response.text[:300])

        if response.status_code == 400:
            st.info(
                "Vérifie le token dans le compte officiel "
                "football-data.org, puis remplace sa valeur dans "
                "les Secrets de Streamlit."
            )

        elif response.status_code == 403:
            st.info(
                "Le token est peut-être reconnu, mais l'accès demandé "
                "peut être limité par les droits du compte."
            )

        elif response.status_code == 429:
            st.info("Limite de requêtes atteinte. Réessaie plus tard.")

except requests.exceptions.Timeout:
    st.error("Le serveur n'a pas répondu à temps.")

except requests.exceptions.RequestException:
    st.error(
        "Impossible de joindre football-data.org. "
        "Vérifie ta connexion internet."
    )

st.divider()
st.caption(
    "Football Analytics AI V2 — diagnostic sécurisé. "
    "Le token secret n'est jamais affiché."
)
