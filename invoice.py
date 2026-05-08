"""
CINEMAWAY - Générateur de Factures PDF
Utilise ReportLab pour produire des factures professionnelles
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.pdfgen import canvas
from datetime import datetime
import io

# ─── Couleurs CINEMAWAY ──────────────────────────────────────────────────────
GOLD       = HexColor('#EBC283')
GOLD_DARK  = HexColor('#8F6C49')
BLACK      = HexColor('#0A0A0A')
DARK_BG    = HexColor('#0A1522')
LIGHT_GREY = HexColor('#F5F5F5')
MID_GREY   = HexColor('#999999')


def generate_invoice(order, transaction, client) -> bytes:
    """
    Génère une facture PDF professionnelle et retourne les bytes.

    Parameters
    ----------
    order       : dict  – données de la commande (to_dict())
    transaction : dict  – données du paiement (to_dict())
    client      : dict  – données du client (to_dict())

    Returns
    -------
    bytes – contenu PDF prêt à envoyer
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=15*mm,
        bottomMargin=20*mm,
    )

    styles = getSampleStyleSheet()
    story  = []

    # ── Styles personnalisés ─────────────────────────────────────────────────
    title_style = ParagraphStyle(
        'CWTitle',
        fontName='Helvetica-Bold',
        fontSize=22,
        textColor=GOLD,
        spaceAfter=2*mm,
    )
    subtitle_style = ParagraphStyle(
        'CWSubtitle',
        fontName='Helvetica',
        fontSize=10,
        textColor=MID_GREY,
        spaceAfter=6*mm,
    )
    label_style = ParagraphStyle(
        'CWLabel',
        fontName='Helvetica-Bold',
        fontSize=8,
        textColor=MID_GREY,
        spaceBefore=3*mm,
    )
    value_style = ParagraphStyle(
        'CWValue',
        fontName='Helvetica',
        fontSize=10,
        textColor=BLACK,
    )
    section_style = ParagraphStyle(
        'CWSection',
        fontName='Helvetica-Bold',
        fontSize=11,
        textColor=GOLD_DARK,
        spaceBefore=6*mm,
        spaceAfter=3*mm,
    )
    total_style = ParagraphStyle(
        'CWTotal',
        fontName='Helvetica-Bold',
        fontSize=14,
        textColor=GOLD,
        alignment=TA_RIGHT,
    )
    footer_style = ParagraphStyle(
        'CWFooter',
        fontName='Helvetica',
        fontSize=7,
        textColor=MID_GREY,
        alignment=TA_CENTER,
        spaceBefore=4*mm,
    )

    # ── En-tête : Logo + Info agence ─────────────────────────────────────────
    header_data = [[
        Paragraph('CINEMAWAY', title_style),
        Paragraph(
            '<b>FACTURE</b>',
            ParagraphStyle('inv', fontName='Helvetica-Bold', fontSize=28,
                           textColor=GOLD_DARK, alignment=TA_RIGHT)
        ),
    ]]
    header_table = Table(header_data, colWidths=[95*mm, 75*mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4*mm),
    ]))
    story.append(header_table)

    # Sous-titre agence
    story.append(Paragraph('Production Audiovisuelle · Marrakech, Maroc', subtitle_style))
    story.append(Paragraph(
        'cinemaway26@gmail.com  ·  +212 654 045 836  ·  ICE: 003766068000003',
        ParagraphStyle('meta', fontName='Helvetica', fontSize=8, textColor=MID_GREY, spaceAfter=4*mm)
    ))

    # Barre de séparation dorée
    story.append(HRFlowable(width='100%', thickness=2, color=GOLD, spaceAfter=6*mm))

    # ── Bloc : Références + Client ───────────────────────────────────────────
    now = datetime.now()
    ref_data = [
        [
            Paragraph('FACTURÉ À', label_style),
            Paragraph('', label_style),
            Paragraph('RÉFÉRENCES', label_style),
        ],
        [
            Paragraph(f"<b>{client.get('name','')}</b>", value_style),
            Paragraph('', value_style),
            Paragraph(f"N° Facture : <b>{transaction.get('reference','—')}</b>", value_style),
        ],
        [
            Paragraph(client.get('company',''), value_style),
            Paragraph('', value_style),
            Paragraph(f"Commande : <b>{order.get('reference','—')}</b>", value_style),
        ],
        [
            Paragraph(client.get('email',''), value_style),
            Paragraph('', value_style),
            Paragraph(f"Date : <b>{now.strftime('%d/%m/%Y')}</b>", value_style),
        ],
        [
            Paragraph(client.get('phone') or '', value_style),
            Paragraph('', value_style),
            Paragraph(f"Méthode : <b>{transaction.get('method','—').capitalize()}</b>", value_style),
        ],
    ]
    ref_table = Table(ref_data, colWidths=[80*mm, 20*mm, 70*mm])
    ref_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2*mm),
        ('BACKGROUND', (0,0), (-1,0), LIGHT_GREY),
        ('TOPPADDING', (0,0), (-1,0), 2*mm),
        ('BOTTOMPADDING', (0,0), (-1,0), 2*mm),
    ]))
    story.append(ref_table)
    story.append(Spacer(1, 6*mm))

    # ── Tableau des prestations ───────────────────────────────────────────────
    story.append(Paragraph('DÉTAIL DES PRESTATIONS', section_style))

    service = order.get('service', {}) or {}
    amount  = transaction.get('amount', 0)

    items_data = [
        ['#', 'Prestation', 'Catégorie', 'Montant (MAD)'],
        [
            '01',
            order.get('title', service.get('name', '—')),
            _cat_label(service.get('category', '')),
            f"{amount:,} MAD",
        ],
    ]

    items_table = Table(items_data, colWidths=[10*mm, 85*mm, 40*mm, 35*mm])
    items_table.setStyle(TableStyle([
        # En-tête
        ('BACKGROUND',    (0,0), (-1,0), DARK_BG),
        ('TEXTCOLOR',     (0,0), (-1,0), GOLD),
        ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0,0), (-1,0), 9),
        ('TOPPADDING',    (0,0), (-1,0), 3*mm),
        ('BOTTOMPADDING', (0,0), (-1,0), 3*mm),
        # Corps
        ('FONTNAME',      (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',      (0,1), (-1,-1), 9),
        ('TOPPADDING',    (0,1), (-1,-1), 3*mm),
        ('BOTTOMPADDING', (0,1), (-1,-1), 3*mm),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [white, LIGHT_GREY]),
        ('ALIGN',         (3,0), (3,-1), 'RIGHT'),
        ('ALIGN',         (0,0), (0,-1), 'CENTER'),
        ('GRID',          (0,0), (-1,-1), 0.5, HexColor('#DDDDDD')),
        ('LINEBELOW',     (0,0), (-1,0), 1.5, GOLD),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 4*mm))

    # ── Totaux ───────────────────────────────────────────────────────────────
    tva_rate = 0.20
    ht       = round(amount / (1 + tva_rate))
    tva      = amount - ht

    totals_data = [
        ['', 'Sous-total HT :', f"{ht:,} MAD"],
        ['', 'TVA (20%) :',     f"{tva:,} MAD"],
        ['', 'TOTAL TTC :',     f"{amount:,} MAD"],
    ]
    totals_table = Table(totals_data, colWidths=[95*mm, 45*mm, 30*mm])
    totals_table.setStyle(TableStyle([
        ('FONTNAME',      (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE',      (0,0), (-1,1), 9),
        ('FONTNAME',      (1,2), (-1,2), 'Helvetica-Bold'),
        ('FONTSIZE',      (1,2), (-1,2), 12),
        ('TEXTCOLOR',     (1,2), (-1,2), GOLD_DARK),
        ('ALIGN',         (1,0), (-1,-1), 'RIGHT'),
        ('TOPPADDING',    (0,0), (-1,-1), 2*mm),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2*mm),
        ('LINEABOVE',     (1,2), (-1,2), 1.5, GOLD),
        ('BACKGROUND',    (1,2), (-1,2), LIGHT_GREY),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 8*mm))

    # ── Description du projet ─────────────────────────────────────────────────
    if order.get('description'):
        story.append(Paragraph('DESCRIPTION DU PROJET', section_style))
        story.append(Paragraph(order['description'], value_style))
        story.append(Spacer(1, 4*mm))

    # ── Statut de paiement ────────────────────────────────────────────────────
    status_color = HexColor('#27AE60') if transaction.get('status') == 'paid' else HexColor('#E74C3C')
    status_label = 'PAYÉ' if transaction.get('status') == 'paid' else 'EN ATTENTE'
    status_data = [[
        Paragraph(
            f'<font color="#{status_color.hexval()[2:]}"><b>● {status_label}</b></font>',
            ParagraphStyle('st', fontName='Helvetica-Bold', fontSize=12, alignment=TA_CENTER)
        )
    ]]
    status_table = Table(status_data, colWidths=[170*mm])
    status_table.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), LIGHT_GREY),
        ('TOPPADDING',    (0,0), (-1,-1), 3*mm),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3*mm),
        ('ROUNDEDCORNERS', [3*mm]),
    ]))
    story.append(status_table)

    # ── Pied de page ─────────────────────────────────────────────────────────
    story.append(HRFlowable(width='100%', thickness=1, color=GOLD, spaceBefore=8*mm, spaceAfter=3*mm))
    story.append(Paragraph(
        'CINEMAWAY Production Agency · Appt 15 Imm 12 Lot SINE ALLAL EL FASSI, Marrakech\n'
        'ICE: 003766068000003 · IF: 67003158 · TP: 45316886 · RC Marrakech N°145536\n'
        'Merci de votre confiance. Tout litige doit être signalé dans les 30 jours suivant réception.',
        footer_style
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def _cat_label(cat: str) -> str:
    mapping = {
        'montage':    'Montage Vidéo',
        'production': 'Production',
        'pub':        'Film Publicitaire',
        'doc':        'Documentaire',
        'social':     'Réseaux Sociaux',
        'complement': 'Complémentaire',
    }
    return mapping.get(cat, cat.capitalize())
