"""
CINEMAWAY v2 — CLI de gestion
Usage: python manage.py <commande>

Commandes:
  runserver        Lance le serveur (avec WebSocket)
  create-admin     Crée un administrateur
  reset-db         Recrée la base de données
  seed             Données de démonstration
  stats            Statistiques générales
  list-orders      Liste les commandes
  list-clients     Liste les clients
  set-status       Change le statut d'une commande
  export           Export JSON complet
  clean-uploads    Supprime les fichiers uploadés orphelins
  shell            Shell Python interactif
"""

import sys, os, json
from datetime import datetime, timedelta
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import (app, db, User, Service, Order, Message,
                 Review, Transaction, OrderFile, Notification, socketio)


def colored(t, c):
    codes = {'green':'\033[92m','red':'\033[91m','yellow':'\033[93m',
             'gold':'\033[33m','reset':'\033[0m','bold':'\033[1m','dim':'\033[2m'}
    return f"{codes.get(c,'')}{t}{codes['reset']}"

def ok(m):   print(f"  {colored('✅','green')}  {m}")
def err(m):  print(f"  {colored('✗','red')}  {colored(m,'red')}")
def info(m): print(f"  {colored('›','gold')}  {m}")
def warn(m): print(f"  {colored('⚠','yellow')}  {colored(m,'yellow')}")
def head(m): print(f"\n  {colored(m,'bold')}\n  {'─'*len(m)}")

def table(headers, rows):
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    fmt = '  ' + '  '.join(f'{{:<{w}}}' for w in widths)
    sep = '  ' + '  '.join('─'*w for w in widths)
    print(colored(fmt.format(*headers), 'bold'))
    print(colored(sep, 'dim'))
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))


def cmd_runserver():
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'
    print(f"\n  {colored('CINEMAWAY v2','bold')} — Uploads · WebSocket · Push · PDF")
    info(f"Démarrage sur http://0.0.0.0:{port}")
    info("WebSocket activé — Ctrl+C pour arrêter\n")
    socketio.run(app, host='0.0.0.0', port=port, debug=debug,
                 allow_unsafe_werkzeug=True)


def cmd_create_admin():
    head("Créer un administrateur")
    with app.app_context():
        name     = input("  Nom complet : ").strip() or "CINEMAWAY Admin"
        email    = input("  Email       : ").strip()
        password = input("  Mot de passe: ").strip()
        if not email or not password:
            err("Email et mot de passe requis."); return
        if User.query.filter_by(email=email).first():
            err(f"Email {email} déjà utilisé."); return
        admin = User(name=name, email=email, role='admin')
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        ok(f"Admin créé : {email}")


def cmd_reset_db():
    head("Réinitialisation de la base de données")
    warn("Cette action efface TOUTES les données !")
    confirm = input("  Tapez 'CONFIRMER' : ").strip()
    if confirm != 'CONFIRMER':
        info("Annulé."); return
    with app.app_context():
        db.drop_all()
        db.create_all()
        from app import seed_admin, seed_services
        seed_admin(); seed_services()
        ok("Base réinitialisée.")
        ok("Admin : admin@cinemaway.ma / cinemaway2024")
    upload_dir = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
    for sub in ['briefs', 'deliverables']:
        folder = os.path.join(upload_dir, sub)
        if os.path.exists(folder):
            for f in os.listdir(folder):
                path = os.path.join(folder, f)
                if os.path.isfile(path): os.remove(path)
    ok("Uploads nettoyés.")


