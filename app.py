"""
CINEMAWAY v2 — Application principale
Nouvelles fonctionnalités :
  - Upload fichiers (images/vidéos/PDFs) via Cloudinary ou stockage local
  - WebSocket (Flask-SocketIO) pour messagerie en temps réel
  - Notifications push navigateur (Web Push API)
  - Factures PDF téléchargeables et fonctionnelles
  - Base de données PostgreSQL (en ligne, multi-PC)
  - CORS activé pour accès depuis n'importe où
"""

import os, uuid, json
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (Flask, render_template, request, jsonify,
                   session, send_file, redirect, url_for)
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ─── App setup ───────────────────────────────────────────────
app = Flask(__name__)

# ─── Config ──────────────────────────────────────────────────
app.config.update(
    SECRET_KEY            = os.environ.get('SECRET_KEY', 'cinemaway-dev-secret-2024'),
    # PostgreSQL en prod, SQLite en dev
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///cinemaway.db'
    ).replace('postgres://', 'postgresql://'),   # fix Railway
    SQLALCHEMY_TRACK_MODIFICATIONS = False,
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True},
    MAX_CONTENT_LENGTH    = 500 * 1024 * 1024,   # 500 MB max upload
    UPLOAD_FOLDER         = os.path.join(os.path.dirname(__file__), 'static', 'uploads'),
    ALLOWED_EXTENSIONS    = {'png','jpg','jpeg','gif','webp','mp4','mov','avi','mkv',
                             'pdf','doc','docx','xls','xlsx','zip','rar'},
)

# CORS — permet l'accès depuis n'importe quel domaine
CORS(app, supports_credentials=True)

db       = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet',
                    logger=False, engineio_logger=False)

# Assurer que le dossier uploads existe
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
for sub in ['briefs', 'avatars', 'deliverables']:
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], sub), exist_ok=True)


# ═══════════════════════════════════════════════════════════
#  MODÈLES
# ═══════════════════════════════════════════════════════════

class User(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    uid           = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    name          = db.Column(db.String(120), nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    phone         = db.Column(db.String(30))
    company       = db.Column(db.String(120))
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20), default='client')
    avatar_url    = db.Column(db.String(300))
    push_sub      = db.Column(db.Text)          # subscription push JSON
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    orders        = db.relationship('Order', backref='client', lazy=True,
                                    foreign_keys='Order.client_id')
    messages      = db.relationship('Message', backref='sender', lazy=True)

    def set_password(self, pw):  self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

    def to_dict(self):
        return dict(id=self.id, uid=self.uid, name=self.name, email=self.email,
                    phone=self.phone, company=self.company, role=self.role,
                    avatar_url=self.avatar_url,
                    created_at=self.created_at.isoformat())


class Service(db.Model):
    __tablename__ = 'services'
    id          = db.Column(db.Integer, primary_key=True)
    category    = db.Column(db.String(60), nullable=False)
    name        = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    price_min   = db.Column(db.Integer, nullable=False)
    price_max   = db.Column(db.Integer, nullable=False)
    duration    = db.Column(db.String(60))
    pack_level  = db.Column(db.String(20))
    active      = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return dict(id=self.id, category=self.category, name=self.name,
                    description=self.description, price_min=self.price_min,
                    price_max=self.price_max, duration=self.duration,
                    pack_level=self.pack_level)


class Order(db.Model):
    __tablename__ = 'orders'
    id           = db.Column(db.Integer, primary_key=True)
    reference    = db.Column(db.String(30), unique=True)
    client_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    service_id   = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    service      = db.relationship('Service')
    title        = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text)
    budget       = db.Column(db.Integer)
    deadline     = db.Column(db.Date)
    status       = db.Column(db.String(30), default='pending')
    progress     = db.Column(db.Integer, default=0)
    notes_admin  = db.Column(db.Text)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow,
                              onupdate=datetime.utcnow)
    # Relations
    messages     = db.relationship('Message',     backref='order', lazy=True)
    reviews      = db.relationship('Review',      backref='order', lazy=True)
    transactions = db.relationship('Transaction', backref='order', lazy=True)
    files        = db.relationship('OrderFile',   backref='order', lazy=True)

    def generate_reference(self):
        self.reference = f"CW-{datetime.now().strftime('%Y%m')}-{self.id:04d}"

    def to_dict(self):
        return dict(
            id=self.id, reference=self.reference, title=self.title,
            description=self.description, budget=self.budget,
            deadline=self.deadline.isoformat() if self.deadline else None,
            status=self.status, progress=self.progress,
            notes_admin=self.notes_admin,
            service=self.service.to_dict() if self.service else None,
            client=self.client.to_dict() if self.client else None,
            files=[f.to_dict() for f in self.files],
            created_at=self.created_at.isoformat(),
            updated_at=self.updated_at.isoformat() if self.updated_at else None,
        )


