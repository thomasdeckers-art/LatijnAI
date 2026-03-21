from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import config
import database
import os
import base64
from PIL import Image
import io
from groq import Groq
import anthropic

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.secret_key = config.SECRET_KEY

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

database.init_db()

groq_client = Groq(api_key=config.GROQ_API_KEY)
GROOT_MODEL = 'llama-3.3-70b-versatile'
KLEIN_MODEL = 'llama3-8b-8192'

class User(UserMixin):
    def __init__(self, id, username, xp, streak):
        self.id = id
        self.username = username
        self.xp = xp
        self.streak = streak

@login_manager.user_loader
def load_user(user_id):
    conn = database.get_db()
    c = database.get_cursor(conn)
    c.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user = c.fetchone()
    c.close()
    conn.close()
    if user:
        return User(user['id'], user['username'], user['xp'], user['streak'])
    return None

def get_level(xp):
    levels = [
        (0, 'Tiro'),
        (500, 'Miles'),
        (1500, 'Optio'),
        (3500, 'Centurio'),
        (7000, 'Tribunus'),
        (12000, 'Legatus'),
        (20000, 'Praetor'),
        (35000, 'Consul'),
        (55000, 'Dictator'),
        (80000, 'Caesar'),
    ]
    level = 'Tiro'
    for xp_needed, name in levels:
        if xp >= xp_needed:
            level = name
    return level

def groq_vraag(systeem, gebruiker):
    melding = None
    try:
        response = groq_client.chat.completions.create(
            model=GROOT_MODEL,
            messages=[
                {'role': 'system', 'content': systeem},
                {'role': 'user', 'content': gebruiker}
            ]
        )
        return response.choices[0].message.content, melding
    except Exception:
        melding = 'Even iets trager door hoog gebruik, we zijn zo terug op volle snelheid.'
        try:
            response = groq_client.chat.completions.create(
                model=KLEIN_MODEL,
                messages=[
                    {'role': 'system', 'content': systeem},
                    {'role': 'user', 'content': gebruiker}
                ]
            )
            return response.choices[0].message.content, melding
        except Exception as e:
            return 'Er is een fout opgetreden. Probeer later opnieuw.', melding

# --- ROUTES ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            return render_template('register.html', error='Vul alle velden in.')
        conn = database.get_db()
        c = database.get_cursor(conn)
        c.execute('SELECT id FROM users WHERE username = %s', (username,))
        bestaand = c.fetchone()
        if bestaand:
            c.close()
            conn.close()
            return render_template('register.html', error='Gebruikersnaam al in gebruik.')
        hashed = generate_password_hash(password)
        c.execute('INSERT INTO users (username, password) VALUES (%s, %s)', (username, hashed))
        conn.commit()
        c.close()
        conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = database.get_db()
        c = database.get_cursor(conn)
        c.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = c.fetchone()
        c.close()
        conn.close()
        if user and check_password_hash(user['password'], password):
            u = User(user['id'], user['username'], user['xp'], user['streak'])
            login_user(u)
            # Streak bijwerken bij login
            update_streak(user['id'])
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Verkeerde gebruikersnaam of wachtwoord.')
    return render_template('login.html')

def update_streak(user_id):
    conn = database.get_db()
    c = database.get_cursor(conn)
    c.execute('SELECT last_active, streak FROM users WHERE id = %s', (user_id,))
    user = c.fetchone()
    vandaag = date.today().isoformat()
    if user['last_active'] is None:
        # Eerste keer inloggen
        c.execute('UPDATE users SET streak = 1, last_active = %s WHERE id = %s', (vandaag, user_id))
    else:
        gisteren = (date.today().replace(day=date.today().day - 1)).isoformat()
        if user['last_active'] == vandaag:
            pass  # Vandaag al ingelogd, streak niet aanpassen
        elif user['last_active'] == gisteren:
            # Gisteren ingelogd → streak +1
            c.execute('UPDATE users SET streak = streak + 1, last_active = %s WHERE id = %s', (vandaag, user_id))
        else:
            # Streak verbroken
            c.execute('UPDATE users SET streak = 1, last_active = %s WHERE id = %s', (vandaag, user_id))
    conn.commit()
    c.close()
    conn.close()

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = database.get_db()
    c = database.get_cursor(conn)
    c.execute('SELECT username, xp FROM users ORDER BY xp DESC LIMIT 5')
    top5 = c.fetchall()
    c.close()
    conn.close()
    level = get_level(current_user.xp)
    return render_template('dashboard.html', top5=top5, level=level)

@app.route('/oefenen')
@login_required
def oefenen():
    return render_template('oefenen.html')

@app.route('/vertalen')
@login_required
def vertalen():
    return render_template('vertalen.html')

# --- API ---

@app.route('/api/vertaal', methods=['POST'])
@login_required
def api_vertaal():
    data = request.get_json()
    tekst = data.get('tekst', '')
    systeem = 'Je bent een Latijn-Nederlands vertaler. Vertaal de gegeven Latijnse tekst naar correct Nederlands. Geef alleen de vertaling, geen uitleg.'
    vertaling, melding = groq_vraag(systeem, tekst)
    return jsonify({'vertaling': vertaling, 'melding': melding})

@app.route('/api/grammatica', methods=['POST'])
@login_required
def api_grammatica():
    data = request.get_json()
    tekst = data.get('tekst', '')
    systeem = 'Je bent een Latijnse grammatica-expert. Geef een duidelijke grammatica-uitleg van de gegeven Latijnse tekst in het Nederlands. Bespreek woordsoorten, naamvallen, werkwoordsvormen en zinsstructuur.'
    uitleg, _ = groq_vraag(systeem, uitleg)
    return jsonify({'uitleg': uitleg})

