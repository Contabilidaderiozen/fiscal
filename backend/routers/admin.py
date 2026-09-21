"""
Router de Administração — ações de manutenção do próprio sistema.

Hoje só tem o restart do serviço via NSSM, mas fica reservado pra outras
ações administrativas futuras (ex: ver status do serviço, ver espaço em
disco, etc).
"""
import subprocess
from fastapi import APIRouter, Depends, HTTPException

import auth

router = APIRouter(prefix="/api/admin", tags=["admin"])

NSSM_PATH = r"C:\nssm\win64\nssm.exe"
SERVICO = "RiozenFiscal"


def _perfil(usuario: dict) -> str:
    """Mesma lógica de main.py:perfil_de_usuario — duplicada aqui (em vez
    de importar de main.py) pra não criar import circular entre main.py
    e os routers."""
    if not usuario:
        return "fiscal"
    perfil = (usuario.get("perfil") or "usuario").lower().strip()
    setor = (usuario.get("setor") or "fiscal").lower().strip()
    if perfil == "admin":
        return "admin"
    if setor == "todos":
        return "admin"
    if setor == "fiscal":
        return "fiscal"
    if setor in ("contabil", "contábil"):
        return "contabil"
    return "fiscal"


def _exigir_admin(usuario: dict = Depends(auth.usuario_atual)):
    if _perfil(usuario) != "admin":
        raise HTTPException(status_code=403, detail="Só administradores podem reiniciar o serviço.")
    return usuario


@router.post("/reiniciar-servico")
def reiniciar_servico(usuario: dict = Depends(_exigir_admin)):
    """
    Dispara 'nssm restart RiozenFiscal' num processo separado e desligado
    (DETACHED_PROCESS), com um atraso de 2s antes de rodar o comando de
    verdade. O atraso existe pra dar tempo dessa resposta HTTP chegar até
    o navegador ANTES do processo atual (este mesmo Uvicorn) ser
    derrubado pelo restart — sem o atraso, a conexão cairia no meio e o
    usuário não veria confirmação nenhuma.
    """
    comando = f'timeout /t 2 /nobreak >nul & "{NSSM_PATH}" restart {SERVICO}'
    try:
        subprocess.Popen(
            ["cmd", "/c", comando],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao disparar o restart: {e}")

    return {
        "ok": True,
        "mensagem": "Reiniciando o serviço em ~2 segundos. A página vai recarregar sozinha em instantes.",
    }
