import psycopg2
import psycopg2.extras
import config

def get_db():
    conn = psycopg2.connect(config.DATABASE_URL)
    return conn

def get_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    conn = get_db()
    c = get_cursor(conn)

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        xp INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        last_active TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS words (
        id SERIAL PRIMARY KEY,
        nummer INTEGER NOT NULL,
        hoofdstuk INTEGER NOT NULL,
        woordsoort TEXT NOT NULL,
        grondwoord TEXT NOT NULL,
        veld2 TEXT,
        veld3 TEXT,
        veld4 TEXT,
        vertaling TEXT NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS progress (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        word_id INTEGER NOT NULL,
        score INTEGER DEFAULT 0,
        laatste_keer TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (word_id) REFERENCES words(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS suggesties (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        word_id INTEGER NOT NULL,
        veld TEXT NOT NULL,
        huidige_waarde TEXT,
        voorgestelde_waarde TEXT NOT NULL,
        status TEXT DEFAULT 'open',
        aangemaakt_op TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (word_id) REFERENCES words(id)
    )''')

    conn.commit()
    c.close()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database aangemaakt!")
