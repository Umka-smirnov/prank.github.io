import json
import os
import random
import threading
import uuid
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, send_from_directory, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import customtkinter as ctk

app = Flask(__name__)
app.secret_key = 'kakoy-to-ochen-sekretniy-klyuch-12346'

SMS_RU_API_ID = 'ВСТАВЬ_СВОЙ_API_ID'
SMS_RU_FROM = ''

DATA_FILE = 'data.json'
TEAM_NAME = 'Команда Констурии'
GROUP_PREFIX = 'group:'

GAMES_GOAL = 2000

# Секретный код для получения прав библиотекаря
LIBRARIAN_CODE = 'KONSTURIA2026'

db_lock = threading.RLock()

pending_codes = {}
typing_state = {}

game_presence = {
    'snake': {},
    'tetris': {},
    'breakout': {}
}

def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data.setdefault('users', [])
                data.setdefault('messages', [])
                data.setdefault('groups', [])
                data.setdefault('books', [])
                data.setdefault('book_requests', [])
                data.setdefault('donated', 0)
                return data
        except Exception:
            return {'users': [], 'messages': [], 'groups': [], 'books': [], 'book_requests': [], 'donated': 0}
    return {'users': [], 'messages': [], 'groups': [], 'books': [], 'book_requests': [], 'donated': 0}


def save_db(db):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


db = load_db()


def is_group(recipient):
    return isinstance(recipient, str) and recipient.startswith(GROUP_PREFIX)


def get_group_id(recipient):
    return recipient[len(GROUP_PREFIX):]


def get_current_user():
    name = session.get('user')
    if not name:
        return None
    with db_lock:
        for u in db['users']:
            if u['name'] == name:
                return u
    return None


def send_code(phone, purpose, name=None):
    code = str(random.randint(1000, 9999))
    pending_codes[phone] = {
        'code': code,
        'expires': datetime.now() + timedelta(minutes=5),
        'name': name,
        'purpose': purpose
    }

    digits = ''.join(ch for ch in phone if ch.isdigit())
    if digits.startswith('8'):
        digits = '7' + digits[1:]
    elif digits.startswith('9') and len(digits) == 10:
        digits = '7' + digits

    text = f'Констурия: код подтверждения {code}. Действует 5 минут.'

    if not SMS_RU_API_ID or SMS_RU_API_ID == 'ВСТАВЬ_СВОЙ_API_ID':
        print(f'[Эмуляция] SMS на {phone}: {text}')
        return

    params = {
        'api_id': SMS_RU_API_ID,
        'to': digits,
        'msg': text,
        'json': 1
    }

    if SMS_RU_FROM:
        params['from'] = SMS_RU_FROM

    try:
        response = requests.get('https://sms.ru/sms/send', params=params, timeout=10)
        data = response.json()

        if data.get('status') == 'OK':
            print(f'SMS отправлено на {digits}, код {code}')
        else:
            print(f'Ошибка SMS.ru: {data}')
            print(f'(резерв) Код для {phone}: {code}')
    except Exception as e:
        print(f'Не удалось отправить SMS: {e}')
        print(f'(резерв) Код для {phone}: {code}')

@app.route('/olga')
def olga():
    return render_template('olga.html', title='Главная')

@app.route('/prank/gimn', methods=['GET', 'POST'])
def gimn():
    return render_template('gimn.html', title='Главная')

@app.route('/prank', methods=['GET', 'POST'])
def prank():
    return render_template('prank.html', title='Главная')

@app.route('/business_card/leo', methods=['GET', 'POST'])
def leo():
    return render_template('leo.html', title='Главная')

@app.before_request
def ensure_client_id():
    if 'client_id' not in session:
        session['client_id'] = uuid.uuid4().hex


@app.context_processor
def inject_user():
    current = session.get('user')
    librarian = False
    if current:
        with db_lock:
            for u in db['users']:
                if u['name'] == current:
                    librarian = u.get('is_librarian', False)
                    break
    return {'current_user': current, 'is_librarian': librarian}


@app.route('/')
def index():
    return render_template('page.html', page='home', title='Главная')