@app.route('/api/woorden')
@login_required
def api_woorden():
    van = request.args.get('van', 1, type=int)
    tot = request.args.get('tot', 20, type=int)
    conn = database.get_db()
    c = database.get_cursor(conn)
    c.execute(
        'SELECT * FROM words WHERE nummer >= %s AND nummer <= %s ORDER BY nummer',
        (van, tot)
    )
    woorden = c.fetchall()
    c.close()
    conn.close()
    return jsonify({'woorden': [dict(w) for w in woorden]})

@app.route('/api/voortgang', methods=['POST'])
@login_required
def api_voortgang():
    data = request.get_json()
    word_id = data.get('word_id')
    juist = data.get('juist')
    nu = datetime.now().isoformat()
    conn = database.get_db()
    c = database.get_cursor(conn)
    c.execute(
        'SELECT * FROM progress WHERE user_id = %s AND word_id = %s',
        (current_user.id, word_id)
    )
    bestaand = c.fetchone()
    if bestaand:
        nieuwe_score = bestaand['score'] + (1 if juist else -1)
        c.execute(
            'UPDATE progress SET score = %s, laatste_keer = %s WHERE user_id = %s AND word_id = %s',
            (nieuwe_score, nu, current_user.id, word_id)
        )
    else:
        c.execute(
            'INSERT INTO progress (user_id, word_id, score, laatste_keer) VALUES (%s, %s, %s, %s)',
            (current_user.id, word_id, 1 if juist else 0, nu)
        )
    if juist:
        c.execute('UPDATE users SET xp = xp + 10 WHERE id = %s', (current_user.id,))
    conn.commit()
    c.close()
    conn.close()
    return jsonify({'ok': True})

# --- ADMIN ---

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['password'] == config.ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_panel'))
        return render_template('admin/login.html', error='Verkeerd wachtwoord.')
    return render_template('admin/login.html')

@app.route('/admin/panel')
def admin_panel():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    conn = database.get_db()
    c = database.get_cursor(conn)
    c.execute('SELECT * FROM users ORDER BY xp DESC')
    users = c.fetchall()
    c.close()
    conn.close()
    return render_template('admin/panel.html', users=users)

@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
def reset_password(user_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    new_password = request.form['new_password']
    hashed = generate_password_hash(new_password)
    conn = database.get_db()
    c = database.get_cursor(conn)
    c.execute('UPDATE users SET password = %s WHERE id = %s', (hashed, user_id))
    conn.commit()
    c.close()
    conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/upload_foto', methods=['POST'])
def admin_upload_foto():
    if not session.get('admin'):
        return jsonify({'ok': False, 'fout': 'Niet ingelogd als admin.'})

    foto = request.files.get('foto')
    hoofdstuk = request.form.get('hoofdstuk', 1, type=int)

    if not foto:
        return jsonify({'ok': False, 'fout': 'Geen foto ontvangen.'})

    if not config.ANTHROPIC_API_KEY:
        return jsonify({'ok': False, 'fout': 'Geen Anthropic API key ingesteld.'})

    foto_bytes = foto.read()
    img = Image.open(io.BytesIO(foto_bytes))
    img = img.convert('RGB')
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=70)
    foto_bytes = output.getvalue()

    foto_b64 = base64.standard_b64encode(foto_bytes).decode('utf-8')
    media_type = 'image/jpeg'

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    prompt = """Dit is een pagina uit een Latijns woordjesboek (Pegasus Novus, 2e middelbaar).
Haal alle woordjes eruit en geef ze terug als JSON lijst.
Elk woord heeft deze velden:
- nummer (int): het nummer van het woord
- woordsoort (string): leid dit af uit de structuur van het woord
- grondwoord (string): het eerste woord zoals het in het boek staat
- veld2 (string of null): genitief, 1e persoon, stam, vrouwelijk, of woordsoortlabel
- veld3 (string of null): geslacht, stamtijden, onzijdig, of null
- veld4 (string of null): extra veld indien nodig, anders null
- vertaling (string): de Nederlandse vertaling

Belangrijk: geef ABSOLUUT alleen een JSON array terug, beginnend met [ en eindigend met ].
Geen tekst ervoor of erna, geen uitleg, geen markdown, geen backticks."""

    try:
        response = client.messages.create(
            model='claude-sonnet-4-5',
            max_tokens=4000,
            messages=[{
                'role': 'user',
                'content': [
                    {
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': media_type,
                            'data': foto_b64
                        }
                    },
                    {
                        'type': 'text',
                        'text': prompt
                    }
                ]
            }]
        )

        import json
        tekst = response.content[0].text.strip()
        if tekst.startswith('```'):
            tekst = tekst.split('\n', 1)[1]
            tekst = tekst.rsplit('```', 1)[0]
        tekst = tekst.strip()
        woorden_data = json.loads(tekst)

        conn = database.get_db()
        c = database.get_cursor(conn)
        toegevoegd = []
        for w in woorden_data:
            c.execute('SELECT id FROM words WHERE nummer = %s', (w['nummer'],))
            bestaand = c.fetchone()
            if not bestaand:
                c.execute(
                    'INSERT INTO words (nummer, hoofdstuk, woordsoort, grondwoord, veld2, veld3, veld4, vertaling) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                    (w['nummer'], hoofdstuk, w['woordsoort'], w['grondwoord'], w.get('veld2'), w.get('veld3'), w.get('veld4'), w['vertaling'])
                )
                toegevoegd.append(w)
        conn.commit()
        c.close()
        conn.close()

        return jsonify({'ok': True, 'aantal': len(toegevoegd), 'woorden': toegevoegd})

    except Exception as e:
        return jsonify({'ok': False, 'fout': str(e)})

if __name__ == '__main__':
    app.run(debug=True)
