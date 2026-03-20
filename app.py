from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import sqlite3
import config
import database
import os
import base64
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
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
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
        bestaand = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if bestaand:
            conn.close()
            return render_template('register.html', error='Gebruikersnaam al in gebruik.')
        hashed = generate_password_hash(password)
        conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed))
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = database.get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            u = User(user['id'], user['username'], user['xp'], user['streak'])
            login_user(u)
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Verkeerde gebruikersnaam of wachtwoord.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = database.get_db()
    top5 = conn.execute('SELECT username, xp FROM users ORDER BY xp DESC LIMIT 5').fetchall()
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
    uitleg, _ = groq_vraag(systeem, tekst)
    return jsonify({'uitleg': uitleg})

@app.route('/api/woorden')
@login_required
def api_woorden():
    van = request.args.get('van', 1, type=int)
    tot = request.args.get('tot', 20, type=int)
    conn = database.get_db()
    woorden = conn.execute(
        'SELECT * FROM words WHERE nummer >= ? AND nummer <= ? ORDER BY nummer',
        (van, tot)
    ).fetchall()
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
    bestaand = conn.execute(
        'SELECT * FROM progress WHERE user_id = ? AND word_id = ?',
        (current_user.id, word_id)
    ).fetchone()
    if bestaand:
        nieuwe_score = bestaand['score'] + (1 if juist else -1)
        conn.execute(
            'UPDATE progress SET score = ?, laatste_keer = ? WHERE user_id = ? AND word_id = ?',
            (nieuwe_score, nu, current_user.id, word_id)
        )
    else:
        conn.execute(
            'INSERT INTO progress (user_id, word_id, score, laatste_keer) VALUES (?, ?, ?, ?)',
            (current_user.id, word_id, 1 if juist else 0, nu)
        )
    if juist:
        xp_gain = 10
        conn.execute('UPDATE users SET xp = xp + ? WHERE id = ?', (xp_gain, current_user.id))
    conn.commit()
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
    users = conn.execute('SELECT * FROM users ORDER BY xp DESC').fetchall()
    conn.close()
    return render_template('admin/panel.html', users=users)

@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
def reset_password(user_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    new_password = request.form['new_password']
    hashed = generate_password_hash(new_password)
    conn = database.get_db()
    conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed, user_id))
    conn.commit()
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
    foto_b64 = base64.standard_b64encode(foto_bytes).decode('utf-8')
    media_type = foto.content_type or 'image/jpeg'

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    prompt = """Dit is een pagina uit een Latijns woordjesboek (Pegasus Novus, 2e middelbaar).
Haal alle woordjes eruit en geef ze terug als JSON lijst.
Elk woord heeft deze velden:
- nummer (int): het nummer van het woord
- woordsoort (string): "znw12" voor zelfstandig naamwoord 1e/2e klasse, "znw3" voor 3e klasse, "ww" voor werkwoord, "bnw" voor bijvoeglijk naamwoord, "bw" voor bijwoord, "vw" voor voegwoord
- grondwoord (string): het eerste woord zoals het in het boek staat
- veld2 (string of null): genitief, 1e persoon, stam, vrouwelijk, of woordsoortlabel
- veld3 (string of null): geslacht, stamtijden, onzijdig, of null
- veld4 (string of null): extra veld indien nodig, anders null
- vertaling (string): de Nederlandse vertaling

Geef ALLEEN de JSON lijst terug, geen uitleg, geen markdown, geen backticks."""

    try:
        response = client.messages.create(
            model='claude-sonnet-4-5-20251001',
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
        woorden_data = json.loads(tekst)

        conn = database.get_db()
        toegevoegd = []
        for w in woorden_data:
            bestaand = conn.execute(
                'SELECT id FROM words WHERE nummer = ?', (w['nummer'],)
            ).fetchone()
            if not bestaand:
                conn.execute(
                    'INSERT INTO words (nummer, hoofdstuk, woordsoort, grondwoord, veld2, veld3, veld4, vertaling) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    (w['nummer'], hoofdstuk, w['woordsoort'], w['grondwoord'], w.get('veld2'), w.get('veld3'), w.get('veld4'), w['vertaling'])
                )
                toegevoegd.append(w)
        conn.commit()
        conn.close()

        return jsonify({'ok': True, 'aantal': len(toegevoegd), 'woorden': toegevoegd})

    except Exception as e:
        return jsonify({'ok': False, 'fout': str(e)})

if __name__ == '__main__':
    app.run(debug=True)
