# utils/email.py
# ─────────────────────────────────────────────────────────────────
# Envoi d'emails HTML pour Talan Assistant.
#
# Fonctions publiques :
#   send_credentials_email(to, name, password)
#   send_leave_request_email(to, employee_name, start_date, end_date, days_count)
#   send_leave_approved_email(to, employee_name, start_date, end_date, days_count, manager_name, cc)
#   send_leave_rejected_email(to, employee_name, start_date, end_date, days_count, reason, manager_name, cc)
#   send_generic_email(to, subject, body, cc_emails)   ← email générique / LLM
# ─────────────────────────────────────────────────────────────────

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

EMAIL_HOST      = os.getenv("EMAIL_HOST")
EMAIL_PORT      = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER      = os.getenv("EMAIL_USER")
EMAIL_PASSWORD  = os.getenv("EMAIL_PASSWORD")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Talan RH System")
EMAIL_DEV_MODE  = os.getenv("EMAIL_DEV_MODE", "false").lower() == "true"


# ══════════════════════════════════════════════════════════════════
# BASE HTML TEMPLATE
# ══════════════════════════════════════════════════════════════════

def _base_html(
    header_color: str,
    header_icon: str,
    header_title: str,
    content_html: str,
) -> str:
    """Génère un email HTML responsive avec un header coloré et un corps structuré."""
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{header_title}</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);max-width:560px;width:100%;">

          <!-- HEADER -->
          <tr>
            <td style="background:{header_color};padding:28px 32px 24px;">
              <div style="font-size:32px;margin-bottom:10px;line-height:1;">{header_icon}</div>
              <p style="margin:0;color:#ffffff;font-size:19px;font-weight:700;letter-spacing:-0.3px;">{header_title}</p>
            </td>
          </tr>

          <!-- BODY -->
          <tr>
            <td style="padding:28px 32px 24px;">
              {content_html}
            </td>
          </tr>

          <!-- FOOTER -->
          <tr>
            <td style="border-top:1px solid #e2e8f0;padding:16px 32px;background:#f8fafc;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <span style="font-size:13px;font-weight:800;color:#0f172a;letter-spacing:-0.4px;">
                      Talan <span style="color:{header_color};">Assistant</span>
                    </span>
                  </td>
                  <td align="right">
                    <span style="font-size:11px;color:#94a3b8;">Système automatisé · Ne pas répondre</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _info_row(label: str, value: str) -> str:
    return f"""
      <tr>
        <td style="padding:7px 0;font-size:14px;color:#64748b;width:40%;">{label}</td>
        <td style="padding:7px 0;font-size:14px;color:#1e293b;font-weight:600;">{value}</td>
      </tr>"""


def _badge(text: str, bg: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;padding:3px 12px;border-radius:20px;'
        f'background:{bg};color:{color};font-size:12px;font-weight:700;">{text}</span>'
    )


# ══════════════════════════════════════════════════════════════════
# SMTP SENDER (interne)
# ══════════════════════════════════════════════════════════════════

def _send(to_email: str, subject: str, plain_body: str, html_body: str, cc_emails: list[str] | None = None) -> None:
    """Envoie l'email en multipart/alternative (texte + HTML)."""
    cc_emails = cc_emails or []

    if EMAIL_DEV_MODE:
        logger.info("=" * 60)
        logger.info("[DEV] Email non envoyé — affichage console")
        logger.info(f"  À       : {to_email}")
        if cc_emails:
            logger.info(f"  CC      : {', '.join(cc_emails)}")
        logger.info(f"  Sujet   : {subject}")
        logger.info(f"  Corps   :\n{plain_body}")
        logger.info("=" * 60)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_USER}>"
    msg["To"]      = to_email
    if cc_emails:
        msg["Cc"] = ", ".join(cc_emails)

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body,  "html",  "utf-8"))

    all_recipients = [to_email] + cc_emails
    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, all_recipients, msg.as_string())
        logger.info(f"[EMAIL] Envoyé : '{subject}' → {to_email}")
    except Exception:
        logger.exception(f"[EMAIL] Échec envoi vers {to_email}")
        raise


# ══════════════════════════════════════════════════════════════════
# TEMPLATES MÉTIER
# ══════════════════════════════════════════════════════════════════

