"""Perfil de TESTE sobre as planilhas reais: os testes nunca usam (nem dependem de) a aprovação do usuário.

Copia o conjunto de controles do perfil real (mesmos arquivos e mesmos valores esperados), marca-o como perfil
TESTE e aprovado pelo teste automatizado. O perfil real (config/controles.json) não é tocado e continua exigindo a
aprovação efetiva da pessoa responsável para aplicar.
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import importacao as I  # noqa: E402


def cfg_teste_real():
    cfg = copy.deepcopy(I.carregar_config())
    conj = []
    for c in cfg["controles"]:
        t = dict(copy.deepcopy(c), id="TESTE · " + c["id"], perfil="TESTE",
                 aprovacao={"status": "APROVADO", "por": "teste automatizado (não substitui a aprovação do usuário)",
                            "em": "2026-10-16"})
        conj.append(t)
    cfg["controles"], cfg["perfil"] = conj, "TESTE"
    return cfg