class OrderFile(db.Model):
    """Fichiers uploadés par le client ou livrés par l'admin."""
    __tablename__ = 'order_files'
    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    uploader_id= db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploader   = db.relationship('User')
    filename   = db.Column(db.String(300), nullable=False)
    url        = db.Column(db.String(500), nullable=False)
    file_type  = db.Column(db.String(20))   # image | video | pdf | doc | other
    size_kb    = db.Column(db.Integer)
    is_deliverable = db.Column(db.Boolean, default=False)  # livrable final
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return dict(id=self.id, order_id=self.order_id,
                    uploader=self.uploader.to_dict(),
                    filename=self.filename, url=self.url,
                    file_type=self.file_type, size_kb=self.size_kb,
                    is_deliverable=self.is_deliverable,
                    created_at=self.created_at.isoformat())


class Message(db.Model):
    __tablename__ = 'messages'
    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    sender_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content    = db.Column(db.Text, nullable=False)
    file_url   = db.Column(db.String(500))   # pièce jointe optionnelle
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return dict(id=self.id, order_id=self.order_id,
                    sender=self.sender.to_dict(), content=self.content,
                    file_url=self.file_url, is_read=self.is_read,
                    created_at=self.created_at.isoformat())


class Review(db.Model):
    __tablename__ = 'reviews'
    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    client_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating     = db.Column(db.Integer, nullable=False)
    comment    = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        u = User.query.get(self.client_id)
        return dict(id=self.id, rating=self.rating, comment=self.comment,
                    client=u.to_dict() if u else None,
                    created_at=self.created_at.isoformat())


class Transaction(db.Model):
    __tablename__ = 'transactions'
    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    amount     = db.Column(db.Integer, nullable=False)
    method     = db.Column(db.String(40), default='virement')
    status     = db.Column(db.String(20), default='pending')
    reference  = db.Column(db.String(80))
    paid_at    = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return dict(id=self.id, order_id=self.order_id, amount=self.amount,
                    method=self.method, status=self.status,
                    reference=self.reference,
                    paid_at=self.paid_at.isoformat() if self.paid_at else None,
                    created_at=self.created_at.isoformat())


class Notification(db.Model):
    """Notifications en base pour l'historique."""
    __tablename__ = 'notifications'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user       = db.relationship('User')
    title      = db.Column(db.String(200), nullable=False)
    body       = db.Column(db.Text)
    icon       = db.Column(db.String(10), default='🎬')
    link       = db.Column(db.String(200))
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return dict(id=self.id, title=self.title, body=self.body,
                    icon=self.icon, link=self.link, is_read=self.is_read,
                    created_at=self.created_at.isoformat())


# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════

