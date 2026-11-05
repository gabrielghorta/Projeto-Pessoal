"""Fixtures explícitas dos cenários anteriores; o importador do produto não cria equipes (D-212)."""
import regras as R


def cadastrar(conn):
    for eid in R.FRENTES:
        nome = 'EQUIPE ZONA ' + eid[4:] if eid.startswith('Zona') else 'EQUIPE ' + eid
        conn.execute('INSERT OR IGNORE INTO equipes(id,nome) VALUES (?,?)', (eid,nome))
