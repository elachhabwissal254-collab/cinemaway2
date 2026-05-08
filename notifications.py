"""
CINEMAWAY - Notifications & Emails
Gestion des alertes internes + emails (SMTP ou simulation)
"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime

# ─── Config SMTP (via variables d'environnement) ──────────────────────────────
SMTP_HOST  = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT  = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER  = os.environ.get('SMTP_USER', 'cinemaway26@gmail.com')
SMTP_PASS  = os.environ.get('SMTP_PASS', '')
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'cinemaway26@gmail.com')
FROM_NAME  = 'CINEMAWAY Agency'

# ─── Templates emails ─────────────────────────────────────────────────────────

EMAIL_BASE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Georgia, serif; background:#f5f5f5; margin:0; padding:0; }}
  .wrap {{ max-width:600px; margin:0 auto; background:#fff; }}
  .header {{ background:#0A1522; padding:32px 40px; text-align:center; }}
  .header h1 {{ color:#EBC283; font-size:28px; letter-spacing:6px; margin:0; font-weight:normal; }}
  .header p {{ color:#8F6C49; font-size:11px; letter-spacing:2px; margin:8px 0 0; }}
  .body {{ padding:36px 40px; color:#333; line-height:1.7; }}
  .body h2 {{ color:#8F6C49; font-size:18px; margin-top:0; }}
  .badge {{ display:inline-block; background:#EBC283; color:#0A1522;
            padding:6px 18px; border-radius:20px; font-weight:bold; font-size:13px; }}
  .info-box {{ background:#f9f6f0; border-left:3px solid #EBC283;
               padding:16px 20px; margin:20px 0; border-radius:0 6px 6px 0; }}
  .info-box p {{ margin:4px 0; font-size:14px; }}
  .btn {{ display:inline-block; background:#EBC283; color:#0A1522;
          text-decoration:none; padding:12px 28px; border-radius:4px;
          font-weight:bold; letter-spacing:1px; margin-top:20px; }}
  .footer {{ background:#0A1522; padding:20px 40px; text-align:center; }}
  .footer p {{ color:#555; font-size:11px; margin:4px 0; }}
  .footer a {{ color:#EBC283; text-decoration:none; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>CINEMAWAY</h1>
    <p>PRODUCTION AGENCY · MARRAKECH</p>
  </div>
  <div class="body">
    {content}
  </div>
  <div class="footer">
    <p>cinemaway26@gmail.com · +212 654 045 836</p>
    <p>Appt 15 Imm 12 Lot SINE ALLAL EL FASSI, Marrakech</p>
    <p style="margin-top:10px;color:#444;">© {year} CINEMAWAY. Tous droits réservés.</p>
  </div>
</div>
</body>
</html>
"""


def _render(content: str) -> str:
    return EMAIL_BASE.format(content=content, year=datetime.now().year)


def _send(to_email: str, subject: str, html_body: str, attachment_bytes=None, attachment_name=None):
    """Envoie un email. Si SMTP_PASS est vide, simule l'envoi (log console)."""
    if not SMTP_PASS:
        print(f"[EMAIL SIM] To: {to_email} | Subject: {subject}")
        return True

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg['To']      = to_email
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    if attachment_bytes and attachment_name:
        part = MIMEApplication(attachment_bytes, Name=attachment_name)
        part['Content-Disposition'] = f'attachment; filename="{attachment_name}"'
        msg.attach(part)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False


# ─── Emails métier ────────────────────────────────────────────────────────────

def send_welcome(user: dict):
    """Email de bienvenue après inscription."""
    content = f"""
    <h2>Bienvenue chez CINEMAWAY, {user['name']} !</h2>
    <p>Votre compte a été créé avec succès. Vous pouvez dès maintenant commander
    vos services audiovisuels et suivre vos projets en temps réel.</p>
    <div class="info-box">
      <p><b>Email :</b> {user['email']}</p>
      <p><b>Rôle :</b> Client</p>
    </div>
    <p>Explorez notre catalogue et lancez votre premier projet cinématographique.</p>
    """
    return _send(
        user['email'],
        '🎬 Bienvenue chez CINEMAWAY',
        _render(content)
    )