def cmd_seed():
    head("Injection de données de démonstration")
    clients_data = [
        {"name":"Karim Mansouri","email":"karim@marquex.ma","company":"Marque X","phone":"+212 661 234 567"},
        {"name":"Sara Benali","email":"sara@startupY.ma","company":"Startup Y","phone":"+212 662 345 678"},
        {"name":"Ahmed Rahmani","email":"ahmed@ong-atlas.ma","company":"ONG Atlas","phone":"+212 663 456 789"},
        {"name":"Fatima Alaoui","email":"fatima@medialab.ma","company":"Media Lab","phone":"+212 664 567 890"},
        {"name":"Youssef Chraibi","email":"youssef@brandco.ma","company":"Brand Co.","phone":"+212 665 678 901"},
    ]
    statuses   = ['pending','in_progress','review','completed','completed']
    progresses = [0, 40, 80, 100, 100]
    msgs_demo  = [
        "Bonjour, pouvez-vous me donner plus de détails sur le calendrier ?",
        "Bien sûr ! Nous commençons la semaine prochaine.",
        "Parfait. Avez-vous reçu notre brief créatif ?",
    ]
    with app.app_context():
        services = Service.query.all()
        if not services:
            err("Aucun service. Lancez : python manage.py reset-db"); return
        admin   = User.query.filter_by(role='admin').first()
        created = 0
        for cd in clients_data:
            if User.query.filter_by(email=cd['email']).first():
                info(f"Ignoré : {cd['email']}"); continue
            client = User(**cd)
            client.set_password('demo1234')
            db.session.add(client)
            db.session.flush()
            nb = random.randint(1, 2)
            for j in range(nb):
                svc    = random.choice(services)
                status = statuses[j % len(statuses)]
                prog   = progresses[j % len(progresses)]
                order  = Order(
                    client_id=client.id, service_id=svc.id,
                    title=f"Projet {svc.name} — {cd['company']}",
                    description=f"Brief de démonstration pour {cd['company']}.",
                    budget=random.choice([5000, 8000, 12000, 15000, 25000]),
                    deadline=(datetime.now()+timedelta(days=random.randint(14,60))).date(),
                    status=status, progress=prog,
                    notes_admin="Projet en bonne voie." if prog > 0 else "",
                )
                db.session.add(order)
                db.session.flush()
                order.generate_reference()
                for k, content in enumerate(msgs_demo):
                    sender = client if k % 2 == 0 else admin
                    db.session.add(Message(order_id=order.id, sender_id=sender.id, content=content))
                if status == 'completed' and order.budget:
                    db.session.add(Transaction(
                        order_id=order.id, amount=order.budget, method='virement',
                        status='paid', reference=f"PAY-DEMO-{order.id:04d}",
                        paid_at=datetime.utcnow()
                    ))
                    db.session.add(Review(
                        order_id=order.id, client_id=client.id,
                        rating=random.randint(4, 5),
                        comment="Excellent travail, équipe très professionnelle !"
                    ))
                db.session.add(Notification(
                    user_id=client.id,
                    title="👋 Bienvenue chez CINEMAWAY !",
                    body="Votre compte démo est prêt.", icon="🎬"
                ))
            db.session.commit()
            created += 1
            ok(f"{cd['name']} ({cd['email']}) / demo1234")
        if created:
            ok(f"\n  {created} client(s) créés avec commandes, messages et notifications.")
        else:
            warn("Tous les clients existaient déjà.")


def cmd_stats():
    head("Statistiques CINEMAWAY v2")
    with app.app_context():
        tc  = User.query.filter_by(role='client').count()
        ta  = User.query.filter_by(role='admin').count()
        to  = Order.query.count()
        ts  = Service.query.filter_by(active=True).count()
        tm  = Message.query.count()
        tr  = Review.query.count()
        tf  = OrderFile.query.count()
        tn  = Notification.query.count()
        rev = db.session.query(db.func.sum(Transaction.amount)).filter_by(status='paid').scalar() or 0
        sts = {s: Order.query.filter_by(status=s).count()
               for s in ['pending','in_progress','review','completed','cancelled']}
        upload_dir = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
        total_size, file_count = 0, 0
        for root, _, files in os.walk(upload_dir):
            for f in files:
                try:
                    total_size += os.path.getsize(os.path.join(root, f))
                    file_count += 1
                except: pass
        size_mb = total_size / 1024 / 1024
        print(f"""
  ┌────────────────────────────────────────┐
  │  {colored('Utilisateurs','bold'):<38} │
  │  Clients          : {colored(str(tc),'gold'):<27} │
  │  Administrateurs  : {colored(str(ta),'gold'):<27} │
  ├────────────────────────────────────────┤
  │  {colored('Commandes','bold'):<38} │
  │  Total            : {colored(str(to),'gold'):<27} │
  │  En attente       : {str(sts['pending']):<27} │
  │  En cours         : {str(sts['in_progress']):<27} │
  │  Terminées        : {colored(str(sts['completed']),'green'):<36} │
  ├────────────────────────────────────────┤
  │  {colored('Activité & Stockage','bold'):<38} │
  │  Messages         : {str(tm):<27} │
  │  Avis clients     : {str(tr):<27} │
  │  Notifications    : {str(tn):<27} │
  │  Fichiers uploadés: {colored(f'{tf} ({file_count} sur disque)','gold'):<36} │
  │  Espace utilisé   : {colored(f'{size_mb:.1f} MB','gold'):<36} │
  │  Revenu total     : {colored(f'{rev:,} MAD','gold'):<36} │
  └────────────────────────────────────────┘""")


def cmd_list_orders():
    head("Liste des commandes")
    with app.app_context():
        orders = Order.query.order_by(Order.created_at.desc()).all()
        if not orders: warn("Aucune commande."); return
        table(
            ['ID','Référence','Client','Service','Budget','Statut','Avanc.','📎'],
            [(o.id, o.reference or '—',
              (o.client.name[:16] if o.client else '—'),
              (o.service.name[:18] if o.service else '—'),
              f"{o.budget:,}" if o.budget else '—',
              o.status, f"{o.progress}%", len(o.files)) for o in orders]
        )
        print(f"\n  {len(orders)} commande(s).")


