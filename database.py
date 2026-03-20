import sqlite3
import config

def get_db():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # Gebruikers
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        xp INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        last_active TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    # Woorden
    c.execute('''CREATE TABLE IF NOT EXISTS words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nummer INTEGER NOT NULL,
        hoofdstuk INTEGER NOT NULL,
        woordsoort TEXT NOT NULL,
        grondwoord TEXT NOT NULL,
        veld2 TEXT,
        veld3 TEXT,
        veld4 TEXT,
        vertaling TEXT NOT NULL
    )''')

    # Voortgang per gebruiker per woord
    c.execute('''CREATE TABLE IF NOT EXISTS progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        word_id INTEGER NOT NULL,
        score INTEGER DEFAULT 0,
        laatste_keer TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (word_id) REFERENCES words(id)
    )''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database aangemaakt!")