def allowed_file(filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in app.config['ALLOWED_EXTENSIONS']

def file_type_from_ext(filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext in {'png','jpg','jpeg','gif','webp'}:    return 'image'
    if ext in {'mp4','mov','avi','mkv','webm'}:     return 'video'
    if ext in {'pdf'}:                              return 'pdf'
    if ext in {'doc','docx','xls','xlsx'}:          return 'doc'
    return 'other'

def save_file_local(file, subfolder='briefs'):
    """Sauvegarde un fichier localement et retourne l'URL relative."""
    filename = secure_filename(file.filename)
    unique   = f"{uuid.uuid4().hex}_{filename}"
    folder   = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
    os.makedirs(folder, exist_ok=True)
    path     = os.path.join(folder, unique)
    file.save(path)
    size_kb  = os.path.getsize(path) // 1024
    url      = f"/static/uploads/{subfolder}/{unique}"
    return url, size_kb

def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if 'user_id' not in session:
            return jsonify({'error': 'Non authentifié'}), 401
        return f(*a, **kw)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a, **kw):
        if 'user_id' not in session:
            return jsonify({'error': 'Non authentifié'}), 401
        u = User.query.get(session['user_id'])
        if not u or u.role != 'admin':
            return jsonify({'error': 'Accès refusé'}), 403
        return f(*a, **kw)
    return d

def current_user():
    return User.query.get(session.get('user_id'))


# ═══════════════════════════════════════════════════════════
#  NOTIFICATIONS (push + base)
# ═══════════════════════════════════════════════════════════

def create_notification(user_id, title, body, icon='🎬', link=None):
    """Crée une notification en base ET l'envoie via WebSocket."""
    notif = Notification(user_id=user_id, title=title, body=body,
                         icon=icon, link=link)
    db.session.add(notif)
    db.session.commit()
    # Envoyer via WebSocket en temps réel
    socketio.emit('notification', notif.to_dict(), room=f"user_{user_id}")
    return notif


# ═══════════════════════════════════════════════════════════
#  ROUTES — PAGES
# ═══════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/uploads/<path:filename>')
def serve_upload(filename):
    upload_dir = app.config['UPLOAD_FOLDER']
    return send_file(os.path.join(upload_dir, filename))


# ═══════════════════════════════════════════════════════════
#  ROUTES — AUTH
# ═══════════════════════════════════════════════════════════

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    if not all(k in data for k in ['name', 'email', 'password']):
        return jsonify({'error': 'Champs requis manquants'}), 400
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email déjà utilisé'}), 409
    u = User(name=data['name'], email=data['email'],
             phone=data.get('phone',''), company=data.get('company',''))
    u.set_password(data['password'])
    db.session.add(u)
    db.session.commit()
    session['user_id'] = u.id
    # Notification de bienvenue
    create_notification(u.id, '👋 Bienvenue chez CINEMAWAY !',
                        'Votre compte est créé. Commandez votre premier projet.')
    return jsonify({'message': 'Compte créé', 'user': u.to_dict()}), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    u = User.query.filter_by(email=data.get('email')).first()
    if not u or not u.check_password(data.get('password', '')):
        return jsonify({'error': 'Identifiants incorrects'}), 401
    session['user_id'] = u.id
    session.permanent = True
    return jsonify({'message': 'Connecté', 'user': u.to_dict()})


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Déconnecté'})


@app.route('/api/auth/me')
@login_required
def me():
    return jsonify(current_user().to_dict())


@app.route('/api/auth/update', methods=['PUT'])
@login_required
def update_profile():
    u    = current_user()
    data = request.get_json()
    for f in ['name', 'phone', 'company']:
        if f in data: setattr(u, f, data[f])
    if data.get('password'):
        u.set_password(data['password'])
    db.session.commit()
    return jsonify({'message': 'Profil mis à jour', 'user': u.to_dict()})


@app.route('/api/auth/avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier'}), 400
    file = request.files['file']
    if not allowed_file(file.filename):
        return jsonify({'error': 'Format non supporté'}), 400
    url, _ = save_file_local(file, 'avatars')
    u = current_user()
    u.avatar_url = url
    db.session.commit()
    return jsonify({'url': url})


# ═══════════════════════════════════════════════════════════
#  ROUTES — PUSH SUBSCRIPTION
# ═══════════════════════════════════════════════════════════

