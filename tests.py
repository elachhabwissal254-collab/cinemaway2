"""
CINEMAWAY — Tests unitaires
Lancer : python -m pytest tests.py -v
"""

import pytest
import json
from app import app, db, User, Service, Order


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SECRET_KEY'] = 'test-secret'
    app.config['ADMIN_EMAIL'] = 'admin@test.com'
    app.config['ADMIN_PASSWORD'] = 'testpass'
    with app.app_context():
        db.create_all()
        _seed_test_data()
    with app.test_client() as c:
        yield c


def _seed_test_data():
    """Crée données de test minimales."""
    admin = User(name='Admin Test', email='admin@test.com', role='admin')
    admin.set_password('testpass')
    db.session.add(admin)
    svc = Service(
        category='montage', name='Montage Test',
        description='Service test', price_min=1000, price_max=2000
    )
    db.session.add(svc)
    db.session.commit()


def reg(c, name='Test User', email='test@test.com', pw='password123'):
    return c.post('/api/auth/register', json={
        'name': name, 'email': email, 'password': pw
    })


def login(c, email='admin@test.com', pw='testpass'):
    return c.post('/api/auth/login', json={'email': email, 'password': pw})


# ── Auth tests ────────────────────────────────────────────────────

class TestAuth:
    def test_register_success(self, client):
        r = reg(client)
        assert r.status_code == 201
        data = r.get_json()
        assert 'user' in data
        assert data['user']['role'] == 'client'

    def test_register_duplicate_email(self, client):
        reg(client)
        r = reg(client)
        assert r.status_code == 409

    def test_register_missing_fields(self, client):
        r = client.post('/api/auth/register', json={'email': 'x@x.com'})
        assert r.status_code == 400

    def test_login_success(self, client):
        r = login(client)
        assert r.status_code == 200
        assert 'user' in r.get_json()

    def test_login_wrong_password(self, client):
        r = login(client, pw='wrongpass')
        assert r.status_code == 401

    def test_login_unknown_email(self, client):
        r = client.post('/api/auth/login', json={'email': 'nobody@x.com', 'password': 'x'})
        assert r.status_code == 401

    def test_me_authenticated(self, client):
        login(client)
        r = client.get('/api/auth/me')
        assert r.status_code == 200
        assert r.get_json()['role'] == 'admin'

    def test_me_unauthenticated(self, client):
        r = client.get('/api/auth/me')
        assert r.status_code == 401

    def test_logout(self, client):
        login(client)
        r = client.post('/api/auth/logout')
        assert r.status_code == 200
        r = client.get('/api/auth/me')
        assert r.status_code == 401


# ── Services tests ────────────────────────────────────────────────

class TestServices:
    def test_list_services(self, client):
        r = client.get('/api/services')
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_filter_services_by_category(self, client):
        r = client.get('/api/services?category=montage')
        assert r.status_code == 200
        data = r.get_json()
        assert all(s['category'] == 'montage' for s in data)

    def test_create_service_as_admin(self, client):
        login(client)
        r = client.post('/api/services', json={
            'category': 'social', 'name': 'Reel Test',
            'description': 'Test', 'price_min': 500, 'price_max': 1200
        })
        assert r.status_code == 201

    def test_create_service_as_client_forbidden(self, client):
        reg(client, email='client2@test.com')
        login(client, email='client2@test.com', pw='password123')
        r = client.post('/api/services', json={
            'category': 'social', 'name': 'Reel', 'price_min': 500, 'price_max': 1200
        })
        assert r.status_code == 403


# ── Orders tests ──────────────────────────────────────────────────

