"""Equipes operacionais criadas pelo usuário, independentes das zonas do projeto (D-212)."""
import servicos as S
from regras import RegraViolada

EMPRESAS = {"ANKARA": ("Ankara", "A"), "E1": ("Empreiteiro 1", "E1."), "E2": ("Empreiteiro 2", "E2.")}


def listar(conn, historicas=False):
    return S._rows(conn.execute("""SELECT e.*,
        (SELECT COUNT(*) FROM funcionarios f WHERE f.equipe_id=e.id) AS integrantes,
        (SELECT COUNT(*) FROM maquinas m WHERE m.equipe_id=e.id) AS maquinas
        FROM equipes e """ + ("" if historicas else "WHERE e.ativa=1 ") + "ORDER BY e.empresa,e.numero,e.id"))


def exigir(conn, equipe_id, completa=True):
    e = S._one(conn, "SELECT * FROM equipes WHERE id=?", equipe_id)
    if not e:
        raise RegraViolada("Equipe não cadastrada. Escolha a equipe ou crie uma em Equipes e designe seus integrantes.")
    if not e["ativa"]:
        raise RegraViolada("Escolha uma equipe ativa em Equipes. Crie a equipe e designe seus integrantes antes de usá-la.")
    if completa and e["empresa"] and not S._one(conn, "SELECT 1 FROM funcionarios WHERE equipe_id=?", equipe_id):
        raise RegraViolada(f"A equipe {e['nome']} ainda não tem integrantes. Designe os membros em Equipes antes de usá-la.")
    return e


def criar(conn, empresa, nome, por):
    if empresa not in EMPRESAS:
        raise RegraViolada("Escolha Ankara, Empreiteiro 1 ou Empreiteiro 2.")
    nome = str(nome or "").strip()
    if len(nome) > 100:
        raise RegraViolada("O nome da equipe deve ter até 100 caracteres.")
    with S.transacao(conn):
        numero = conn.execute("SELECT COALESCE(MAX(numero),0)+1 FROM equipes WHERE empresa=?", (empresa,)).fetchone()[0]
        titulo, prefixo = EMPRESAS[empresa]
        sigla = prefixo + str(numero)
        while S._one(conn,"SELECT 1 FROM equipes WHERE id=?",sigla):
            numero += 1
            sigla = prefixo + str(numero)
        nome = nome or f"{titulo} · Equipe {numero}"
        conn.execute("INSERT INTO equipes(id,nome,empresa,numero,ativa,criada_em,criada_por) VALUES (?,?,?,?,1,?,?)",
                     (sigla, nome, empresa, numero, S._agora(), por))
    return sigla


def excluir(conn, equipe_id, por):
    exigir(conn, equipe_id, completa=False)
    conn.execute("UPDATE equipes SET ativa=0,excluida_em=?,excluida_por=? WHERE id=?", (S._agora(), por, equipe_id))


def _livre(conn, tipo, ref):
    r = S._one(conn, """SELECT c.data FROM checkin_presencas p JOIN checkins c ON c.id=p.checkin_id
                       WHERE p.recurso_tipo=? AND p.recurso_id=? AND c.encerrado=0 LIMIT 1""", tipo, ref)
    if r:
        raise RegraViolada(f"Este integrante/recurso está em um check-in aberto de {r['data']}. Registre a devolução antes de mudar a equipe.")


def _id_recurso(ref):
    try:
        n = int(ref)
        if n <= 0 or str(ref).strip() != str(n):
            raise ValueError
        return n
    except (TypeError, ValueError):
        raise RegraViolada("Escolha um integrante/recurso válido.") from None


def membro(conn, equipe_id, nome=None, funcao=None, funcionario_id=None):
    exigir(conn, equipe_id, completa=False)
    with S.transacao(conn):
        if funcionario_id:
            f = S._one(conn, "SELECT * FROM funcionarios WHERE id=?", _id_recurso(funcionario_id))
            if not f:
                raise RegraViolada("Funcionário não encontrado.")
            if f["equipe_id"] == equipe_id:
                return f["id"]
            _livre(conn, "FUNCIONARIO", f["id"])
            if f["equipe_id"]:
                atual = S._one(conn, "SELECT ativa FROM equipes WHERE id=?", f["equipe_id"])
                if atual and atual["ativa"]:
                    raise RegraViolada("Este funcionário já pertence a outra equipe ativa. Retire-o dela antes de designá-lo.")
            conn.execute("UPDATE funcionarios SET equipe_id=? WHERE id=?", (equipe_id, f["id"]))
            return f["id"]
        nome, funcao = str(nome or "").strip(), str(funcao or "").strip()
        if not nome or len(nome) > 150 or len(funcao) > 100:
            raise RegraViolada("Informe o nome do integrante (até 150 caracteres) e a função (até 100).")
        if S._one(conn, "SELECT id FROM funcionarios WHERE equipe_id=? AND LOWER(TRIM(nome))=LOWER(?)", equipe_id, nome):
            raise RegraViolada("Já existe um integrante com esse nome nesta equipe.")
        return conn.execute("INSERT INTO funcionarios(nome,funcao,equipe_id) VALUES (?,?,?)", (nome, funcao, equipe_id)).lastrowid


def retirar_membro(conn, equipe_id, funcionario_id):
    exigir(conn, equipe_id, completa=False)
    f = S._one(conn, "SELECT * FROM funcionarios WHERE id=? AND equipe_id=?", _id_recurso(funcionario_id), equipe_id)
    if not f:
        raise RegraViolada("Integrante não encontrado nesta equipe.")
    _livre(conn, "FUNCIONARIO", f["id"])
    conn.execute("UPDATE funcionarios SET equipe_id=NULL WHERE id=?", (f["id"],))


def recursos(conn, equipe_id):
    return {"funcionarios": S._rows(conn.execute("SELECT * FROM funcionarios WHERE equipe_id=? ORDER BY nome", (equipe_id,))),
            "maquinas": S._rows(conn.execute("SELECT * FROM maquinas WHERE equipe_id=? ORDER BY descricao", (equipe_id,)))}


def disponiveis(conn):
    return S._rows(conn.execute("""SELECT f.* FROM funcionarios f LEFT JOIN equipes e ON e.id=f.equipe_id
                                   WHERE e.id IS NULL OR e.ativa=0 ORDER BY f.nome"""))


def validar_presencas(conn, equipe_id, funcionarios, maquinas):
    for tipo, tabela, ids in (("FUNCIONARIO", "funcionarios", funcionarios), ("MAQUINA", "maquinas", maquinas)):
        ids = [_id_recurso(ref) for ref in ids]
        if len(set(ids)) != len(ids):
            raise RegraViolada("O mesmo integrante/recurso apareceu mais de uma vez.")
        for ref in ids:
            if not S._one(conn, f"SELECT 1 FROM {tabela} WHERE id=? AND equipe_id=?", ref, equipe_id):
                raise RegraViolada("A presença contém integrante ou máquina que não pertence à equipe escolhida.")