@app.route('/api/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    """Enregistre la subscription push navigateur."""
    data = request.get_json()
    u = current_user()
    u.push_sub = json.dumps(data)
    db.session.commit()
    return jsonify({'message': 'Subscription enregistrée'})


@app.route('/api/notifications')
@login_required
def get_notifications():
    u = current_user()
    notifs = Notification.query.filter_by(user_id=u.id)\
        .order_by(Notification.created_at.desc()).limit(30).all()
    return jsonify([n.to_dict() for n in notifs])


@app.route('/api/notifications/<int:nid>/read', methods=['PUT'])
@login_required
def mark_read(nid):
    n = Notification.query.get_or_404(nid)
    if n.user_id != session['user_id']:
        return jsonify({'error': 'Accès refusé'}), 403
    n.is_read = True
    db.session.commit()
    return jsonify({'message': 'Lu'})


@app.route('/api/notifications/read-all', methods=['PUT'])
@login_required
def mark_all_read():
    Notification.query.filter_by(user_id=session['user_id'], is_read=False)\
        .update({'is_read': True})
    db.session.commit()
    return jsonify({'message': 'Tout marqué comme lu'})


# ═══════════════════════════════════════════════════════════
#  ROUTES — SERVICES
# ═══════════════════════════════════════════════════════════

@app.route('/api/services')
def get_services():
    cat = request.args.get('category')
    q   = Service.query.filter_by(active=True)
    if cat: q = q.filter_by(category=cat)
    return jsonify([s.to_dict() for s in q.all()])

@app.route('/api/services/<int:sid>')
def get_service(sid):
    return jsonify(Service.query.get_or_404(sid).to_dict())

@app.route('/api/services', methods=['POST'])
@admin_required
def create_service():
    s = Service(**request.get_json())
    db.session.add(s); db.session.commit()
    return jsonify(s.to_dict()), 201

@app.route('/api/services/<int:sid>', methods=['PUT'])
@admin_required
def update_service(sid):
    s = Service.query.get_or_404(sid)
    for k,v in request.get_json().items(): setattr(s, k, v)
    db.session.commit()
    return jsonify(s.to_dict())

@app.route('/api/services/<int:sid>', methods=['DELETE'])
@admin_required
def delete_service(sid):
    Service.query.get_or_404(sid).active = False
    db.session.commit()
    return jsonify({'message': 'Désactivé'})


# ═══════════════════════════════════════════════════════════
#  ROUTES — COMMANDES
# ═══════════════════════════════════════════════════════════

@app.route('/api/orders', methods=['POST'])
@login_required
def create_order():
    # Supporte multipart (avec fichiers) ET JSON
    if request.content_type and 'multipart' in request.content_type:
        service_id  = int(request.form.get('service_id', 0))
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '')
        budget      = int(request.form.get('budget', 0)) or None
        deadline_s  = request.form.get('deadline', '')
    else:
        data        = request.get_json()
        service_id  = int(data.get('service_id', 0))
        title       = data.get('title', '').strip()
        description = data.get('description', '')
        budget      = data.get('budget')
        deadline_s  = data.get('deadline', '')

    if not service_id or not title:
        return jsonify({'error': 'service_id et title requis'}), 400

    deadline = None
    if deadline_s:
        try: deadline = datetime.strptime(deadline_s, '%Y-%m-%d').date()
        except: pass

    order = Order(client_id=session['user_id'], service_id=service_id,
                  title=title, description=description,
                  budget=budget, deadline=deadline)
    db.session.add(order)
    db.session.flush()
    order.generate_reference()

    # Sauvegarder les fichiers uploadés
    files_saved = []
    if request.files:
        for key in request.files:
            for f in request.files.getlist(key):
                if f and f.filename and allowed_file(f.filename):
                    url, size_kb = save_file_local(f, 'briefs')
                    of = OrderFile(
                        order_id    = order.id,
                        uploader_id = session['user_id'],
                        filename    = secure_filename(f.filename),
                        url         = url,
                        file_type   = file_type_from_ext(f.filename),
                        size_kb     = size_kb,
                    )
                    db.session.add(of)
                    files_saved.append(of)

    db.session.commit()

    # Notifier les admins
    admins = User.query.filter_by(role='admin').all()
    for admin in admins:
        create_notification(admin.id, '📥 Nouvelle commande',
                            f"{order.client.name} — {title}",
                            icon='📋', link=f'/admin/orders/{order.id}')

    return jsonify({'message': 'Commande créée', 'order': order.to_dict()}), 201


@app.route('/api/orders')
@login_required
def list_orders():
    u = current_user()
    if u.role == 'admin':
        orders = Order.query.order_by(Order.created_at.desc()).all()
    else:
        orders = Order.query.filter_by(client_id=u.id)\
                      .order_by(Order.created_at.desc()).all()
    return jsonify([o.to_dict() for o in orders])


@app.route('/api/orders/<int:oid>')
@login_required
def get_order(oid):
    o = Order.query.get_or_404(oid)
    u = current_user()
    if u.role != 'admin' and o.client_id != u.id:
        return jsonify({'error': 'Accès refusé'}), 403
    return jsonify(o.to_dict())


@app.route('/api/orders/<int:oid>/status', methods=['PUT'])
@admin_required
def update_order_status(oid):
    o    = Order.query.get_or_404(oid)
    data = request.get_json()
    old_status = o.status
    if 'status'      in data: o.status      = data['status']
    if 'progress'    in data: o.progress    = data['progress']
    if 'notes_admin' in data: o.notes_admin = data['notes_admin']
    o.updated_at = datetime.utcnow()
    db.session.commit()

    # Notifier le client
    status_labels = {
        'pending':     'En attente', 'in_progress': 'En production',
        'review':      'En révision', 'completed':   'Livré ✅',
        'cancelled':   'Annulé'
    }
    if o.status != old_status:
        create_notification(
            o.client_id,
            f'📢 Projet mis à jour — {status_labels.get(o.status, o.status)}',
            f'Votre projet "{o.title}" est maintenant : {status_labels.get(o.status, o.status)}',
            icon='🎬', link=f'/orders/{o.id}'
        )
    return jsonify({'message': 'Mis à jour', 'order': o.to_dict()})