@app.route('/robots.txt')
def robots():
    return send_from_directory('templates', 'robots.txt')


@app.route('/chats')
def chats():
    return render_template('page.html', page='chats', title='Чаты')


@app.route('/library')
def library():
    return render_template('page.html', page='library', title='Библиотека')


@app.route('/games')
def games():
    with db_lock:
        donated = db.get('donated', 0)

    if donated >= GAMES_GOAL:
        return render_template('page.html', page='games_play', title='Игры')

    progress = min(100, int(donated / GAMES_GOAL * 100))
    return render_template('page.html', page='games', title='Игры',
                           donated=donated, goal=GAMES_GOAL, progress=progress)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        phone = (request.form.get('phone') or '').strip()
        name = (request.form.get('name') or '').strip()
        code = (request.form.get('code') or '').strip()

        if code:
            record = pending_codes.get(phone)

            if not record or record['purpose'] != 'register':
                return render_template('page.html', page='register', title='Регистрация',
                                       error='Код не найден. Попробуй снова.')

            if datetime.now() > record['expires']:
                pending_codes.pop(phone, None)
                return render_template('page.html', page='register', title='Регистрация',
                                       error='Код истёк. Попробуй снова.')

            if record['code'] != code:
                return render_template('page.html', page='register', title='Регистрация',
                                       error='Неверный код.', code_sent=True,
                                       phone=phone, name=name)

            pending_codes.pop(phone, None)

            with db_lock:
                for user in db['users']:
                    if user['phone'] == phone:
                        session['user'] = user['name']
                        return redirect('/login')

                new_user = {
                    'name': record.get('name') or name or 'Пользователь',
                    'phone': phone,
                    'history': [],
                    'last_read': {},
                    'is_librarian': False
                }
                db['users'].append(new_user)
                save_db(db)
                session['user'] = new_user['name']

            print('Зарегистрирован:', new_user['name'], phone)
            return redirect('/login')

        else:
            if not name:
                return render_template('page.html', page='register', title='Регистрация',
                                       error='Введи имя')

            if not phone or len(phone) < 5:
                return render_template('page.html', page='register', title='Регистрация',
                                       error='Введи корректный номер телефона')

            with db_lock:
                for user in db['users']:
                    if user['phone'] == phone:
                        return render_template('page.html', page='register', title='Регистрация',
                                               error='Такой номер уже зарегистрирован. Попробуй войти.')

            send_code(phone, 'register', name)
            return render_template('page.html', page='register', title='Регистрация',
                                   code_sent=True, phone=phone, name=name)

    return render_template('page.html', page='register', title='Регистрация')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = (request.form.get('phone') or '').strip()
        code = (request.form.get('code') or '').strip()

        if code:
            record = pending_codes.get(phone)

            if not record or record['purpose'] != 'login':
                return render_template('page.html', page='login', title='Вход',
                                       error='Код не найден. Попробуй снова.')

            if datetime.now() > record['expires']:
                pending_codes.pop(phone, None)
                return render_template('page.html', page='login', title='Вход',
                                       error='Код истёк. Попробуй снова.')

            if record['code'] != code:
                return render_template('page.html', page='login', title='Вход',
                                       error='Неверный код.', code_sent=True, phone=phone)

            pending_codes.pop(phone, None)

            with db_lock:
                for user in db['users']:
                    if user['phone'] == phone:
                        ip = request.remote_addr
                        time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        user['history'].append({'ip': ip, 'time': time_now})
                        save_db(db)
                        session['user'] = user['name']
                        print(f'Вход выполнен: {phone} | IP: {ip}')
                        return redirect('/login')

            return render_template('page.html', page='login', title='Вход',
                                   error='Номер не найден.')

        else:
            if not phone or len(phone) < 5:
                return render_template('page.html', page='login', title='Вход',
                                       error='Введи корректный номер телефона')

            with db_lock:
                found = any(user['phone'] == phone for user in db['users'])

            if not found:
                return render_template('page.html', page='login', title='Вход',
                                       error='Номер не найден. Зарегистрируйся.')

            send_code(phone, 'login')
            return render_template('page.html', page='login', title='Вход',
                                   code_sent=True, phone=phone)

    return render_template('page.html', page='login', title='Вход')


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')