def cmd_list_clients():
    head("Liste des clients")
    with app.app_context():
        clients = User.query.filter_by(role='client').order_by(User.created_at.desc()).all()
        if not clients: warn("Aucun client."); return
        table(
            ['ID','Nom','Email','Entreprise','Commandes','Inscrit le'],
            [(c.id, c.name[:22], c.email[:28], (c.company or '—')[:18],
              Order.query.filter_by(client_id=c.id).count(),
              c.created_at.strftime('%Y-%m-%d')) for c in clients]
        )
        print(f"\n  {len(clients)} client(s).")


def cmd_set_status():
    head("Modifier le statut d'une commande")
    statuses = ['pending','in_progress','review','completed','cancelled']
    with app.app_context():
        try: oid = int(input("  ID de la commande : ").strip())
        except ValueError: err("ID invalide."); return
        o = Order.query.get(oid)
        if not o: err(f"Commande #{oid} introuvable."); return
        info(f"Commande : {o.reference} — {o.title}")
        info(f"Statut actuel : {o.status}")
        print(f"\n  Statuts disponibles :")
        for i, s in enumerate(statuses, 1):
            print(f"    {i}. {s}")
        try:
            choice = int(input("\n  Choix (1-5) : ").strip()) - 1
            new_status = statuses[choice]
        except (ValueError, IndexError): err("Choix invalide."); return
        prog_map = {'pending':0,'in_progress':30,'review':80,'completed':100,'cancelled':0}
        o.status = new_status
        o.progress = prog_map.get(new_status, o.progress)
        o.updated_at = datetime.utcnow()
        db.session.commit()
        ok(f"Mis à jour : {o.reference} → {new_status}")


def cmd_export():
    head("Export des données")
    with app.app_context():
        data = {
            'exported_at': datetime.utcnow().isoformat(),
            'version': 'v2',
            'clients':  [u.to_dict() for u in User.query.filter_by(role='client').all()],
            'services': [s.to_dict() for s in Service.query.all()],
            'orders':   [o.to_dict() for o in Order.query.all()],
            'reviews':  [r.to_dict() for r in Review.query.all()],
        }
        fn = f"cinemaway_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        ok(f"Export créé : {fn}")
        info(f"{len(data['clients'])} clients, {len(data['orders'])} commandes")


def cmd_clean_uploads():
    head("Nettoyage des fichiers orphelins")
    with app.app_context():
        upload_dir = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
        db_urls = {f.url for f in OrderFile.query.all()}
        db_urls |= {u.avatar_url for u in User.query.all() if u.avatar_url}
        removed = 0
        for sub in ['briefs', 'deliverables', 'avatars']:
            folder = os.path.join(upload_dir, sub)
            if not os.path.exists(folder): continue
            for fname in os.listdir(folder):
                path = os.path.join(folder, fname)
                url  = f"/static/uploads/{sub}/{fname}"
                if url not in db_urls:
                    os.remove(path); removed += 1
        ok(f"{removed} fichier(s) orphelin(s) supprimé(s).")


def cmd_shell():
    head("Shell Python CINEMAWAY v2")
    info("Variables : app, db, User, Service, Order, Message, Review, Transaction, OrderFile, Notification, socketio")
    import code
    with app.app_context():
        code.interact(local={
            'app':app,'db':db,'socketio':socketio,
            'User':User,'Service':Service,'Order':Order,
            'Message':Message,'Review':Review,'Transaction':Transaction,
            'OrderFile':OrderFile,'Notification':Notification,
        }, banner='')


COMMANDS = {
    'runserver':     cmd_runserver,
    'create-admin':  cmd_create_admin,
    'reset-db':      cmd_reset_db,
    'seed':          cmd_seed,
    'stats':         cmd_stats,
    'list-orders':   cmd_list_orders,
    'list-clients':  cmd_list_clients,
    'set-status':    cmd_set_status,
    'export':        cmd_export,
    'clean-uploads': cmd_clean_uploads,
    'shell':         cmd_shell,
}

if __name__ == '__main__':
    print(f"\n  {colored('CINEMAWAY v2','bold')} — Uploads · WebSocket · Push · PDF\n")
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(0)
    command = sys.argv[1].lower()
    if command not in COMMANDS:
        err(f"Commande inconnue : '{command}'")
        info("Tapez 'python manage.py' pour voir les commandes."); sys.exit(1)
    try:
        COMMANDS[command]()
    except KeyboardInterrupt:
        print(f"\n\n  {colored('Interruption.','dim')}\n")
    except Exception as e:
        err(f"Erreur : {e}")
        import traceback; traceback.print_exc(); sys.exit(1)