@app.route('/api/orders/<int:oid>/cancel', methods=['PUT'])
@login_required
def cancel_order(oid):
    o = Order.query.get_or_404(oid)
    u = current_user()
    if u.role != 'admin' and o.client_id != u.id:
        return jsonify({'error': 'Accès refusé'}), 403
    if o.status not in ('pending',):
        return jsonify({'error': 'Impossible d\'annuler'}), 400
    o.status = 'cancelled'
    db.session.commit()
    return jsonify({'message': 'Annulé'})


# ═══════════════════════════════════════════════════════════
#  ROUTES — UPLOAD FICHIERS
# ═══════════════════════════════════════════════════════════

@app.route('/api/orders/<int:oid>/files', methods=['POST'])
@login_required
def upload_order_files(oid):
    """Upload de fichiers sur une commande existante."""
    o = Order.query.get_or_404(oid)
    u = current_user()
    if u.role != 'admin' and o.client_id != u.id:
        return jsonify({'error': 'Accès refusé'}), 403
    if 'files' not in request.files:
        return jsonify({'error': 'Aucun fichier envoyé'}), 400

    saved = []
    is_deliverable = request.form.get('is_deliverable', 'false') == 'true'
    subfolder = 'deliverables' if is_deliverable else 'briefs'

    for f in request.files.getlist('files'):
        if not f or not f.filename: continue
        if not allowed_file(f.filename):
            continue
        url, size_kb = save_file_local(f, subfolder)
        of = OrderFile(
            order_id       = oid,
            uploader_id    = u.id,
            filename       = secure_filename(f.filename),
            url            = url,
            file_type      = file_type_from_ext(f.filename),
            size_kb        = size_kb,
            is_deliverable = is_deliverable,
        )
        db.session.add(of)
        saved.append(of)

    db.session.commit()

    # Notifications croisées
    if saved:
        if u.role == 'admin':
            # Admin a livré des fichiers → notifier client
            create_notification(
                o.client_id, '📦 Nouveau livrable disponible !',
                f'{len(saved)} fichier(s) ajouté(s) à votre projet "{o.title}"',
                icon='📁', link=f'/orders/{oid}'
            )
        else:
            # Client a uploadé des fichiers → notifier admins
            admins = User.query.filter_by(role='admin').all()
            for admin in admins:
                create_notification(
                    admin.id, '📎 Nouveaux fichiers reçus',
                    f'{o.client.name} a uploadé {len(saved)} fichier(s) sur "{o.title}"',
                    icon='📁', link=f'/admin/orders/{oid}'
                )
        # Émettre via WebSocket pour mise à jour temps réel
        socketio.emit('files_updated', {
            'order_id': oid,
            'files': [f.to_dict() for f in saved]
        }, room=f"order_{oid}")

    return jsonify({'message': f'{len(saved)} fichier(s) uploadé(s)',
                    'files': [f.to_dict() for f in saved]}), 201


@app.route('/api/orders/<int:oid>/files')
@login_required
def get_order_files(oid):
    o = Order.query.get_or_404(oid)
    u = current_user()
    if u.role != 'admin' and o.client_id != u.id:
        return jsonify({'error': 'Accès refusé'}), 403
    return jsonify([f.to_dict() for f in o.files])


@app.route('/api/orders/<int:oid>/files/<int:fid>', methods=['DELETE'])
@login_required
def delete_order_file(oid, fid):
    of = OrderFile.query.get_or_404(fid)
    u  = current_user()
    if u.role != 'admin' and of.uploader_id != u.id:
        return jsonify({'error': 'Accès refusé'}), 403
    # Supprimer le fichier physique si local
    if of.url.startswith('/static/uploads/'):
        path = os.path.join(os.path.dirname(__file__), of.url.lstrip('/'))
        if os.path.exists(path): os.remove(path)
    db.session.delete(of)
    db.session.commit()
    return jsonify({'message': 'Fichier supprimé'})


# ═══════════════════════════════════════════════════════════
#  ROUTES — MESSAGES
# ═══════════════════════════════════════════════════════════