def send_credentials_email(to_email: str, name: str, password: str) -> None:
    """Email de bienvenue avec identifiants de connexion."""
    subject = "Vos identifiants — Talan Assistant"
    first   = name.split()[0]

    plain = (
        f"Bonjour {first},\n\n"
        f"Votre compte Talan Assistant a été créé.\n\n"
        f"  Email        : {to_email}\n"
        f"  Mot de passe : {password}\n\n"
        f"Veuillez changer votre mot de passe dès votre première connexion.\n\n"
        f"Cordialement,\nTalan Assistant"
    )

    html = _base_html(
        header_color="#0ea5e9",
        header_icon="🔐",
        header_title="Bienvenue sur Talan Assistant",
        content_html=f"""
          <p style="margin:0 0 8px;font-size:15px;color:#1e293b;">Bonjour <strong>{first}</strong>,</p>
          <p style="margin:0 0 20px;font-size:14px;color:#475569;">Votre compte vient d'être créé. Voici vos identifiants de connexion :</p>

          <table width="100%" cellpadding="0" cellspacing="0"
                 style="background:#f0f9ff;border-left:4px solid #0ea5e9;border-radius:6px;padding:16px 20px;margin-bottom:20px;">
            {_info_row("Email", to_email)}
            {_info_row("Mot de passe", f'<code style="background:#e0f2fe;padding:2px 8px;border-radius:4px;font-family:monospace;">{password}</code>')}
          </table>

          <p style="margin:0;font-size:13px;color:#f59e0b;background:#fffbeb;border:1px solid #fde68a;border-radius:6px;padding:10px 14px;">
            ⚠️ Veuillez changer votre mot de passe dès votre première connexion.
          </p>
        """,
    )

    _send(to_email, subject, plain, html)


def send_leave_request_email(
    to_email: str,
    employee_name: str,
    start_date: str,
    end_date: str,
    days_count: int,
) -> None:
    """Notifie le manager qu'une demande de congé vient d'être déposée."""
    subject = f"Nouvelle demande de congé — {employee_name}"
    first   = employee_name.split()[0]

    plain = (
        f"Bonjour,\n\n"
        f"{employee_name} a déposé une demande de congé.\n\n"
        f"  Du    : {start_date}\n"
        f"  Au    : {end_date}\n"
        f"  Durée : {days_count} jour(s) ouvré(s)\n\n"
        f"Cette demande sera traitée par l'équipe RH.\n\n"
        f"Cordialement,\nTalan Assistant"
    )

    pending_badge = _badge("⏳ En cours de traitement RH", "#fef9c3", "#854d0e")

    html = _base_html(
        header_color="#f59e0b",
        header_icon="📋",
        header_title="Nouvelle demande de congé",
        content_html=f"""
          <p style="margin:0 0 6px;font-size:15px;color:#1e293b;">Bonjour,</p>
          <p style="margin:0 0 20px;font-size:14px;color:#475569;">
            Pour information, <strong>{employee_name}</strong> a déposé une demande de congé.
          </p>

          <table width="100%" cellpadding="0" cellspacing="0"
                 style="background:#fffbeb;border-left:4px solid #f59e0b;border-radius:6px;padding:16px 20px;margin-bottom:20px;">
            {_info_row("Employé", f"<strong>{employee_name}</strong>")}
            {_info_row("Du", start_date)}
            {_info_row("Au", end_date)}
            {_info_row("Durée", f"{days_count} jour(s) ouvré(s)")}
            {_info_row("Traitement", pending_badge)}
          </table>

          <p style="margin:0;font-size:13px;color:#64748b;background:#f8fafc;border-radius:6px;padding:10px 14px;">
            Cette demande sera traitée par l'équipe RH. Vous recevrez une notification une fois la décision prise.
          </p>
        """,
    )

    _send(to_email, subject, plain, html)


