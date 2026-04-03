import psycopg2, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
conn = psycopg2.connect('postgresql://postgres:postgres123@localhost:5432/winegod_db')
cur = conn.cursor()

terms = [
    'pabst', 'sabana', 'hilos', 'fabada', 'penne', 'paccheri',
    'fettuccine', 'szirup', 'sirop', 'ballpen', 'samsung',
    'spritz', 'vermouth', 'distillery', 'topping', 'keg', 'rollon',
]

for t in terms:
    cur.execute("SELECT count(*) FROM wines_clean WHERE nome_normalizado LIKE %s", ('%' + t + '%',))
    c = cur.fetchone()[0]
    cur.execute("SELECT nome_normalizado FROM wines_clean WHERE nome_normalizado LIKE %s ORDER BY random() LIMIT 3", ('%' + t + '%',))
    exs = [r[0][:55] for r in cur.fetchall()]
    print(f'{t}: {c}')
    for e in exs:
        print(f'  "{e}"')
    print()

conn.close()