@app.route('/api/orders/<int:oid>/messages')
@login_required
def get_messages(oid):
    o = Order.query.get_or_404(oid)
    u = current_user()
    if u.role != 'admin' and o.client_id != u.id:
        return jsonify({'error': 'Accès refusé'}), 403
    msgs = Message.query.filter_by(order_id=oid)\
                  .order_by(Message.created_at).all()
    # Marquer comme lus
    for m in msgs:
        if m.sender_id != u.id: m.is_read = True
    db.session.commit()
    return jsonify([m.to_dict() for m in msgs])


@app.route('/api/orders/<int:oid>/messages', methods=['POST'])
@login_required
def send_message(oid):
    o = Order.query.get_or_404(oid)
    u = current_user()
    if u.role != 'admin' and o.client_id != u.id:
        return jsonify({'error': 'Accès refusé'}), 403

    content  = ''
    file_url = None

    if request.content_type and 'multipart' in request.content_type:
        content = request.form.get('content', '').strip()
        if 'file' in request.files:
            f = request.files['file']
            if f and allowed_file(f.filename):
                file_url, _ = save_file_local(f, 'briefs')
    else:
        data    = request.get_json()
        content = data.get('content', '').strip()

    if not content and not file_url:
        return jsonify({'error': 'Message vide'}), 400

    msg = Message(order_id=oid, sender_id=u.id,
                  content=content, file_url=file_url)
    db.session.add(msg)
    db.session.commit()

    msg_dict = msg.to_dict()

    # Émettre via WebSocket en temps réel
    socketio.emit('new_message', msg_dict, room=f"order_{oid}")

    # Notifier l'autre partie
    recipient_id = o.client_id if u.role == 'admin' else \
                   User.query.filter_by(role='admin').first().id
    if recipient_id:
        preview = content[:80] + ('…' if len(content) > 80 else '')
        create_notification(
            recipient_id,
            f'💬 Nouveau message — {o.reference or o.title}',
            f'{u.name} : {preview}',
            icon='💬', link=f'/orders/{oid}'
        )

    return jsonify(msg_dict), 201


# ═══════════════════════════════════════════════════════════
#  ROUTES — PAIEMENTS & FACTURES
# ═══════════════════════════════════════════════════════════

@app.route('/api/orders/<int:oid>/pay', methods=['POST'])
@login_required
def create_payment(oid):
    o = Order.query.get_or_404(oid)
    u = current_user()
    if u.role != 'admin' and o.client_id != u.id:
        return jsonify({'error': 'Accès refusé'}), 403
    data = request.get_json()
    txn = Transaction(
        order_id  = oid,
        amount    = data.get('amount', o.budget or 0),
        method    = data.get('method', 'virement'),
        status    = 'paid',
        reference = f"PAY-{datetime.now().strftime('%Y%m%d%H%M%S')}-{oid}",
        paid_at   = datetime.utcnow(),
    )
    db.session.add(txn)
    db.session.commit()
    # Notifier le client
    create_notification(o.client_id, '💳 Paiement confirmé',
                        f'Paiement de {txn.amount:,} MAD reçu pour "{o.title}"',
                        icon='✅', link=f'/orders/{oid}')
    return jsonify({'message': 'Paiement enregistré',
                    'transaction': txn.to_dict()}), 201


@app.route('/api/orders/<int:oid>/transactions')
@login_required
def get_transactions(oid):
    o = Order.query.get_or_404(oid)
    u = current_user()
    if u.role != 'admin' and o.client_id != u.id:
        return jsonify({'error': 'Accès refusé'}), 403
    return jsonify([t.to_dict() for t in
                    Transaction.query.filter_by(order_id=oid).all()])


@app.route('/api/orders/<int:oid>/invoice')
@login_required
def download_invoice(oid):
    """Génère et retourne la facture PDF — FONCTIONNEL."""
    from invoice import generate_invoice
    o = Order.query.get_or_404(oid)
    u = current_user()
    if u.role != 'admin' and o.client_id != u.id:
        return jsonify({'error': 'Accès refusé'}), 403
    txn = Transaction.query.filter_by(order_id=oid, status='paid')\
                     .order_by(Transaction.created_at.desc()).first()
    if not txn:
        # Générer une facture pro-forma si pas de paiement
        txn_dict = {'reference': f'PROFORMA-{oid}', 'amount': o.budget or 0,
                    'method': '—', 'status': 'proforma', 'paid_at': None}
    else:
        txn_dict = txn.to_dict()
    pdf_bytes = generate_invoice(o.to_dict(), txn_dict, o.client.to_dict())
    import io
    ref = txn_dict.get('reference', f'PROFORMA-{oid}')
    return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                     as_attachment=True,
                     download_name=f"Facture_{ref}.pdf")