def send_leave_approved_email(
    to_email: str,
    employee_name: str,
    start_date: str,
    end_date: str,
    days_count: int,
    manager_name: str | None = None,
    cc_emails: list[str] | None = None,
) -> None:
    """Notifie l'employé que son congé a été approuvé."""
    subject = "Votre congé a été approuvé ✅ — Talan"
    first   = employee_name.split()[0]

    manager_line = f"\nVotre manager {manager_name} a été notifié.\n" if manager_name else ""
    plain = (
        f"Bonjour {first},\n\n"
        f"Votre demande de congé a été approuvée.\n\n"
        f"  Du    : {start_date}\n"
        f"  Au    : {end_date}\n"
        f"  Durée : {days_count} jour(s) ouvré(s)\n"
        f"{manager_line}\n"
        f"Cordialement,\nL'équipe RH — Talan Tunisie"
    )

    approved_badge = _badge("✅ Approuvé", "#dcfce7", "#15803d")
    manager_note = (
        f'<p style="margin:16px 0 0;font-size:13px;color:#475569;">'
        f'Votre manager <strong>{manager_name}</strong> a également été notifié.</p>'
    ) if manager_name else ""

    html = _base_html(
        header_color="#10b981",
        header_icon="✅",
        header_title="Votre congé a été approuvé",
        content_html=f"""
          <p style="margin:0 0 6px;font-size:15px;color:#1e293b;">Bonjour <strong>{first}</strong>,</p>
          <p style="margin:0 0 20px;font-size:14px;color:#475569;">
            Bonne nouvelle ! Votre demande de congé a été <strong>approuvée</strong>.
          </p>

          <table width="100%" cellpadding="0" cellspacing="0"
                 style="background:#f0fdf4;border-left:4px solid #10b981;border-radius:6px;padding:16px 20px;margin-bottom:16px;">
            {_info_row("Du", start_date)}
            {_info_row("Au", end_date)}
            {_info_row("Durée", f"{days_count} jour(s) ouvré(s)")}
            {_info_row("Statut", approved_badge)}
          </table>

          {manager_note}
        """,
    )

    _send(to_email, subject, plain, html, cc_emails)


def send_leave_rejected_email(
    to_email: str,
    employee_name: str,
    start_date: str,
    end_date: str,
    days_count: int,
    reason: str = "",
    manager_name: str | None = None,
    cc_emails: list[str] | None = None,
) -> None:
    """Notifie l'employé que son congé a été refusé."""
    subject = "Votre demande de congé n'a pas été approuvée — Talan"
    first   = employee_name.split()[0]
    reason_text = reason or "Aucune raison précisée"

    plain = (
        f"Bonjour {first},\n\n"
        f"Votre demande de congé n'a pas pu être approuvée.\n\n"
        f"  Du    : {start_date}\n"
        f"  Au    : {end_date}\n"
        f"  Durée : {days_count} jour(s) ouvré(s)\n"
        f"  Motif : {reason_text}\n\n"
        f"Pour toute question, contactez l'équipe RH.\n\n"
        f"Cordialement,\nL'équipe RH — Talan Tunisie"
    )

    rejected_badge = _badge("❌ Refusé", "#fee2e2", "#b91c1c")
    manager_note = (
        f'<p style="margin:16px 0 0;font-size:13px;color:#475569;">'
        f'Votre manager <strong>{manager_name}</strong> a également été informé.</p>'
    ) if manager_name else ""

    html = _base_html(
        header_color="#ef4444",
        header_icon="❌",
        header_title="Demande de congé refusée",
        content_html=f"""
          <p style="margin:0 0 6px;font-size:15px;color:#1e293b;">Bonjour <strong>{first}</strong>,</p>
          <p style="margin:0 0 20px;font-size:14px;color:#475569;">
            Nous vous informons que votre demande de congé n'a pas pu être approuvée.
          </p>

          <table width="100%" cellpadding="0" cellspacing="0"
                 style="background:#fef2f2;border-left:4px solid #ef4444;border-radius:6px;padding:16px 20px;margin-bottom:16px;">
            {_info_row("Du", start_date)}
            {_info_row("Au", end_date)}
            {_info_row("Durée", f"{days_count} jour(s) ouvré(s)")}
            {_info_row("Statut", rejected_badge)}
            {_info_row("Motif", f'<em style="color:#7f1d1d;">{reason_text}</em>')}
          </table>

          <p style="margin:0;font-size:13px;color:#475569;background:#f8fafc;border-radius:6px;padding:10px 14px;">
            Pour toute question ou recours, contactez directement l'équipe RH.
          </p>

          {manager_note}
        """,
    )

    _send(to_email, subject, plain, html, cc_emails)


def send_generic_email(
    to_email: str,
    subject: str,
    body: str,
    cc_emails: list[str] | None = None,
) -> None:
    """
    Envoie un email générique (contenu LLM ou texte libre).
    Le corps texte brut est converti en HTML simple avec mise en forme.
    """
    cc_emails = cc_emails or []

    # Convertit le texte brut en HTML lisible
    lines_html = "".join(
        f'<p style="margin:0 0 8px;font-size:14px;color:#334155;">{line if line.strip() else "&nbsp;"}</p>'
        for line in body.split("\n")
    )

    html = _base_html(
        header_color="#6366f1",
        header_icon="✉️",
        header_title=subject,
        content_html=f'<div style="line-height:1.6;">{lines_html}</div>',
    )

    _send(to_email, subject, body, html, cc_emails)