@app.route('/api/users')
def api_users():
    current = session.get('user')
    if not current:
        return jsonify({'error': 'Нужно войти'}), 401
    with db_lock:
        names = [u['name'] for u in db['users'] if u['name'] != current]
    return jsonify(names)


@app.route('/api/groups', methods=['GET', 'POST'])
def api_groups():
    current = session.get('user')
    if not current:
        return jsonify({'error': 'Нужно войти'}), 401

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        members = data.get('members') or []

        if not name:
            return jsonify({'error': 'Введи название группы'}), 400
        if not members:
            return jsonify({'error': 'Добавь хотя бы одного участника'}), 400

        with db_lock:
            valid = [u['name'] for u in db['users'] if u['name'] != current]
            members = [m for m in members if m in valid]
            if not members:
                return jsonify({'error': 'Выбранные пользователи не найдены'}), 400

            group = {
                'id': uuid.uuid4().hex[:12],
                'name': name,
                'creator': current,
                'members': [current] + members,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            db['groups'].append(group)
            save_db(db)

            return jsonify({
                'id': group['id'],
                'recipient': GROUP_PREFIX + group['id'],
                'name': name,
                'members': group['members']
            }), 201

    with db_lock:
        groups = list(db['groups'])

    return jsonify([{
        'id': g['id'],
        'recipient': GROUP_PREFIX + g['id'],
        'name': g['name'],
        'members': g['members'],
        'creator': g['creator']
    } for g in groups if current in g['members']])


@app.route('/api/groups/<group_id>/leave', methods=['POST'])
def leave_group(group_id):
    current = session.get('user')
    if not current:
        return jsonify({'error': 'Нужно войти'}), 401

    with db_lock:
        for g in db['groups']:
            if g['id'] == group_id and current in g['members']:
                g['members'].remove(current)
                break
        else:
            return jsonify({'error': 'Группа не найдена'}), 404

        db['groups'] = [g for g in db['groups'] if g['members']]
        save_db(db)

    return jsonify({'success': True})


@app.route('/api/chats')
def api_chats():
    current = session.get('user')
    if not current:
        return jsonify({'error': 'Нужно войти'}), 401

    with db_lock:
        msgs = list(db['messages'])
        groups = list(db['groups'])

    partners = set()
    for m in msgs:
        s, r = m.get('sender'), m.get('recipient')
        if is_group(r):
            continue
        if s == current:
            partners.add(r)
        elif r == current:
            partners.add(s)
    partners.add(TEAM_NAME)

    personal = [TEAM_NAME] + sorted(p for p in partners if p != TEAM_NAME)

    my_groups = [{
        'id': g['id'],
        'recipient': GROUP_PREFIX + g['id'],
        'name': g['name'],
        'members': g['members']
    } for g in groups if current in g['members']]

    return jsonify({'personal': personal, 'groups': my_groups})


@app.route('/api/messages', methods=['GET', 'POST'])
def api_messages():
    current = session.get('user')
    if not current:
        return jsonify({'error': 'Нужно войти, чтобы пользоваться чатом'}), 401

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        text = (data.get('text') or '').strip()
        recipient = (data.get('recipient') or TEAM_NAME).strip()

        if not text:
            return jsonify({'error': 'Пустое сообщение'}), 400

        if is_group(recipient):
            with db_lock:
                group = next((g for g in db['groups'] if g['id'] == get_group_id(recipient)), None)
            if not group:
                return jsonify({'error': 'Группа не найдена'}), 404
            if current not in group['members']:
                return jsonify({'error': 'Ты не участник этой группы'}), 403

        message = {
            'sender': current,
            'recipient': recipient,
            'text': text,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        with db_lock:
            db['messages'].append(message)
            if len(db['messages']) > 1000:
                db['messages'] = db['messages'][-1000:]
            save_db(db)

        return jsonify(message), 201

    partner = request.args.get('with', TEAM_NAME)

    if is_group(partner):
        with db_lock:
            group = next((g for g in db['groups'] if g['id'] == get_group_id(partner)), None)
        if not group:
            return jsonify([])
        if current not in group['members']:
            return jsonify({'error': 'Нет доступа'}), 403

    with db_lock:
        msgs = list(db['messages'])

    conversation = []
    for m in msgs:
        s, r = m.get('sender'), m.get('recipient')
        if is_group(partner):
            if r == partner:
                conversation.append(m)
        else:
            if (s == current and r == partner) or (s == partner and r == current):
                conversation.append(m)

    with db_lock:
        for u in db['users']:
            if u['name'] == current:
                lr = u.setdefault('last_read', {})
                if lr.get(partner) != len(conversation):
                    lr[partner] = len(conversation)
                    save_db(db)
            break

    return jsonify(conversation)


@app.route('/api/unread')
def api_unread():
    current = session.get('user')
    if not current:
        return jsonify({})

    with db_lock:
        msgs = list(db['messages'])
        groups = list(db['groups'])
        me = next((u for u in db['users'] if u['name'] == current), None)

    last_read = (me or {}).get('last_read', {})
    result = {}

    partners = {TEAM_NAME}
    for m in msgs:
        s, r = m.get('sender'), m.get('recipient')
        if is_group(r):
            continue
        if s == current:
            partners.add(r)
        elif r == current:
            partners.add(s)

    for p in partners:
        count = sum(1 for m in msgs
                    if (m['sender'] == current and m['recipient'] == p)
                    or (m['sender'] == p and m['recipient'] == current))
        result[p] = max(0, count - last_read.get(p, 0))

    for g in groups:
        if current in g['members']:
            key = GROUP_PREFIX + g['id']
            count = sum(1 for m in msgs if m['recipient'] == key)
            result[key] = max(0, count - last_read.get(key, 0))

    return jsonify(result)


@app.route('/api/typing', methods=['GET', 'POST'])
def api_typing():
    current = session.get('user')
    if not current:
        return jsonify({'error': 'Нужно войти'}), 401

    now = datetime.now()

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        chat = data.get('chat', '')
        if not chat:
            return jsonify({'error': 'Нет чата'}), 400
        typing_state.setdefault(chat, {})[current] = now
        return jsonify({'success': True})

    chat = request.args.get('chat', '')
    active = []
    if chat in typing_state:
        for name, ts in list(typing_state[chat].items()):
            if (now - ts).total_seconds() < 3:
                if name != current:
                    active.append(name)
            else:
                del typing_state[chat][name]

    return jsonify(active)


# ---------- Игры ----------

@app.route('/api/games/presence', methods=['POST'])
def games_presence():
    data = request.get_json(silent=True) or {}
    game = data.get('game')
    client_id = session.get('client_id')

    if not client_id:
        return jsonify({'error': 'Нет идентификатора'}), 400

    now = datetime.now()
    with db_lock:
        for g in game_presence:
            game_presence[g].pop(client_id, None)
        if game in game_presence:
            game_presence[game][client_id] = now

    return jsonify({'success': True})


@app.route('/api/games/online')
def games_online():
    now = datetime.now()
    result = {}
    with db_lock:
        for game, players in game_presence.items():
            active = {cid: ts for cid, ts in players.items()
                      if (now - ts).total_seconds() < 10}
            game_presence[game] = active
            result[game] = len(active)
    return jsonify(result)


# ---------- Библиотека ----------

@app.route('/api/librarian/activate', methods=['POST'])
def librarian_activate():
    current = session.get('user')
    if not current:
        return jsonify({'error': 'Нужно войти в аккаунт'}), 401

    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()

    if code != LIBRARIAN_CODE:
        return jsonify({'error': 'Неверный секретный код'}), 403

    with db_lock:
        for u in db['users']:
            if u['name'] == current:
                u['is_librarian'] = True
                save_db(db)
                break

    print(f'{current} стал библиотекарем')
    return jsonify({'success': True})


@app.route('/api/books', methods=['GET', 'POST'])
def api_books():
    if request.method == 'POST':
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Нужно войти'}), 401
        if not user.get('is_librarian'):
            return jsonify({'error': 'Только библиотекарь может добавлять книги'}), 403

        data = request.get_json(silent=True) or {}
        title = (data.get('title') or '').strip()
        author = (data.get('author') or '').strip()
        image = (data.get('image') or '').strip()
        description = (data.get('description') or '').strip()
        available = data.get('available', True)
        holder = (data.get('holder') or '').strip()

        if not title or not author:
            return jsonify({'error': 'Введи название и автора книги'}), 400
        if not available and not holder:
            return jsonify({'error': 'Укажи, у кого книга, если её нет в наличии'}), 400

        book = {
            'id': uuid.uuid4().hex[:12],
            'title': title,
            'author': author,
            'image': image,
            'description': description,
            'available': bool(available),
            'holder': holder,
            'added_by': user['name'],
            'added_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        with db_lock:
            db.setdefault('books', []).append(book)
            save_db(db)

        print(f'Добавлена книга: {title} ({author})')
        return jsonify(book), 201

    with db_lock:
        books = list(db.get('books', []))
    return jsonify(books)


@app.route('/api/books/<book_id>', methods=['PUT', 'DELETE'])
def api_book_detail(book_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Нужно войти'}), 401
    if not user.get('is_librarian'):
        return jsonify({'error': 'Только библиотекарь может изменять книги'}), 403

    if request.method == 'DELETE':
        with db_lock:
            db['books'] = [b for b in db.get('books', []) if b['id'] != book_id]
            save_db(db)
        return jsonify({'success': True})

    data = request.get_json(silent=True) or {}

    with db_lock:
        for b in db.get('books', []):
            if b['id'] == book_id:
                if 'title' in data:
                    b['title'] = data['title'].strip()
                if 'author' in data:
                    b['author'] = data['author'].strip()
                if 'image' in data:
                    b['image'] = data['image'].strip()
                if 'description' in data:
                    b['description'] = data['description'].strip()
                if 'available' in data:
                    b['available'] = bool(data['available'])
                if 'holder' in data:
                    b['holder'] = data['holder'].strip()
                save_db(db)
                return jsonify(b)

    return jsonify({'error': 'Книга не найдена'}), 404


@app.route('/api/books/requests', methods=['GET', 'POST'])
def api_book_requests():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Нужно войти'}), 401

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        book_id = data.get('book_id')

        if not book_id:
            return jsonify({'error': 'Нет книги'}), 400

        with db_lock:
            book = next((b for b in db.get('books', []) if b['id'] == book_id), None)

        if not book:
            return jsonify({'error': 'Книга не найдена'}), 404
        if book['available']:
            return jsonify({'error': 'Книга уже в наличии'}), 400
        if not book['holder']:
            return jsonify({'error': 'Неизвестно, у кого книга'}), 400
        if book['holder'] == user['name']:
            return jsonify({'error': 'Книга уже у тебя'}), 400

        with db_lock:
            existing = next((r for r in db.get('book_requests', [])
                             if r['book_id'] == book_id
                             and r['from_user'] == user['name']
                             and r['status'] == 'pending'), None)

        if existing:
            return jsonify({'error': 'Ты уже отправил заявку на эту книгу'}), 400

        request_obj = {
            'id': uuid.uuid4().hex[:12],
            'book_id': book_id,
            'book_title': book['title'],
            'from_user': user['name'],
            'to_user': book['holder'],
            'status': 'pending',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        with db_lock:
            db.setdefault('book_requests', []).append(request_obj)
            save_db(db)

        print(f'Заявка на книгу: {user["name"]} хочет забрать "{book["title"]}" у {book["holder"]}')
        return jsonify(request_obj), 201

    with db_lock:
        all_requests = list(db.get('book_requests', []))

    incoming = [r for r in all_requests if r['to_user'] == user['name'] and r['status'] == 'pending']
    outgoing = [r for r in all_requests if r['from_user'] == user['name'] and r['status'] == 'pending']

    return jsonify({'incoming': incoming, 'outgoing': outgoing})


@app.route('/api/books/requests/<request_id>/approve', methods=['POST'])
def api_request_approve(request_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Нужно войти'}), 401

    with db_lock:
        req = next((r for r in db.get('book_requests', []) if r['id'] == request_id), None)
        if not req:
            return jsonify({'error': 'Заявка не найдена'}), 404
        if req['to_user'] != user['name']:
            return jsonify({'error': 'Это не твоя заявка'}), 403
        if req['status'] != 'pending':
            return jsonify({'error': 'Заявка уже обработана'}), 400

        req['status'] = 'approved'

        for b in db.get('books', []):
            if b['id'] == req['book_id']:
                b['holder'] = req['from_user']
                break

        save_db(db)

    print(f'Заявка подтверждена: книга "{req["book_title"]}" переписана на {req["from_user"]}')
    return jsonify({'success': True})


@app.route('/api/books/requests/<request_id>/reject', methods=['POST'])
def api_request_reject(request_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Нужно войти'}), 401

    with db_lock:
        req = next((r for r in db.get('book_requests', []) if r['id'] == request_id), None)
        if not req:
            return jsonify({'error': 'Заявка не найдена'}), 404
        if req['to_user'] != user['name']:
            return jsonify({'error': 'Это не твоя заявка'}), 403

        req['status'] = 'rejected'
        save_db(db)

    return jsonify({'success': True})


def run_flask():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)


def run_gui():
    ctk.set_appearance_mode("dark")

    root = ctk.CTk()
    root.title("Констурия — Чат команды")
    root.geometry("1050x680")
    root.configure(fg_color="#0f172a")
    root.minsize(800, 500)

    header = ctk.CTkFrame(root, fg_color="#1e1b4b", corner_radius=0)
    header.pack(fill="x")

    title = ctk.CTkLabel(header, text="Чат команды Констурии",
                         font=("Segoe UI", 24, "bold"), text_color="#ffffff")
    title.pack(pady=18)

    main_area = ctk.CTkFrame(root, fg_color="transparent")
    main_area.pack(fill="both", expand=True, padx=16, pady=16)
    main_area.grid_columnconfigure(1, weight=1)
    main_area.grid_rowconfigure(0, weight=1)

    users_frame = ctk.CTkFrame(main_area, fg_color="#111827", corner_radius=14)
    users_frame.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
    users_frame.grid_rowconfigure(1, weight=1)
    users_frame.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(users_frame, text="Пользователи", font=("Segoe UI", 16, "bold"),
                 text_color="#c4b5fd").grid(row=0, column=0, pady=(14, 6), padx=14, sticky="w")

    users_list = ctk.CTkScrollableFrame(users_frame, fg_color="transparent", width=220,
                                        scrollbar_button_color="#7c3aed",
                                        scrollbar_button_hover_color="#a855f7")
    users_list.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 10))

    chat_frame = ctk.CTkFrame(main_area, fg_color="#111827", corner_radius=14)
    chat_frame.grid(row=0, column=1, sticky="nsew")
    chat_frame.grid_rowconfigure(1, weight=1)
    chat_frame.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(chat_frame, text="Выбери пользователя слева",
                 font=("Segoe UI", 16, "bold"), text_color="#94a3b8").grid(row=0, column=0, pady=(14, 6), padx=16, sticky="w")

    messages_box = ctk.CTkScrollableFrame(chat_frame, fg_color="transparent",
                                          scrollbar_button_color="#7c3aed",
                                          scrollbar_button_hover_color="#a855f7")
    messages_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))

    input_frame = ctk.CTkFrame(chat_frame, fg_color="transparent")
    input_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
    input_frame.grid_columnconfigure(0, weight=1)

    reply_input = ctk.CTkEntry(input_frame, placeholder_text="Напиши ответ...",
                               height=42, corner_radius=21, font=("Segoe UI", 14))
    reply_input.grid(row=0, column=0, sticky="ew", padx=(0, 8))

    ctk.CTkButton(input_frame, text="Отправить", width=120, height=42,
                  corner_radius=21, font=("Segoe UI", 14, "bold"),
                  fg_color="#7c3aed", hover_color="#6d28d9",
                  command=lambda: send_reply()).grid(row=0, column=1)

    selected_user = [None]
    user_buttons = {}

    def get_team_users():
        with db_lock:
            msgs = list(db['messages'])
        names = []
        for m in msgs:
            if m.get('recipient') == TEAM_NAME:
                s = m.get('sender')
                if s and s not in names:
                    names.append(s)
        return names

    def get_team_conversation(user):
        with db_lock:
            msgs = list(db['messages'])
        return [m for m in msgs
                if (m.get('sender') == user and m.get('recipient') == TEAM_NAME)
                or (m.get('sender') == TEAM_NAME and m.get('recipient') == user)]

    def refresh_users():
        names = get_team_users()
        for child in users_list.winfo_children():
            child.destroy()
        user_buttons.clear()

        if not names:
            ctk.CTkLabel(users_list, text="Пока никто не писал",
                         font=("Segoe UI", 13), text_color="#64748b").pack(pady=20)
            return

        for name in names:
            btn = ctk.CTkButton(users_list, text=name, anchor="w", height=40, corner_radius=10,
                                font=("Segoe UI", 14),
                                fg_color="#7c3aed" if name == selected_user[0] else "#1f2937",
                                hover_color="#374151",
                                command=lambda n=name: select_user(n))
            btn.pack(fill="x", pady=3, padx=4)
            user_buttons[name] = btn

    def select_user(name):
        selected_user[0] = name
        for n, btn in user_buttons.items():
            btn.configure(fg_color="#7c3aed" if n == name else "#1f2937")
        refresh_chat()

    def refresh_chat():
        for child in messages_box.winfo_children():
            child.destroy()
        if not selected_user[0]:
            return

        conv = get_team_conversation(selected_user[0])
        if not conv:
            ctk.CTkLabel(messages_box, text="Сообщений пока нет",
                         font=("Segoe UI", 14), text_color="#64748b").pack(pady=40)
            return

        for m in conv:
            is_team = m.get('sender') == TEAM_NAME
            card = ctk.CTkFrame(messages_box,
                                fg_color="#24204d" if is_team else "#1e293b", corner_radius=14)
            card.pack(fill="x", pady=6)

            ctk.CTkFrame(card, width=5, fg_color="#a855f7" if is_team else "#38bdf8",
                         corner_radius=3).pack(side="left", fill="y", pady=8)

            content = ctk.CTkFrame(card, fg_color="transparent")
            content.pack(fill="x", padx=14, pady=10)

            ctk.CTkLabel(content, text=f"{m.get('sender', '')} • {m.get('time', '')}",
                         font=("Segoe UI", 12, "bold"),
                         text_color="#c4b5fd" if is_team else "#94a3b8",
                         anchor="w").pack(fill="x")

            ctk.CTkLabel(content, text=m.get('text', ''), font=("Segoe UI", 15),
                         text_color="#e2e8f0", anchor="w", wraplength=560,
                         justify="left").pack(fill="x", pady=(4, 0))

        messages_box.update_idletasks()
        try:
            messages_box._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def send_reply():
        if not selected_user[0]:
            return
        text = reply_input.get().strip()
        if not text:
            return

        with db_lock:
            db['messages'].append({
                'sender': TEAM_NAME,
                'recipient': selected_user[0],
                'text': text,
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            save_db(db)

        reply_input.delete(0, 'end')
        refresh_chat()

    reply_input.bind('<Return>', lambda event: send_reply())

    last_count = [0]

    def update():
        with db_lock:
            count = len(db['messages'])
        if count != last_count[0]:
            refresh_users()
            if selected_user[0]:
                refresh_chat()
            last_count[0] = count
        root.after(1500, update)

    update()
    root.mainloop()


if __name__ == '__main__':
    server_thread = threading.Thread(target=run_flask, daemon=True)
    server_thread.start()
    run_gui()