# ═══════════════════════════════════════════════════════════
#  ROUTES — AVIS
# ═══════════════════════════════════════════════════════════

@app.route('/api/orders/<int:oid>/review', methods=['POST'])
@login_required
def submit_review(oid):
    o = Order.query.get_or_404(oid)
    u = current_user()
    if o.client_id != u.id:
        return jsonify({'error': 'Accès refusé'}), 403
    if o.status not in ('completed', 'delivered'):
        return jsonify({'error': 'Commande non terminée'}), 400
    if Review.query.filter_by(order_id=oid, client_id=u.id).first():
        return jsonify({'error': 'Avis déjà soumis'}), 409
    data = request.get_json()
    rev  = Review(order_id=oid, client_id=u.id,
                  rating=data.get('rating', 5), comment=data.get('comment',''))
    db.session.add(rev)
    db.session.commit()
    return jsonify(rev.to_dict()), 201


@app.route('/api/reviews')
def get_reviews():
    revs = Review.query.order_by(Review.created_at.desc()).limit(20).all()
    return jsonify([r.to_dict() for r in revs])


# ═══════════════════════════════════════════════════════════
#  ROUTES — ADMIN
# ═══════════════════════════════════════════════════════════

@app.route('/api/admin/stats')
@admin_required
def admin_stats():
    total_orders  = Order.query.count()
    pending       = Order.query.filter_by(status='pending').count()
    in_progress   = Order.query.filter_by(status='in_progress').count()
    completed     = Order.query.filter_by(status='completed').count()
    total_clients = User.query.filter_by(role='client').count()
    total_revenue = db.session.query(db.func.sum(Transaction.amount))\
                              .filter_by(status='paid').scalar() or 0
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    return jsonify(dict(total_orders=total_orders, pending=pending,
                        in_progress=in_progress, completed=completed,
                        total_clients=total_clients, total_revenue=total_revenue,
                        recent_orders=[o.to_dict() for o in recent_orders]))


@app.route('/api/admin/clients')
@admin_required
def admin_clients():
    clients = User.query.filter_by(role='client')\
                  .order_by(User.created_at.desc()).all()
    return jsonify([c.to_dict() for c in clients])


@app.route('/api/admin/notify-client', methods=['POST'])
@admin_required
def admin_notify_client():
    """Envoie une notification manuelle à un client."""
    data = request.get_json()
    create_notification(
        data['user_id'],
        data.get('title', 'Message de CINEMAWAY'),
        data.get('body', ''),
        icon=data.get('icon', '🎬'),
    )
    return jsonify({'message': 'Notification envoyée'})


import csv, io as _io
@app.route('/api/admin/export/orders')
@admin_required
def export_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    out    = _io.StringIO()
    w      = csv.writer(out)
    w.writerow(['Référence','Client','Email','Service','Titre',
                'Budget','Statut','Avancement','Date'])
    for o in orders:
        w.writerow([o.reference, o.client.name, o.client.email,
                    o.service.name if o.service else '—',
                    o.title, o.budget or '—', o.status, f'{o.progress}%',
                    o.created_at.strftime('%Y-%m-%d %H:%M')])
    out.seek(0)
    return send_file(
        _io.BytesIO(out.getvalue().encode('utf-8-sig')),
        mimetype='text/csv', as_attachment=True,
        download_name=f"commandes_{datetime.now().strftime('%Y%m%d')}.csv"
    )


@app.route('/api/admin/export/clients')
@admin_required
def export_clients():
    clients = User.query.filter_by(role='client').all()
    out     = _io.StringIO()
    w       = csv.writer(out)
    w.writerow(['Nom','Email','Téléphone','Entreprise','Commandes','Inscrit le'])
    for c in clients:
        w.writerow([c.name, c.email, c.phone or '—', c.company or '—',
                    Order.query.filter_by(client_id=c.id).count(),
                    c.created_at.strftime('%Y-%m-%d')])
    out.seek(0)
    return send_file(
        _io.BytesIO(out.getvalue().encode('utf-8-sig')),
        mimetype='text/csv', as_attachment=True,
        download_name=f"clients_{datetime.now().strftime('%Y%m%d')}.csv"
    )


# ═══════════════════════════════════════════════════════════
#  WEBSOCKET EVENTS
# ═══════════════════════════════════════════════════════════

