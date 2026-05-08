"""
CINEMAWAY - Routes étendues
Intègre : factures PDF, notifications email, export CSV admin
À importer dans app.py via :  from routes_extended import register_extended_routes
"""

from flask import Blueprint, send_file, jsonify, session, request
import io, csv
from datetime import datetime
from functools import wraps

bp = Blueprint('extended', __name__)


def _login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if 'user_id' not in session:
            return jsonify({'error': 'Non authentifié'}), 401
        return f(*a, **kw)
    return d


def _admin_required(f):
    @wraps(f)
    def d(*a, **kw):
        if 'user_id' not in session:
            return jsonify({'error': 'Non authentifié'}), 401
        from app import User
        u = User.query.get(session['user_id'])
        if not u or u.role != 'admin':
            return jsonify({'error': 'Accès refusé'}), 403
        return f(*a, **kw)
    return d


# ─── Facture PDF ─────────────────────────────────────────────────────────────

@bp.route('/api/orders/<int:oid>/invoice')
@_login_required
def download_invoice(oid):
    """Génère et retourne la facture PDF de la dernière transaction."""
    from app import Order, Transaction, User
    from invoice import generate_invoice

    order = Order.query.get_or_404(oid)
    user  = User.query.get(session['user_id'])
    if user.role != 'admin' and order.client_id != user.id:
        return jsonify({'error': 'Accès refusé'}), 403

    txn = Transaction.query.filter_by(order_id=oid, status='paid').order_by(
        Transaction.created_at.desc()
    ).first()
    if not txn:
        return jsonify({'error': 'Aucun paiement trouvé'}), 404

    pdf_bytes = generate_invoice(order.to_dict(), txn.to_dict(), order.client.to_dict())
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Facture_{txn.reference}.pdf"
    )


# ─── Envoi facture par email ──────────────────────────────────────────────────

@bp.route('/api/orders/<int:oid>/invoice/send', methods=['POST'])
@_login_required
def send_invoice_email(oid):
    from app import Order, Transaction, User
    from invoice import generate_invoice
    from notifications import send_invoice

    order = Order.query.get_or_404(oid)
    user  = User.query.get(session['user_id'])
    if user.role != 'admin' and order.client_id != user.id:
        return jsonify({'error': 'Accès refusé'}), 403

    txn = Transaction.query.filter_by(order_id=oid, status='paid').order_by(
        Transaction.created_at.desc()
    ).first()
    if not txn:
        return jsonify({'error': 'Aucun paiement trouvé'}), 404

    pdf_bytes = generate_invoice(order.to_dict(), txn.to_dict(), order.client.to_dict())
    ok = send_invoice(order.to_dict(), txn.to_dict(), order.client.to_dict(), pdf_bytes)
    return jsonify({'message': 'Facture envoyée' if ok else 'Erreur envoi email'})


# ─── Notifications automatiques ──────────────────────────────────────────────

@bp.route('/api/orders/<int:oid>/notify-status', methods=['POST'])
@_admin_required
def notify_status(oid):
    """Envoie un email au client après changement de statut."""
    from app import Order
    from notifications import send_status_update

    order = Order.query.get_or_404(oid)
    data  = request.get_json()
    new_status = data.get('status', order.status)
    ok = send_status_update(order.to_dict(), order.client.to_dict(), new_status)
    return jsonify({'message': 'Notification envoyée' if ok else 'Erreur'})


# ─── Export CSV (Admin) ───────────────────────────────────────────────────────

@bp.route('/api/admin/export/orders')
@_admin_required
def export_orders_csv():
    """Exporte toutes les commandes en CSV."""
    from app import Order

    orders = Order.query.order_by(Order.created_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Référence', 'Client', 'Email', 'Service', 'Titre',
        'Budget (MAD)', 'Statut', 'Avancement (%)', 'Date création'
    ])
    for o in orders:
        writer.writerow([
            o.reference,
            o.client.name,
            o.client.email,
            o.service.name if o.service else '—',
            o.title,
            o.budget or '—',
            o.status,
            o.progress,
            o.created_at.strftime('%Y-%m-%d %H:%M'),
        ])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"commandes_cinemaway_{datetime.now().strftime('%Y%m%d')}.csv"
    )


@bp.route('/api/admin/export/clients')
@_admin_required
def export_clients_csv():
    """Exporte tous les clients en CSV."""
    from app import User, Order, Transaction, db

    clients = User.query.filter_by(role='client').all()
    output  = io.StringIO()
    writer  = csv.writer(output)
    writer.writerow([
        'Nom', 'Email', 'Téléphone', 'Entreprise',
        'Nb Commandes', 'CA Total (MAD)', 'Inscrit le'
    ])
    for c in clients:
        nb_orders = Order.query.filter_by(client_id=c.id).count()
        revenue   = db.session.query(db.func.sum(Transaction.amount))\
            .join(Order, Transaction.order_id == Order.id)\
            .filter(Order.client_id == c.id, Transaction.status == 'paid')\
            .scalar() or 0
        writer.writerow([
            c.name, c.email, c.phone or '—', c.company or '—',
            nb_orders, revenue, c.created_at.strftime('%Y-%m-%d')
        ])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"clients_cinemaway_{datetime.now().strftime('%Y%m%d')}.csv"
    )


# ─── Stats détaillées Admin ───────────────────────────────────────────────────

@bp.route('/api/admin/stats/revenue')
@_admin_required
def revenue_stats():
    """Revenus mensuels des 12 derniers mois."""
    from app import Transaction, db
    from sqlalchemy import extract

    results = db.session.query(
        extract('year',  Transaction.paid_at).label('year'),
        extract('month', Transaction.paid_at).label('month'),
        db.func.sum(Transaction.amount).label('total')
    ).filter(
        Transaction.status == 'paid',
        Transaction.paid_at.isnot(None)
    ).group_by('year', 'month').order_by('year', 'month').limit(12).all()

    months_fr = ['Jan','Fév','Mar','Avr','Mai','Jun','Jul','Aoû','Sep','Oct','Nov','Déc']
    data = [
        {
            'label': f"{months_fr[int(r.month)-1]} {int(r.year)}",
            'total': int(r.total or 0)
        }
        for r in results
    ]
    return jsonify(data)


@bp.route('/api/admin/stats/services')
@_admin_required
def service_stats():
    """Répartition des commandes par catégorie de service."""
    from app import Order, Service, db

    results = db.session.query(
        Service.category,
        db.func.count(Order.id).label('count')
    ).join(Order, Order.service_id == Service.id)\
     .group_by(Service.category).all()

    labels = {
        'montage':    'Montage Vidéo',
        'production': 'Production',
        'pub':        'Film Publicitaire',
        'doc':        'Documentaire',
        'social':     'Réseaux Sociaux',
        'complement': 'Complémentaire',
    }
    return jsonify([
        {'category': labels.get(r.category, r.category), 'count': r.count}
        for r in results
    ])


# ─── Enregistrement dans app ──────────────────────────────────────────────────

def register_extended_routes(app):
    app.register_blueprint(bp)