def send_order_confirmation(order: dict, client: dict):
    """Confirmation de commande au client."""
    service = order.get('service', {}) or {}
    content = f"""
    <h2>Commande confirmée</h2>
    <p>Bonjour {client['name']}, votre commande a bien été enregistrée.</p>
    <div class="info-box">
      <p><b>Référence :</b> {order.get('reference','—')}</p>
      <p><b>Service :</b> {service.get('name', order.get('title',''))}</p>
      <p><b>Statut :</b> <span class="badge">En attente</span></p>
      <p><b>Date :</b> {order.get('created_at','')[:10]}</p>
    </div>
    <p>Notre équipe va analyser votre brief et vous contacter sous 24h.</p>
    """
    return _send(
        client['email'],
        f"✅ Commande {order.get('reference','—')} confirmée",
        _render(content)
    )


def send_order_new_admin(order: dict, client: dict, admin_email: str):
    """Alerte admin : nouvelle commande."""
    service = order.get('service', {}) or {}
    content = f"""
    <h2>🆕 Nouvelle commande reçue</h2>
    <div class="info-box">
      <p><b>Client :</b> {client['name']} ({client['email']})</p>
      <p><b>Entreprise :</b> {client.get('company','—')}</p>
      <p><b>Service :</b> {service.get('name','—')}</p>
      <p><b>Budget :</b> {order.get('budget','—')} MAD</p>
      <p><b>Ref :</b> {order.get('reference','—')}</p>
    </div>
    <p>Connectez-vous au tableau de bord admin pour traiter cette commande.</p>
    """
    return _send(admin_email, f"📥 Nouvelle commande – {order.get('reference','')}", _render(content))


def send_status_update(order: dict, client: dict, new_status: str):
    """Notification de changement de statut."""
    labels = {
        'pending':     ('⏳ En attente', '#F39C12'),
        'in_progress': ('🎬 En cours de production', '#2980B9'),
        'review':      ('🔍 En révision', '#8E44AD'),
        'completed':   ('✅ Terminé', '#27AE60'),
        'cancelled':   ('❌ Annulé', '#E74C3C'),
    }
    label, color = labels.get(new_status, (new_status, '#333'))
    content = f"""
    <h2>Mise à jour de votre projet</h2>
    <p>Bonjour {client['name']}, le statut de votre commande a été mis à jour.</p>
    <div class="info-box">
      <p><b>Commande :</b> {order.get('reference','—')} – {order.get('title','')}</p>
      <p><b>Nouveau statut :</b> <span class="badge">{label}</span></p>
      <p><b>Avancement :</b> {order.get('progress',0)}%</p>
    </div>
    {"<p>Votre projet est terminé ! Pensez à laisser un avis.</p>" if new_status == 'completed' else
     "<p>Connectez-vous pour suivre l'avancement en temps réel.</p>"}
    """
    return _send(
        client['email'],
        f"📢 Statut mis à jour – {order.get('reference','—')}",
        _render(content)
    )


def send_new_message(order: dict, recipient: dict, sender_name: str, preview: str):
    """Notification de nouveau message dans le chat."""
    content = f"""
    <h2>Nouveau message</h2>
    <p>Bonjour {recipient['name']}, vous avez reçu un message concernant votre projet.</p>
    <div class="info-box">
      <p><b>De :</b> {sender_name}</p>
      <p><b>Projet :</b> {order.get('reference','—')} – {order.get('title','')}</p>
      <p><b>Message :</b> {preview[:120]}{'...' if len(preview) > 120 else ''}</p>
    </div>
    <p>Connectez-vous pour répondre.</p>
    """
    return _send(
        recipient['email'],
        f"💬 Nouveau message – {order.get('reference','—')}",
        _render(content)
    )


def send_invoice(order: dict, transaction: dict, client: dict, pdf_bytes: bytes):
    """Envoi de la facture PDF par email."""
    ref = transaction.get('reference', 'FACTURE')
    content = f"""
    <h2>Votre facture CINEMAWAY</h2>
    <p>Bonjour {client['name']}, veuillez trouver ci-joint votre facture.</p>
    <div class="info-box">
      <p><b>Référence :</b> {ref}</p>
      <p><b>Commande :</b> {order.get('reference','—')}</p>
      <p><b>Montant :</b> {transaction.get('amount',0):,} MAD TTC</p>
      <p><b>Statut :</b> <span class="badge">PAYÉ</span></p>
    </div>
    <p>Merci pour votre confiance. À très bientôt pour de nouveaux projets !</p>
    """
    return _send(
        client['email'],
        f"🧾 Facture {ref} – CINEMAWAY",
        _render(content),
        attachment_bytes=pdf_bytes,
        attachment_name=f"Facture_{ref}.pdf"
    )