@socketio.on('connect')
def on_connect():
    if 'user_id' in session:
        u = User.query.get(session['user_id'])
        if u:
            join_room(f"user_{u.id}")
            emit('connected', {'user_id': u.id, 'name': u.name})

@socketio.on('disconnect')
def on_disconnect():
    if 'user_id' in session:
        leave_room(f"user_{session['user_id']}")

@socketio.on('join_order')
def on_join_order(data):
    """Client/admin rejoint le room d'une commande pour le chat temps réel."""
    oid = data.get('order_id')
    if oid and 'user_id' in session:
        u = User.query.get(session['user_id'])
        o = Order.query.get(oid)
        if o and (u.role == 'admin' or o.client_id == u.id):
            join_room(f"order_{oid}")
            emit('joined_order', {'order_id': oid})

@socketio.on('leave_order')
def on_leave_order(data):
    oid = data.get('order_id')
    if oid: leave_room(f"order_{oid}")

@socketio.on('typing')
def on_typing(data):
    """Indicateur de frappe en temps réel."""
    oid = data.get('order_id')
    if oid and 'user_id' in session:
        u = User.query.get(session['user_id'])
        emit('user_typing', {'name': u.name if u else '—'},
             room=f"order_{oid}", include_self=False)


# ═══════════════════════════════════════════════════════════
#  SEED & INIT
# ═══════════════════════════════════════════════════════════

def seed_services():
    if Service.query.count() > 0: return
    services = [
        ('montage','Montage Simple','Coupes et transitions basiques',800,1500,'3-5 jours',None),
        ('montage','Montage Avancé','Effets, storytelling, sound design',1500,3000,'5-10 jours',None),
        ('montage','Montage Publicitaire','Vidéo optimisée Reels, TikTok',2000,4000,'5-7 jours',None),
        ('montage','Montage Cinématographique','Color grading + narration pro',3000,7000,'7-14 jours',None),
        ('production','Tournage Demi-Journée','1 caméra, 4h de tournage',2000,4000,'1 jour',None),
        ('production','Tournage Journée Complète','Matériel + équipe',4000,8000,'1 jour',None),
        ('production','Tournage Multi-Caméras','Setup professionnel',8000,15000,'1-3 jours',None),
        ('pub','Pack Basic','Vidéo courte simple',5000,8000,'7-10 jours','basic'),
        ('pub','Pack Pro','Concept + tournage + montage avancé',8000,15000,'14-21 jours','pro'),
        ('pub','Pack Premium','Production cinématographique complète',15000,30000,'30-60 jours','premium'),
        ('doc','Mini Documentaire','3 à 5 minutes',7000,12000,'14-21 jours',None),
        ('doc','Documentaire Standard','5 à 15 minutes',12000,25000,'30-45 jours',None),
        ('doc','Documentaire Premium','Projet artistique complet',25000,60000,'60-90 jours',None),
        ('social','Vidéo Courte (Reels)','15 à 30 secondes',500,1200,'2-3 jours',None),
        ('social','Pack 5 Vidéos','Contenu optimisé réseaux sociaux',2000,5000,'7-14 jours',None),
        ('social','Pack Mensuel','Création régulière de contenu',5000,15000,'Mensuel',None),
        ('complement','Voice-over','Narration professionnelle',500,1500,'1-3 jours',None),
        ('complement','Sous-titres','Sous-titrage professionnel',200,800,'1-2 jours',None),
        ('complement','Color Grading Avancé','Étalonnage cinématographique',500,2000,'2-5 jours',None),
        ('complement','Script / Storytelling','Rédaction et narration créative',1000,3000,'3-7 jours',None),
    ]
    for cat,name,desc,pmin,pmax,dur,pack in services:
        db.session.add(Service(category=cat,name=name,description=desc,
                               price_min=pmin,price_max=pmax,
                               duration=dur,pack_level=pack))
    db.session.commit()
    print("✅ 20 services chargés")

def seed_admin():
    if User.query.filter_by(role='admin').first(): return
    a = User(name='CINEMAWAY Admin', email='admin@cinemaway.ma', role='admin')
    a.set_password('cinemaway2024')
    db.session.add(a)
    db.session.commit()
    print("✅ Admin créé : admin@cinemaway.ma / cinemaway2024")

with app.app_context():
    db.create_all()
    seed_admin()
    seed_services()
    from routes_extended import register_extended_routes
    register_extended_routes(app)

if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'
    socketio.run(app, host='0.0.0.0', port=port, debug=debug)