class TestOrders:
    def _svc_id(self, client):
        svcs = client.get('/api/services').get_json()
        return svcs[0]['id']

    def test_create_order(self, client):
        reg(client, email='ord@test.com')
        login(client, email='ord@test.com', pw='password123')
        sid = self._svc_id(client)
        r = client.post('/api/orders', json={
            'service_id': sid, 'title': 'Mon premier film',
            'description': 'Brief test', 'budget': 5000
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data['order']['reference'].startswith('CW-')

    def test_list_orders_client(self, client):
        reg(client, email='lst@test.com')
        login(client, email='lst@test.com', pw='password123')
        sid = self._svc_id(client)
        client.post('/api/orders', json={'service_id': sid, 'title': 'Projet A', 'budget': 2000})
        r = client.get('/api/orders')
        assert r.status_code == 200
        assert len(r.get_json()) >= 1

    def test_create_order_missing_fields(self, client):
        reg(client, email='miss@test.com')
        login(client, email='miss@test.com', pw='password123')
        r = client.post('/api/orders', json={'title': 'Aucun service'})
        assert r.status_code == 400

    def test_admin_update_status(self, client):
        reg(client, email='upd@test.com')
        login(client, email='upd@test.com', pw='password123')
        sid = self._svc_id(client)
        oid = client.post('/api/orders', json={'service_id': sid, 'title': 'Proj B', 'budget': 3000}).get_json()['order']['id']
        login(client)  # re-login as admin
        r = client.put(f'/api/orders/{oid}/status', json={'status': 'in_progress', 'progress': 30})
        assert r.status_code == 200
        assert r.get_json()['order']['status'] == 'in_progress'

    def test_cancel_pending_order(self, client):
        reg(client, email='cnc@test.com')
        login(client, email='cnc@test.com', pw='password123')
        sid = self._svc_id(client)
        oid = client.post('/api/orders', json={'service_id': sid, 'title': 'Annuler', 'budget': 1000}).get_json()['order']['id']
        r = client.put(f'/api/orders/{oid}/cancel')
        assert r.status_code == 200

    def test_get_order_unauthorized(self, client):
        reg(client, email='a1@test.com')
        login(client, email='a1@test.com', pw='password123')
        sid = self._svc_id(client)
        oid = client.post('/api/orders', json={'service_id': sid, 'title': 'Privé', 'budget': 1000}).get_json()['order']['id']
        reg(client, email='a2@test.com')
        login(client, email='a2@test.com', pw='password123')
        r = client.get(f'/api/orders/{oid}')
        assert r.status_code == 403


# ── Messages tests ────────────────────────────────────────────────

class TestMessages:
    def _create_order(self, client, email):
        reg(client, email=email)
        login(client, email=email, pw='password123')
        sid = client.get('/api/services').get_json()[0]['id']
        return client.post('/api/orders', json={'service_id': sid, 'title': 'Chat test'}).get_json()['order']['id']

    def test_send_and_read_message(self, client):
        oid = self._create_order(client, 'msg@test.com')
        r = client.post(f'/api/orders/{oid}/messages', json={'content': 'Bonjour !'})
        assert r.status_code == 201
        msgs = client.get(f'/api/orders/{oid}/messages').get_json()
        assert any(m['content'] == 'Bonjour !' for m in msgs)

    def test_empty_message_rejected(self, client):
        oid = self._create_order(client, 'emp@test.com')
        r = client.post(f'/api/orders/{oid}/messages', json={'content': ''})
        assert r.status_code == 400


# ── Payments tests ────────────────────────────────────────────────

class TestPayments:
    def test_create_payment(self, client):
        reg(client, email='pay@test.com')
        login(client, email='pay@test.com', pw='password123')
        sid = client.get('/api/services').get_json()[0]['id']
        oid = client.post('/api/orders', json={'service_id': sid, 'title': 'Paiement test', 'budget': 3000}).get_json()['order']['id']
        r = client.post(f'/api/orders/{oid}/pay', json={'amount': 3000, 'method': 'virement'})
        assert r.status_code == 201
        txn = r.get_json()['transaction']
        assert txn['status'] == 'paid'
        assert txn['reference'].startswith('PAY-')

    def test_get_transactions(self, client):
        reg(client, email='txn@test.com')
        login(client, email='txn@test.com', pw='password123')
        sid = client.get('/api/services').get_json()[0]['id']
        oid = client.post('/api/orders', json={'service_id': sid, 'title': 'Trans test', 'budget': 2000}).get_json()['order']['id']
        client.post(f'/api/orders/{oid}/pay', json={'amount': 2000, 'method': 'carte'})
        r = client.get(f'/api/orders/{oid}/transactions')
        assert r.status_code == 200
        assert len(r.get_json()) >= 1


# ── Admin tests ───────────────────────────────────────────────────

class TestAdmin:
    def test_admin_stats(self, client):
        login(client)
        r = client.get('/api/admin/stats')
        assert r.status_code == 200
        data = r.get_json()
        assert 'total_orders' in data
        assert 'total_revenue' in data

    def test_admin_stats_forbidden_for_client(self, client):
        reg(client, email='fbd@test.com')
        login(client, email='fbd@test.com', pw='password123')
        r = client.get('/api/admin/stats')
        assert r.status_code == 403

    def test_admin_clients_list(self, client):
        login(client)
        r = client.get('/api/admin/clients')
        assert r.status_code == 200

    def test_export_orders_csv(self, client):
        login(client)
        r = client.get('/api/admin/export/orders')
        assert r.status_code == 200
        assert 'csv' in r.content_type

    def test_export_clients_csv(self, client):
        login(client)
        r = client.get('/api/admin/export/clients')
        assert r.status_code == 200
        assert 'csv' in r.content_type


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
