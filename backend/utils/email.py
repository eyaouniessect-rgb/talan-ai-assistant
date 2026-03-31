# utils/email.py
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

EMAIL_HOST      = os.getenv("EMAIL_HOST")
EMAIL_PORT      = int(os.getenv("EMAIL_PORT"))
EMAIL_USER      = os.getenv("EMAIL_USER")
EMAIL_PASSWORD  = os.getenv("EMAIL_PASSWORD")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME")
EMAIL_DEV_MODE  = os.getenv("EMAIL_DEV_MODE", "false").lower() == "true"


def send_credentials_email(to_email: str, name: str, password: str) -> None:
    """
    Envoie un email contenant les identifiants de connexion au nouvel utilisateur.
    En mode DEV (EMAIL_DEV_MODE=true), affiche l'email dans la console.
    """
    subject = "Vos identifiants Talan Assistant"
    body = f"""\
Bonjour {name},

Votre compte Talan Assistant a été créé.

Vos identifiants de connexion :
  Email    : {to_email}
  Mot de passe : {password}

Veuillez changer votre mot de passe dès votre première connexion.

Cordialement,
{EMAIL_FROM_NAME}
"""

    if EMAIL_DEV_MODE:
        logger.info("=" * 60)
        logger.info(f"[DEV] Email non envoyé — affichage console")
        logger.info(f"  À       : {to_email}")
        logger.info(f"  Sujet   : {subject}")
        logger.info(f"  Corps   :\n{body}")
        logger.info("=" * 60)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_USER}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(body, "plain", "utf-8"))

    logger.info(f"[EMAIL] Début envoi des identifiants vers {to_email}")
    try:
        logger.info(f"[EMAIL] Connexion SMTP à {EMAIL_HOST}:{EMAIL_PORT}")
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            logger.info("[EMAIL] Activation TLS")
            server.starttls()
            logger.info(f"[EMAIL] Authentification SMTP avec {EMAIL_USER}")
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            logger.info(f"[EMAIL] Envoi du message à {to_email}")
            server.sendmail(EMAIL_USER, to_email, msg.as_string())
    except Exception:
        logger.exception(f"[EMAIL] Echec envoi vers {to_email}")
        raise

    logger.info(f"[EMAIL] Email envoyé avec succès à {to_email}")
