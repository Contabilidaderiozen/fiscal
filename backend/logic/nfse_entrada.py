"""
nfse_entrada.py — Módulo de Apuração de NFS-e de Entrada
Acessa o Portal Nacional NFS-e (gov.br/nfse) com certificado digital instalado no Windows,
consulta notas de serviço recebidas e verifica retenções obrigatórias por código LC 116.
"""

import os, time, json, re, traceback
from datetime import datetime
from . import tabela_ir_fonte_novo

# ─── Tabela de retenções por código LC 116 ───────────────────────────────────
# Formato: codigo_lc116 -> {
#   "descricao": str,
#   "iss": bool,          # município retém ISS
#   "irrf": bool,         # IRRF 1,5% (ou alíquota específica)
#   "irrf_aliq": float,   # alíquota IRRF (%)
#   "pis": float,         # PIS (%)
#   "cofins": float,      # COFINS (%)
#   "csll": float,        # CSLL (%)
#   "obs": str            # observação
# }
# Fonte: LC 116/2003, IN RFB 2.145/2023, Solução de Consulta COSIT

TABELA_LC116 = {
    # ── Serviços sujeitos a retenção federal (PCC + IRRF) ─────────────────────
    "1.01": {"descricao": "Análise e desenvolvimento de sistemas", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0,
             "obs": "Sujeito a retenções federais (PCC 4,65%) e ISS"},
    "1.02": {"descricao": "Programação", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0,
             "obs": "Sujeito a retenções federais (PCC 4,65%) e ISS"},
    "1.03": {"descricao": "Processamento, armazenamento ou hospedagem de dados", "iss": True,
             "irrf": False, "irrf_aliq": 0, "pis": 0.65, "cofins": 3.0, "csll": 1.0,
             "obs": "PCC sem IRRF"},
    "1.04": {"descricao": "Elaboração de programas de computadores", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "1.05": {"descricao": "Licenciamento de software", "iss": True,
             "irrf": False, "irrf_aliq": 0, "pis": 0.65, "cofins": 3.0, "csll": 1.0,
             "obs": "PCC sem IRRF"},
    "1.07": {"descricao": "Suporte técnico em informática", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "4.01": {"descricao": "Medicina e biomedicina", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "4.02": {"descricao": "Análises clínicas, patologia, eletricidade médica", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "4.03": {"descricao": "Hospitais, clínicas, laboratórios", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "4.16": {"descricao": "Odontologia", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "5.01": {"descricao": "Medicina veterinária e zootecnia", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "6.01": {"descricao": "Barbearia, cabeleireiros, manicuros, pedicuros", "iss": True,
             "irrf": False, "irrf_aliq": 0, "pis": 0, "cofins": 0, "csll": 0,
             "obs": "Sem retenção federal — apenas ISS"},
    "6.04": {"descricao": "Ginástica, dança, esportes, natação", "iss": True,
             "irrf": False, "irrf_aliq": 0, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "7.01": {"descricao": "Engenharia, agronomia, agrimensura, arquitetura", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "7.02": {"descricao": "Execução de obras de construção civil", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0,
             "obs": "Verificar retenção de ISS conforme município"},
    "7.03": {"descricao": "Elaboração de planos diretores, estudos de viabilidade", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "7.09": {"descricao": "Varrição, coleta, remoção, incineração de lixo", "iss": True,
             "irrf": False, "irrf_aliq": 0, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "7.10": {"descricao": "Limpeza, manutenção e conservação", "iss": True,
             "irrf": True, "irrf_aliq": 1.0, "pis": 0.65, "cofins": 3.0, "csll": 1.0,
             "obs": "IRRF 1% para limpeza/conservação (Lei 9.064/1995)"},
    "7.11": {"descricao": "Decoração e jardinagem", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "7.17": {"descricao": "Instalação e montagem de produtos e equipamentos", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "7.19": {"descricao": "Acompanhamento e fiscalização de obras", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "8.01": {"descricao": "Ensino regular pré-escolar, fundamental, médio e superior", "iss": True,
             "irrf": False, "irrf_aliq": 0, "pis": 0, "cofins": 0, "csll": 0,
             "obs": "Entidades de ensino: verificar imunidade/isenção"},
    "8.02": {"descricao": "Instrução, treinamento, orientação pedagógica", "iss": True,
             "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "9.01": {"descricao": "Hospedagem de qualquer natureza em hotéis", "iss": True,
             "irrf": False, "irrf_aliq": 0, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "10.01": {"descricao": "Agenciamento, corretagem e intermediação", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "10.02": {"descricao": "Agenciamento de seguros", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "10.09": {"descricao": "Representação de qualquer natureza", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "11.01": {"descricao": "Guarda e estacionamento de veículos", "iss": True,
              "irrf": False, "irrf_aliq": 0, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "11.02": {"descricao": "Vigilância, segurança ou monitoramento de bens e pessoas", "iss": True,
              "irrf": True, "irrf_aliq": 1.0, "pis": 0.65, "cofins": 3.0, "csll": 1.0,
              "obs": "IRRF 1% para vigilância/segurança"},
    "11.03": {"descricao": "Escolta, inclusive de veículos e cargas", "iss": True,
              "irrf": True, "irrf_aliq": 1.0, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "11.04": {"descricao": "Armazenamento, depósito, carga, descarga", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "12.01": {"descricao": "Espetáculos teatrais", "iss": True,
              "irrf": False, "irrf_aliq": 0, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "13.01": {"descricao": "Produção, gravação, edição, legendagem de filmes e vídeos", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "14.01": {"descricao": "Lubrificação, limpeza, lustração, revisão, manutenção de máquinas", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "14.05": {"descricao": "Restauração, recondicionamento, acondicionamento de produtos", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "15.01": {"descricao": "Assessoria ou consultoria de qualquer natureza", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "15.02": {"descricao": "Análise, exame, pesquisa, coleta, compilação e fornecimento de dados", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "15.03": {"descricao": "Planejamento, organização, gerenciamento de projetos", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "15.04": {"descricao": "Recrutamento, agenciamento, seleção, colocação de mão-de-obra", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "15.05": {"descricao": "Fornecimento de mão-de-obra, mesmo em caráter temporário", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "15.06": {"descricao": "Propaganda e publicidade", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "15.08": {"descricao": "Franquia (franchising)", "iss": True,
              "irrf": False, "irrf_aliq": 0, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "15.09": {"descricao": "Perícias, laudos, exames técnicos e análises técnicas", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "15.10": {"descricao": "Planejamento, organização e administração de feiras", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "15.13": {"descricao": "Auditoria", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "15.14": {"descricao": "Análise de Organização e Métodos", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "15.17": {"descricao": "Assessoria ou consultoria de qualquer natureza — financeira", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "16.01": {"descricao": "Serviços de transporte de natureza municipal", "iss": True,
              "irrf": False, "irrf_aliq": 0, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "17.01": {"descricao": "Assessoria ou consultoria jurídica", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "17.06": {"descricao": "Arbitragem de qualquer espécie", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "17.09": {"descricao": "Datilografia, digitação, estenografia, expediente", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "17.10": {"descricao": "Secretaria e expediente", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "17.11": {"descricao": "Comunicação de massa por qualquer meio", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "17.12": {"descricao": "Contestação judicial e administrativa", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "17.14": {"descricao": "Instalação e manutenção de aparelhos", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "17.19": {"descricao": "Serviços de distribuição e venda de bilhetes de loteria", "iss": True,
              "irrf": False, "irrf_aliq": 0, "pis": 0, "cofins": 0, "csll": 0, "obs": "Sem retenção"},
    "17.20": {"descricao": "Feiras, exposições, congressos e congêneres", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "21.01": {"descricao": "Serviços de registros públicos, cartorários e notariais", "iss": True,
              "irrf": False, "irrf_aliq": 0, "pis": 0, "cofins": 0, "csll": 0, "obs": "Serviços notariais — sem retenção federal"},
    "22.01": {"descricao": "Planos de medicina de grupo ou individual", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "25.01": {"descricao": "Funerárias e serviços relacionados", "iss": True,
              "irrf": False, "irrf_aliq": 0, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "26.01": {"descricao": "Serviços de coleta de resíduos sólidos", "iss": True,
              "irrf": False, "irrf_aliq": 0, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
    "40.01": {"descricao": "Serviços portuários, ferroportuários, de terminais rodoviários", "iss": True,
              "irrf": True, "irrf_aliq": 1.5, "pis": 0.65, "cofins": 3.0, "csll": 1.0, "obs": ""},
}

# Valor mínimo para retenção federal (IN 2.145/2023)
MINIMO_RETENCAO_FEDERAL = 10.00
# PCC padrão para serviços sujeitos (quando IRRF + PIS + COFINS + CSLL aplicáveis)
ALIQ_PIS_PADRAO   = 0.65
ALIQ_COFINS_PADRAO = 3.00
ALIQ_CSLL_PADRAO  = 1.00


def verificar_retencoes(nota: dict) -> dict:
    """
    Dado um dict de nota fiscal, retorna análise completa de retenções.
    nota deve ter: numero, serie, valor, codigo_servico, iss_retido, irrf_retido,
                   pis_retido, cofins_retido, csll_retido, prestador_cnpj, prestador_nome
    """
    codigo = str(nota.get("codigo_servico", "")).strip()
    valor  = float(nota.get("valor_servico", 0) or 0)

    # Tenta achar na tabela antiga (já revisada p/ PCC) primeiro no formato
    # cru, depois no formato normalizado (a API manda '170601', a tabela usa '17.06')
    regra = TABELA_LC116.get(codigo, None)
    codigo_normalizado = tabela_ir_fonte_novo._normalizar_codigo(codigo)
    if regra is None and codigo_normalizado != codigo:
        regra = TABELA_LC116.get(codigo_normalizado, None)

    pcc_nao_verificado = False

    # Não achou na tabela antiga (não revisada p/ PCC) — tenta a tabela nova
    # de IRRF (700+ códigos). Nesse caso, o IRRF é confiável, mas o PCC
    # (PIS/COFINS/CSLL) fica marcado para verificação manual.
    if regra is None:
        info_ir = tabela_ir_fonte_novo.consultar_irrf(codigo)
        if info_ir["status"] in ("RETIDO", "ISENTO", "AUTO_RECOLHIMENTO"):
            regra = {
                "descricao": info_ir.get("categoria", "") or "Ver Relacao_Codigos_Servico_x_IR_Fonte.csv",
                "iss": True,
                "irrf": info_ir["status"] == "RETIDO",
                "irrf_aliq": info_ir["aliquota"] or 0,
                "pis": 0, "cofins": 0, "csll": 0,
                "obs": f"IRRF via tabela nova ({info_ir['base_legal']}). "
                       f"PCC (PIS/COFINS/CSLL) NÃO verificado automaticamente — conferir manualmente.",
            }
            pcc_nao_verificado = True

    resultado = {
        "numero": nota.get("numero", ""),
        "serie": nota.get("serie", ""),
        "data_emissao": nota.get("data_emissao", ""),
        "prestador_cnpj": nota.get("prestador_cnpj", ""),
        "prestador_nome": nota.get("prestador_nome", ""),
        "valor_servico": valor,
        "codigo_servico": codigo,
        "descricao_servico": regra["descricao"] if regra else "Código não encontrado na LC 116",
        "iss_retido_nota": float(nota.get("iss_retido", 0) or 0),
        "irrf_retido_nota": float(nota.get("irrf_retido", 0) or 0),
        "pis_retido_nota": float(nota.get("pis_retido", 0) or 0),
        "cofins_retido_nota": float(nota.get("cofins_retido", 0) or 0),
        "csll_retido_nota": float(nota.get("csll_retido", 0) or 0),
        "codigo_encontrado": regra is not None,
        "alertas": [],
    }

    if not regra:
        resultado["status_geral"] = "CODIGO_NAO_ENCONTRADO"
        resultado["alertas"].append(f"Código LC 116 '{codigo}' não encontrado na tabela. Verificar manualmente.")
        return resultado

    # ── Calcular retenções que DEVERIAM existir ──────────────────────────────
    # ISS: pra uma concessionária (Riozen/BYD/Toyota) como TOMADORA, a
    # retenção de ISS na fonte não se aplica na prática, em nenhum dos dois
    # cenários:
    #   - Prestador de fora do Rio: desde 06/2021 (Nota Carioca) e formalizado
    #     pelo art. 35 da LC municipal nº 235/2021 (revogou o CEPOM), não há
    #     mais retenção nesse caso — o prestador segue a tributação do
    #     próprio município dele.
    #   - Prestador do Rio: a retenção só é obrigatória pras categorias
    #     específicas do art. 7º do RISS (Decreto nº 10.514/91) — bancos,
    #     seguradoras, administradoras de cartão de crédito, cias aéreas,
    #     imobiliárias, planos de saúde, rádio/TV, empresas de jogos — e
    #     nenhuma delas descreve uma concessionária de veículos.
    # Por isso o campo "iss" da tabela por código (que não considera essa
    # regra de responsabilidade tributária) é ignorado aqui. Se um fornecedor
    # específico exigir retenção por outro motivo, tratar como exceção pontual.
    deve_reter_iss   = False
    deve_reter_irrf  = regra["irrf"] and valor >= MINIMO_RETENCAO_FEDERAL
    deve_reter_pis   = regra["pis"] > 0 and valor >= MINIMO_RETENCAO_FEDERAL
    deve_reter_cofins= regra["cofins"] > 0 and valor >= MINIMO_RETENCAO_FEDERAL
    deve_reter_csll  = regra["csll"] > 0 and valor >= MINIMO_RETENCAO_FEDERAL

    irrf_esperado   = round(valor * regra["irrf_aliq"]  / 100, 2) if deve_reter_irrf   else 0
    pis_esperado    = round(valor * regra["pis"]         / 100, 2) if deve_reter_pis    else 0
    cofins_esperado = round(valor * regra["cofins"]      / 100, 2) if deve_reter_cofins else 0
    csll_esperado   = round(valor * regra["csll"]        / 100, 2) if deve_reter_csll   else 0

    resultado.update({
        "deve_reter_iss":    deve_reter_iss,
        "deve_reter_irrf":   deve_reter_irrf,
        "deve_reter_pis":    deve_reter_pis,
        "deve_reter_cofins": deve_reter_cofins,
        "deve_reter_csll":   deve_reter_csll,
        "irrf_esperado":     irrf_esperado,
        "pis_esperado":      pis_esperado,
        "cofins_esperado":   cofins_esperado,
        "csll_esperado":     csll_esperado,
        "obs_tabela":        regra.get("obs", ""),
    })

    # ── Verificar divergências ────────────────────────────────────────────────
    alertas = []
    status_ok = True

    def _diverge(campo, esperado, retido, nome):
        nonlocal status_ok
        if esperado > 0 and abs(retido - esperado) > 0.05:
            if retido == 0:
                alertas.append(f"{nome} NÃO retido — deveria ser R$ {esperado:.2f}")
            else:
                alertas.append(f"{nome} retido R$ {retido:.2f} — esperado R$ {esperado:.2f}")
            status_ok = False

    _diverge("irrf",   irrf_esperado,   resultado["irrf_retido_nota"],   "IRRF")
    _diverge("pis",    pis_esperado,    resultado["pis_retido_nota"],    "PIS")
    _diverge("cofins", cofins_esperado, resultado["cofins_retido_nota"], "COFINS")
    _diverge("csll",   csll_esperado,   resultado["csll_retido_nota"],   "CSLL")

    # ISS: verificar apenas se havia valor retido quando não deveria
    if not deve_reter_iss and resultado["iss_retido_nota"] > 0:
        alertas.append(f"ISS retido indevidamente: R$ {resultado['iss_retido_nota']:.2f}")
        status_ok = False

    if pcc_nao_verificado:
        alertas.append(
            "PIS/COFINS/CSLL não verificados automaticamente para este código "
            "(fonte só cobre IRRF) — conferir manualmente."
        )

    resultado["alertas"] = alertas
    if pcc_nao_verificado and status_ok:
        resultado["status_geral"] = "PCC_NAO_VERIFICADO"
    else:
        resultado["status_geral"] = "OK" if status_ok else "DIVERGENCIA"
    return resultado


# ── Certificados digitais por empresa/filial ─────────────────────────────────
# Mapeamento construído a partir do certmgr.msc em 20/07/2026 — para cada CNPJ
# com mais de um certificado instalado, foi escolhido o que NÃO está vencido
# nessa data. Revisar esta tabela sempre que um certificado for renovado.
#
# ATENÇÃO: Toyota CAMPO GRANDE (22.134.988/0003-86) só tem um certificado
# instalado e ele já está VENCIDO (validade 12/05/2026). Essa filial vai
# falhar na autenticação até que um certificado novo seja emitido/instalado.
CERT_CONFIG = {
    ("Toyota", "PILARES"):                 {"subject_cn": "MOITINHO AUTOMOVEIS LTDA:22134988000114", "issuer_cn": "Solucao Digital Multipla"},
    ("Toyota", "TIJUCA"):                   {"subject_cn": "MOITINHO AUTOMOVEIS LTDA:22134988000203", "issuer_cn": "Solucao Digital Multipla"},
    ("Toyota", "CAMPO GRANDE"):             None,  # sem certificado válido — ver aviso acima
    ("Toyota", "BARRA - JARDIM OCEANICO"):  {"subject_cn": "MOITINHO AUTOMOVEIS LTDA:22134988000467", "issuer_cn": "Solucao Digital Multipla"},
    ("Toyota", "JACAREPAGUA WP"):            {"subject_cn": "MOITINHO AUTOMOVEIS LTDA:22134988000548", "issuer_cn": "Solucao Digital Multipla"},
    ("Toyota", "LEXUS"):                    {"subject_cn": "MOITINHO AUTOMOVEIS LTDA:22134988000629", "issuer_cn": "Solucao Digital Multipla"},
    ("Toyota", "ALVORADA"):                 {"subject_cn": "MOITINHO AUTOMOVEIS LTDA:22134988000700", "issuer_cn": "CONSULTI BRASIL RFB"},
    ("Toyota", "RECREIO"):                  {"subject_cn": "MOITINHO AUTOMOVEIS LTDA:22134988000890", "issuer_cn": "CONSULTI BRASIL RFB"},
    ("BYD", "JACAREPAGUA"):                 {"subject_cn": "MR RIO AUTOMOVEIS LTDA:52752754000100",   "issuer_cn": "CONSULTI BRASIL RFB"},
    ("BYD", "CAMPO GRANDE"):                {"subject_cn": "MR RIO AUTOMOVEIS LTDA:52752754000282",   "issuer_cn": "CONSULTI BRASIL RFB"},
    ("BYD", "SAO JOAO DE MERITI"):          {"subject_cn": "MR RIO AUTOMOVEIS LTDA:52752754000363",   "issuer_cn": "CONSULTI BRASIL RFB"},
    ("BYD", "BARRA MANSA"):                 {"subject_cn": "MR RIO AUTOMOVEIS LTDA:52752754000444",   "issuer_cn": "CONSULTI RFB"},
    ("Riozen", "INTERMEDIACAO"):            {"subject_cn": "RIOZEN INTERMEDIACAO DE NEGOCIOS LTDA:58489102000100", "issuer_cn": "CONSULTI BRASIL RFB"},
}


def acessar_portal_nfse(cnpj_tomador: str, data_inicio: str, data_fim: str,
                         empresa: str = None, filial: str = None,
                         callback_log=None, callback_progresso=None,
                         headless: bool = False) -> list:
    """
    Acessa o Portal Nacional NFS-e via Selenium, seleciona certificado digital,
    e retorna lista de notas de entrada no período.
    Retorna lista de dicts com dados das notas.

    headless=True roda sem janela visível. Só é seguro se o certificado da
    empresa/filial já estiver confirmado funcionando com seleção automática
    (CERT_CONFIG) — se o filtro de certificado falhar em modo headless, não
    há como intervir manualmente e a consulta simplesmente falha.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    import json as _json

    def log(msg):
        if callback_log: callback_log(msg)

    def prog(pct, msg=""):
        if callback_progresso: callback_progresso(pct, msg)

    # ── Configurar Chrome ────────────────────────────────────────────────────
    import tempfile, shutil
    pasta_downloads = tempfile.mkdtemp(prefix="nfse_xml_")

    opts = Options()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--disable-web-security")
    if headless:
        # NÃO usamos --headless=new: testes mostraram que a autenticação por
        # certificado trava/expira em headless de verdade, mesmo com o filtro
        # de seleção automática configurado corretamente — provavelmente
        # porque o Windows exige uma sessão de área de trabalho interativa
        # para liberar a chave privada do certificado, algo que o Chrome
        # headless não tem. Em vez disso, abrimos uma janela normal (mantém
        # a sessão interativa) mas posicionada bem fora da tela, então na
        # prática o usuário não vê nada.
        opts.add_argument("--window-position=-32000,-32000")
        opts.add_argument("--window-size=1920,1080")
        log("Chrome rodando fora da área visível da tela (sem janela para o usuário).")
    else:
        opts.add_argument("--start-maximized")
    opts.add_experimental_option("prefs", {
        "download.default_directory": pasta_downloads,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })

    # ── Selecao automatica de certificado (evita o popup nativo do Windows) ──
    cert_info = CERT_CONFIG.get((empresa, filial)) if empresa and filial else None
    if cert_info:
        auto_select = _json.dumps([{
            "pattern": "https://www.nfse.gov.br",
            "filter": {
                "SUBJECT": {"CN": cert_info["subject_cn"]},
                "ISSUER":  {"CN": cert_info["issuer_cn"]},
            }
        }])
        opts.add_argument(f"--auto-select-certificate-for-urls={auto_select}")
        log(f"Certificado configurado para seleção automática: {cert_info['subject_cn']}")
    elif empresa and filial and (empresa, filial) in CERT_CONFIG and cert_info is None:
        log(f"AVISO: não há certificado válido cadastrado para {empresa} / {filial}. "
            f"Selecione manualmente ou verifique se o certificado está vencido.")
    else:
        log("Nenhum certificado configurado para seleção automática — selecione manualmente.")


    log("Abrindo navegador...")
    prog(5, "Iniciando Chrome")

    try:
        driver = webdriver.Chrome(options=opts)
        wait   = WebDriverWait(driver, 60)
    except Exception as ex:
        raise RuntimeError(f"Não foi possível abrir o Chrome: {ex}\n"
                           "Verifique se o ChromeDriver está instalado.")

    notas = []

    try:
        # ── 1. Acessar portal ────────────────────────────────────────────────
        URL_PORTAL = "https://www.nfse.gov.br/EmissorNacional/Login"
        log(f"Acessando {URL_PORTAL}...")
        prog(10, "Abrindo portal NFS-e")
        driver.get(URL_PORTAL)

        # ── 1b. Clicar em "Certificado Digital" para disparar a autenticação ──
        log("Clicando em 'Certificado Digital'...")
        prog(12, "Selecionando modo de acesso")
        time.sleep(2)
        clicou_cert = False
        ESTRATEGIAS_CERT = [
            (By.XPATH, "//img[contains(@alt,'Certificado')]"),
            (By.XPATH, "//img[contains(@src,'ertificado')]"),
            (By.XPATH, "//*[contains(text(),'Certificado Digital')]"),
            (By.XPATH, "//a[.//img[contains(@alt,'Certificado')]]"),
            (By.CSS_SELECTOR, "img[alt*='ertificado']"),
        ]
        for by, sel in ESTRATEGIAS_CERT:
            try:
                elemento = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((by, sel)))
                elemento.click()
                clicou_cert = True
                break
            except Exception:
                continue

        if not clicou_cert:
            log("AVISO: não encontrei o botão 'Certificado Digital' automaticamente. "
                "Clique nele manualmente na janela do navegador.")
        else:
            log("  Certificado Digital selecionado.")

        # ── 2. Aguardar seleção de certificado ───────────────────────────────
        if headless:
            log("Aguardando autenticação automática por certificado (máx. 120s)...")
        else:
            log("AÇÃO NECESSÁRIA: selecione o certificado digital na janela do navegador")
            log("Aguardando autenticação (máx. 120s)...")
        prog(15, "Aguardando certificado")

        # Aguarda login ser concluído (URL muda ou elemento de dashboard aparece)
        try:
            wait_login = WebDriverWait(driver, 120)
            wait_login.until(lambda d: "Login" not in d.current_url or
                             len(d.find_elements(By.CSS_SELECTOR, "[class*='dashboard'], [class*='home'], [id*='main']")) > 0)
        except TimeoutException:
            raise RuntimeError("Tempo esgotado aguardando autenticação. Selecione o certificado e tente novamente.")

        log("Autenticação realizada!")
        prog(25, "Autenticado")

        # ── 3. Navegar para NFS-e recebidas ─────────────────────────────────
        log("Navegando para NFS-e recebidas...")
        prog(30, "Buscando notas recebidas")

        # Tentar via menu ou URL direta — a URL confirmada em produção vem primeiro
        URLS_TENTATIVAS = [
            "https://www.nfse.gov.br/EmissorNacional/Notas/Recebidas",
            "https://www.nfse.gov.br/EmissorNacional/NfseRecebida",
            "https://www.nfse.gov.br/EmissorNacional/Nfse/Recebidas",
            "https://www.nfse.gov.br/EmissorNacional/Consulta/NfseRecebida",
        ]

        navegou = False
        for url in URLS_TENTATIVAS:
            try:
                driver.get(url)
                time.sleep(2)
                url_atual = driver.current_url.lower()
                titulo    = driver.title.lower()
                corpo     = driver.page_source.lower()
                deu_erro = (
                    "erro" in url_atual or "error" in url_atual or
                    "404" in titulo or "erro" in titulo or
                    "erro interno do servidor" in corpo or "500 -" in corpo
                )
                if not deu_erro:
                    navegou = True
                    log(f"  Acessando: {url}")
                    break
                else:
                    log(f"  {url} -> página de erro, tentando próxima URL...")
            except Exception:
                continue

        if not navegou:
            # Tentar via menu lateral
            try:
                menu_items = driver.find_elements(By.XPATH,
                    "//*[contains(text(),'Recebida') or contains(text(),'recebida') or contains(text(),'Tomada')]")
                if menu_items:
                    menu_items[0].click()
                    time.sleep(2)
                    navegou = True
                    log("  Navegado via menu")
            except Exception:
                pass

        if not navegou:
            log("AVISO: não foi possível navegar automaticamente. Acesse manualmente: NFS-e Recebidas")

        # ── 4. Preencher filtro de período (dividido em blocos de até 30 dias,
        #      limite exigido pelo próprio portal) e extrair notas de cada bloco ──
        periodos = _dividir_periodo_30_dias(data_inicio, data_fim)
        if len(periodos) > 1:
            log(f"Período total maior que 30 dias — dividido em {len(periodos)} consulta(s).")

        estado_xml = {"falhas_consecutivas": 0, "desativado": False}

        for idx_periodo, (p_ini, p_fim) in enumerate(periodos, start=1):
            log(f"Filtrando período {idx_periodo}/{len(periodos)}: {p_ini} a {p_fim}")
            prog(35 + int(10 * idx_periodo / len(periodos)), "Aplicando filtros")

            try:
                _preencher_filtro_periodo(driver, p_ini, p_fim, log)
            except Exception as ex:
                log(f"AVISO: erro ao preencher filtro automaticamente: {ex}")
                log("Preencha o período manualmente e clique em Filtrar na janela do navegador.")
                log("Aguardando 40s para preenchimento manual...")
                prog(40, "Aguardando filtro manual")
                time.sleep(40)

            log("Aguardando resultados...")
            time.sleep(3)

            log(f"Extraindo dados das notas ({p_ini} a {p_fim})...")
            notas.extend(_extrair_notas_portal(driver, wait, log, prog, p_ini, p_fim, pasta_downloads, estado_xml))

        log(f"Total de notas encontradas: {len(notas)}")
        prog(90, f"{len(notas)} notas extraídas")

    except Exception as ex:
        log(f"ERRO: {ex}")
        traceback.print_exc()
        raise
    finally:
        try: driver.quit()
        except Exception: pass
        try: shutil.rmtree(pasta_downloads, ignore_errors=True)
        except Exception: pass

    return notas


def _dividir_periodo_30_dias(data_inicio_str: str, data_fim_str: str) -> list:
    """Divide o período em blocos de no máximo 30 dias (limite do portal)."""
    from datetime import datetime, timedelta
    d_ini = datetime.strptime(data_inicio_str, "%d/%m/%Y")
    d_fim = datetime.strptime(data_fim_str, "%d/%m/%Y")
    blocos = []
    cursor = d_ini
    while cursor <= d_fim:
        fim_bloco = min(cursor + timedelta(days=29), d_fim)
        blocos.append((cursor.strftime("%d/%m/%Y"), fim_bloco.strftime("%d/%m/%Y")))
        cursor = fim_bloco + timedelta(days=1)
    return blocos or [(data_inicio_str, data_fim_str)]


def _definir_valor_campo(driver, campo, valor):
    """Preenche um campo de data; se for readonly/datepicker e não aceitar
    digitação normal, força o valor via JS e dispara os eventos input/change
    para o framework da página reconhecer a mudança."""
    campo.clear()
    campo.send_keys(valor)
    if campo.get_attribute("value") != valor:
        driver.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
            "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
            campo, valor,
        )


def _preencher_filtro_periodo(driver, data_inicio: str, data_fim: str, log):
    """Preenche os campos de Data Inicial / Data Final e clica em Filtrar."""
    from selenium.webdriver.common.by import By

    SELETORES_INI = ("input[id*='dataInicial' i], input[name*='dataInicial' i], "
                      "input[placeholder*='nicial' i], input[id*='inicio' i], "
                      "input[id*='DataInicial'], input[name*='DataInicial']").split(",")
    for sel_ini in SELETORES_INI:
        try:
            campo = driver.find_element(By.CSS_SELECTOR, sel_ini.strip())
            _definir_valor_campo(driver, campo, data_inicio)
            break
        except Exception: continue

    SELETORES_FIM = ("input[id*='dataFinal' i], input[name*='dataFinal' i], "
                      "input[placeholder*='inal' i], input[id*='fim' i], "
                      "input[id*='DataFinal'], input[name*='DataFinal']").split(",")
    for sel_fim in SELETORES_FIM:
        try:
            campo = driver.find_element(By.CSS_SELECTOR, sel_fim.strip())
            _definir_valor_campo(driver, campo, data_fim)
            break
        except Exception: continue

    # Clicar Filtrar/Pesquisar/Consultar/Buscar — usa contains(., 'X') em vez
    # de contains(text(), 'X') porque o texto do botão costuma vir depois de
    # um ícone (ex.: funil), e contains(text(),..) só olha o nó de texto
    # direto, que pode não incluir o texto se a estrutura interna variar.
    btn = None
    for btn_txt in ["Filtrar", "Pesquisar", "Consultar", "Buscar"]:
        for xp in (f"//button[contains(., '{btn_txt}')]",
                   f"//input[@value='{btn_txt}']",
                   f"//a[contains(., '{btn_txt}')]"):
            try:
                btn = driver.find_element(By.XPATH, xp)
                if btn:
                    break
            except Exception:
                continue
        if btn:
            break

    if not btn:
        raise RuntimeError("Não encontrei os campos de data ou o botão Filtrar na página.")

    try:
        btn.click()
    except Exception:
        driver.execute_script("arguments[0].click();", btn)
    time.sleep(3)


def _extrair_notas_portal(driver, wait, log, prog, data_inicio, data_fim, pasta_downloads, estado_xml=None) -> list:
    """Extrai dados das notas da tabela de resultados do portal, percorrendo
    todas as páginas de resultado até não haver mais próxima página."""
    from selenium.webdriver.common.by import By

    notas = []
    pagina = 1
    MAX_PAGINAS = 200  # trava de segurança contra loop infinito
    if estado_xml is None:
        estado_xml = {"falhas_consecutivas": 0, "desativado": False}

    def _fingerprint_pagina():
        linhas = driver.find_elements(By.CSS_SELECTOR,
            "table tbody tr, [class*='lista'] [class*='item'], [class*='grid'] [class*='row']")
        if not linhas:
            return ""
        try:
            return linhas[0].text.strip()
        except Exception:
            return ""

    SELETORES_PROXIMA = [
        (By.XPATH, "//a[contains(text(),'Próxima') or contains(text(),'proxima') or contains(text(),'Next')]"),
        (By.XPATH, "//button[contains(text(),'Próxima') or contains(text(),'Next')]"),
        (By.XPATH, "//a[@aria-label='Next' or @aria-label='Próxima' or @aria-label='Próxima página']"),
        (By.CSS_SELECTOR, "a[aria-label*='ext'], a[aria-label*='róxima']"),
        (By.CSS_SELECTOR, ".pagination a[rel='next'], [class*='pag'] a[rel='next']"),
        (By.XPATH, "//li[not(contains(@class,'disabled'))]//a[contains(@class,'next') or contains(text(),'>')]"),
        (By.CSS_SELECTOR, "[class*='pag'] .fa-chevron-right, [class*='pag'] .fa-angle-right"),
    ]

    while True:
        time.sleep(2)
        linhas = driver.find_elements(By.CSS_SELECTOR,
            "table tbody tr, [class*='lista'] [class*='item'], [class*='grid'] [class*='row']")

        if not linhas:
            log(f"  Página {pagina}: nenhuma linha encontrada")
            break

        log(f"  Página {pagina}: {len(linhas)} linhas")
        fingerprint_antes = _fingerprint_pagina()

        for linha in linhas:
            try:
                nota = _extrair_dados_linha(driver, linha, log, pasta_downloads, estado_xml)
                if nota:
                    notas.append(nota)
            except Exception as ex:
                log(f"  AVISO linha: {ex}")
                continue
            if pasta_downloads and estado_xml is not None and not estado_xml.get("desativado"):
                time.sleep(2.5)  # ritmo mais humano entre notas, reduz risco de CAPTCHA

        if pagina >= MAX_PAGINAS:
            log(f"  Limite de {MAX_PAGINAS} páginas atingido — parando por segurança.")
            break

        # Verificar próxima página
        btn_prox = None
        for by, sel in SELETORES_PROXIMA:
            try:
                candidato = driver.find_element(by, sel)
                # Ignora se o próprio elemento ou o <li> pai estiver desabilitado
                classe_pai = ""
                try:
                    classe_pai = candidato.find_element(By.XPATH, "..").get_attribute("class") or ""
                except Exception:
                    pass
                if "disabled" in (candidato.get_attribute("class") or "") or "disabled" in classe_pai:
                    continue
                if candidato.is_enabled():
                    btn_prox = candidato
                    break
            except Exception:
                continue

        if not btn_prox:
            log("  Sem próxima página — fim da lista.")
            break

        try:
            btn_prox.click()
            time.sleep(2)
            fingerprint_depois = _fingerprint_pagina()
            if fingerprint_depois == fingerprint_antes:
                log("  Clique em 'próxima página' não mudou o conteúdo — encerrando paginação.")
                break
            pagina += 1
            prog(50 + min(pagina * 2, 35), f"Página {pagina}")
        except Exception:
            break  # Sem próxima página

    return notas


def _extrair_dados_linha(driver, linha, log, pasta_downloads=None, estado_xml=None) -> dict:
    """Extrai dados de uma linha da tabela de resultados.

    Esta tabela (Notas Recebidas) não tem uma coluna de 'número da nota'
    visível — só Geração, Emitida por, Competência, Preço e Situação. Por
    isso a validade da linha é baseada em CNPJ + valor, e um identificador
    é sintetizado a partir do timestamp de Geração (data/hora de emissão),
    que já é suficientemente único para fins de relatório."""
    from selenium.webdriver.common.by import By

    cells = linha.find_elements(By.TAG_NAME, "td")
    if len(cells) < 3:
        return None

    textos = [c.text.strip() for c in cells]

    nota_base = {}
    try:
        # Extrair dados básicos das células visíveis
        for i, txt in enumerate(textos):
            # Número da nota, se existir como coluna isolada (portais variam)
            if re.match(r'^\d{5,15}$', txt):
                nota_base["numero"] = txt
            # Datas — aceita ano com 2 ou 4 dígitos (esta tabela usa dd/mm/aa)
            elif re.match(r'^\d{2}/\d{2}/\d{2,4}', txt):
                if "data_emissao" not in nota_base:
                    nota_base["data_emissao"] = txt
                if "geracao" not in nota_base:
                    nota_base["geracao"] = txt
            # CNPJ (a célula "Emitida por" normalmente vem como "CNPJ - RAZAO SOCIAL")
            elif re.match(r'^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', txt):
                nota_base["prestador_cnpj"] = txt
                partes = txt.split("-", 1)
                if len(partes) > 1 and len(partes[1].strip()) > 3:
                    # remove o próprio CNPJ do início, sobra "NNN - RAZAO SOCIAL"
                    resto = txt.split(" ", 1)
                    if len(resto) > 1:
                        nota_base["prestador_nome"] = resto[1].lstrip("- ").strip()
            # Valores monetários
            elif re.match(r'^R?\$?\s*\d{1,3}(\.\d{3})*,\d{2}', txt):
                val = _parse_valor(txt)
                if "valor_servico" not in nota_base:
                    nota_base["valor_servico"] = val

        # NOTA: a extração de detalhe (código LC 116, retenções) abrindo uma
        # nova aba por nota foi DESATIVADA — sem timeout de segurança, uma
        # única trava (aba que não abre, certificado pedido de novo numa aba
        # escondida, etc.) prendia o processo inteiro sem chance de recuperação.

        # Sem coluna de número visível nesta tabela: sintetiza um identificador
        # a partir do CNPJ + timestamp de geração (data e hora), que é
        # suficientemente único para o relatório.
        if not nota_base.get("numero") and nota_base.get("geracao"):
            base_id = f"{nota_base.get('prestador_cnpj','')}_{nota_base['geracao']}"
            nota_base["numero"] = base_id.replace(" ", "_").replace("/", "").replace(":", "").replace(".", "").replace("-", "")
            nota_base["numero_sintetico"] = True

        # ── Baixar e ler o XML da nota (código LC 116 + retenções) ───────────
        # Usa o menu "⋮" > "Download XML" da própria linha — fica na mesma
        # página (sem abrir aba/navegar), então não corre o risco de derrubar
        # a sessão como a abordagem anterior (aba nova) causava.
        if pasta_downloads and estado_xml is not None and not estado_xml.get("desativado"):
            estado_xml["tentativas"] = estado_xml.get("tentativas", 0) + 1
            debug_esta_tentativa = estado_xml["tentativas"] <= 3
            try:
                caminho_xml = _baixar_xml_nota(driver, linha, pasta_downloads, log, debug=debug_esta_tentativa)
                if caminho_xml:
                    nome_arquivo = os.path.basename(caminho_xml)
                    if estado_xml.get("ultimo_arquivo") == nome_arquivo:
                        log(f"    AVISO: baixou o mesmo arquivo XML da nota anterior ({nome_arquivo}) "
                            "— pode ser que o menu esteja preso na linha errada.")
                    estado_xml["ultimo_arquivo"] = nome_arquivo
                    dados_xml = _parsear_xml_nota(caminho_xml)
                    nota_base.update({k: v for k, v in dados_xml.items() if v})
                    try: os.remove(caminho_xml)
                    except Exception: pass
                    estado_xml["falhas_consecutivas"] = 0
                else:
                    estado_xml["falhas_consecutivas"] += 1
            except Exception as ex:
                log(f"    AVISO: não consegui baixar/ler o XML desta nota: {ex}")
                estado_xml["falhas_consecutivas"] += 1

            if estado_xml["falhas_consecutivas"] >= 5:
                estado_xml["desativado"] = True
                log("AVISO: download de XML falhou 5 vezes seguidas — desativando pelo "
                    "resto da consulta (código LC116/retenções não virão das notas restantes).")

    except Exception as ex:
        log(f"    erro linha: {ex}")

    # Válida se: tem numero (real ou sintético) E pelo menos CNPJ ou valor
    if nota_base.get("numero") and (nota_base.get("prestador_cnpj") or "valor_servico" in nota_base):
        return nota_base
    return None


def _baixar_xml_nota(driver, linha, pasta_downloads, log, timeout_download=25, debug=False) -> str:
    """Abre o menu '⋮' da linha, clica em 'Download XML' e espera o arquivo
    aparecer na pasta de downloads. Retorna o caminho do arquivo baixado, ou
    None se não conseguir (menu não encontrado, opção ausente, timeout).
    Se debug=True, loga cada etapa (usado só nas primeiras tentativas)."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # Limpa arquivos .xml deixados por uma tentativa anterior que deu timeout
    # (senão a próxima nota pode "ver" esse arquivo velho e ficar confusa
    # sobre o que é novo, ou nunca reconhecer um download genuíno como novo).
    for f in os.listdir(pasta_downloads):
        if f.lower().endswith(".xml") or f.lower().endswith(".crdownload"):
            try: os.remove(os.path.join(pasta_downloads, f))
            except Exception: pass

    arquivo_antes = set(os.listdir(pasta_downloads))  # foto ANTES de disparar o download

    # 1. Achar e clicar no botão "⋮" (menu de ações) desta linha
    SELETORES_MENU = [
        (By.CSS_SELECTOR, "a.icone-trigger"),
        (By.CSS_SELECTOR, ".menu-suspenso-tabela a"),
        (By.CSS_SELECTOR, "i.glyphicon-option-vertical"),
        (By.CSS_SELECTOR, "td.opcoes a"),
        (By.CSS_SELECTOR, "button[class*='dropdown'], button[class*='menu'], button[class*='acoes']"),
        (By.XPATH, ".//button[contains(@class,'dots') or contains(@aria-label,'ções') or contains(@aria-label,'enu')]"),
        (By.XPATH, ".//td[last()]//button"),
        (By.XPATH, ".//td[last()]//*[self::i or self::span][contains(@class,'dot') or contains(@class,'more') or contains(@class,'ellipsis')]"),
    ]
    btn_menu = None
    seletor_usado = None
    for by, sel in SELETORES_MENU:
        try:
            btn_menu = linha.find_element(by, sel)
            seletor_usado = sel
            break
        except Exception:
            continue
    if not btn_menu:
        if debug: log("    [debug] nenhum seletor de menu '⋮' encontrou elemento nesta linha")
        return None
    if debug: log(f"    [debug] botão de menu encontrado via: {seletor_usado}")

    try:
        btn_menu.click()
        if debug: log("    [debug] clique no botão de menu OK")
    except Exception as ex:
        if debug: log(f"    [debug] clique direto falhou ({ex}), tentando via JS")
        try:
            driver.execute_script("arguments[0].click();", btn_menu)
            if debug: log("    [debug] clique via JS OK")
        except Exception as ex2:
            if debug: log(f"    [debug] clique via JS também falhou: {ex2}")
            return None

    # 2. Achar e clicar em "Download XML" no menu que abriu (pode renderizar
    #    fora da linha, ex.: anexado ao <body>, por isso busca na página toda).
    #    Usa contains(., ...) em vez de contains(text(), ...) porque o texto
    #    pode estar dividido por um ícone dentro do link (contains(text(),..)
    #    só olha o nó de texto direto e quebra fácil nesse caso).
    XPATHS_DOWNLOAD_XML = [
        "//a[contains(., 'Download XML')]",
        "//li[contains(., 'Download XML')]",
        "//button[contains(., 'Download XML')]",
        "//*[contains(., 'Download XML')][self::span or self::div]",
    ]
    opcao_xml = None
    for xp in XPATHS_DOWNLOAD_XML:
        try:
            opcao_xml = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.XPATH, xp)))
            if debug: log(f"    [debug] 'Download XML' achado via: {xp}")
            break
        except Exception:
            continue

    if opcao_xml:
        try:
            opcao_xml.click()
            if debug: log("    [debug] opção 'Download XML' clicada")
        except Exception as ex:
            if debug: log(f"    [debug] achei mas não consegui clicar, tentando via JS: {ex}")
            try:
                driver.execute_script("arguments[0].click();", opcao_xml)
            except Exception as ex2:
                if debug: log(f"    [debug] clique via JS também falhou: {ex2}")
                opcao_xml = None

    if not opcao_xml:
        if debug:
            # Diagnóstico: mostra um pedaço do HTML perto de onde 'Download' aparece,
            # pra identificar a estrutura real sem precisar de outro print de tela.
            try:
                fonte = driver.page_source
                idx = fonte.find("Download")
                if idx >= 0:
                    trecho = fonte[max(0, idx-200):idx+300]
                    log(f"    [debug] HTML perto de 'Download': ...{trecho}...")
                else:
                    log("    [debug] a palavra 'Download' não aparece em nenhum lugar do HTML atual "
                        "— o menu provavelmente não abriu de verdade.")
            except Exception:
                pass
        # Fecha o menu (ESC) antes de desistir, pra não deixar aberto na próxima linha
        try: driver.execute_script("document.body.click();")
        except Exception: pass
        return None

    # 3. Esperar o arquivo .xml aparecer completo na pasta de downloads
    limite = time.time() + timeout_download
    while time.time() < limite:
        time.sleep(0.5)
        atuais = set(os.listdir(pasta_downloads))
        novos = atuais - arquivo_antes
        completos = [f for f in novos if f.lower().endswith(".xml")]
        if completos:
            if debug: log(f"    [debug] arquivo XML apareceu: {completos[0]}")
            return os.path.join(pasta_downloads, completos[0])
        # ainda baixando (.crdownload) — continua esperando
    if debug:
        log(f"    [debug] timeout esperando XML. Conteúdo da pasta agora: {os.listdir(pasta_downloads)}")
    return None


def _parsear_xml_nota(caminho_xml: str) -> dict:
    """Lê o XML da NFS-e e extrai os campos relevantes para o relatório de
    retenções. Usa busca por nome de tag (ignorando namespace) porque o
    schema exato pode variar; se os campos não vierem certos, o log de
    'AVISO' ajuda a identificar o que ajustar."""
    import xml.etree.ElementTree as ET

    dados = {}
    try:
        tree = ET.parse(caminho_xml)
        root = tree.getroot()

        def tag_sem_ns(el):
            return el.tag.split("}")[-1] if "}" in el.tag else el.tag

        # Mapa tag(lowercase) -> texto, para toda a árvore
        valores = {}
        for el in root.iter():
            nome = tag_sem_ns(el).lower()
            if el.text and el.text.strip():
                valores.setdefault(nome, el.text.strip())

        def achar(*candidatos):
            for c in candidatos:
                if c in valores:
                    return valores[c]
            # busca fuzzy por substring se não achou exato
            for chave, val in valores.items():
                if any(c in chave for c in candidatos):
                    return val
            return None

        dados["numero"]         = achar("nnfse", "numero", "nnf")
        dados["serie"]          = achar("serie", "sserie")
        dados["codigo_servico"] = achar("ctribnac", "coditemlistaservico", "itemlistaservico",
                                         "codigotributacaomunicipal", "ctribmun")
        dados["valor_servico"]  = achar("vservprest", "valorservico", "vliq", "vservicos")
        dados["iss_retido"]     = achar("vissretido", "vretissqn", "vissret")
        dados["irrf_retido"]    = achar("virrf", "vretirrf")
        dados["pis_retido"]     = achar("vpis", "vretpis")
        dados["cofins_retido"]  = achar("vcofins", "vretcofins")
        dados["csll_retido"]    = achar("vcsll", "vretcsll")
        dados["prestador_cnpj"] = achar("cnpj")
        dados["prestador_nome"] = achar("xnome", "razaosocial")
        dados["data_emissao"]   = achar("dhemi", "dataemissao", "demi")

        # Converte valores monetários textuais para float quando possível
        for campo in ("valor_servico","iss_retido","irrf_retido","pis_retido","cofins_retido","csll_retido"):
            if dados.get(campo):
                try: dados[campo] = float(str(dados[campo]).replace(",", "."))
                except Exception: pass

        dados = {k: v for k, v in dados.items() if v is not None}
    except Exception:
        pass

    return dados



    """Extrai dados detalhados da página de detalhe de uma NFS-e."""
    from selenium.webdriver.common.by import By

    dados = {}
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text

        # Código de serviço LC 116
        m = re.search(r'(?:Código de Serviço|Item Lista Serviço|LC\s*116)[:\s]*(\d{1,2}\.\d{2})', page_text)
        if m: dados["codigo_servico"] = m.group(1)

        # Número e série
        m = re.search(r'Número[:\s]*(\d+)', page_text)
        if m: dados["numero"] = m.group(1)
        m = re.search(r'Série[:\s]*(\w+)', page_text)
        if m: dados["serie"] = m.group(1)

        # Prestador
        m = re.search(r'Prestador[:\s\n]*([\w\s\-\.]+?)(?:\n|CNPJ|CPF)', page_text)
        if m: dados["prestador_nome"] = m.group(1).strip()
        m = re.search(r'CNPJ[:\s]*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', page_text)
        if m: dados["prestador_cnpj"] = m.group(1)

        # Valores
        for campo, padrao in [
            ("valor_servico",  r'Valor dos Serviços[:\s]*R?\$?\s*([\d\.,]+)'),
            ("iss_retido",     r'ISS Retido[:\s]*R?\$?\s*([\d\.,]+)'),
            ("irrf_retido",    r'IR Retido[:\s]*R?\$?\s*([\d\.,]+)|IRRF[:\s]*R?\$?\s*([\d\.,]+)'),
            ("pis_retido",     r'PIS Retido[:\s]*R?\$?\s*([\d\.,]+)'),
            ("cofins_retido",  r'COFINS Retido[:\s]*R?\$?\s*([\d\.,]+)'),
            ("csll_retido",    r'CSLL Retido[:\s]*R?\$?\s*([\d\.,]+)'),
        ]:
            m = re.search(padrao, page_text, re.IGNORECASE)
            if m:
                val_str = m.group(1) or m.group(2) or "0"
                dados[campo] = _parse_valor(val_str)

        # Data de emissão
        m = re.search(r'(?:Data de Emissão|Emissão)[:\s]*(\d{2}/\d{2}/\d{4})', page_text)
        if m: dados["data_emissao"] = m.group(1)

    except Exception:
        pass

    return dados


def _parse_valor(texto: str) -> float:
    """Converte string monetária brasileira para float."""
    txt = re.sub(r'[R$\s]', '', texto)
    txt = txt.replace('.', '').replace(',', '.')
    try: return float(txt)
    except Exception: return 0.0


def gerar_relatorio_excel(notas_analisadas: list, cnpj_tomador: str,
                           periodo: str, pasta_destino: str,
                           callback_log=None) -> str:
    """
    Gera relatório Excel com análise completa de retenções.
    Retorna caminho do arquivo gerado.
    """
    import openpyxl
    from openpyxl.styles import (Font, PatternFill, Alignment, Border, Side,
                                  numbers)
    from openpyxl.utils import get_column_letter

    def log(msg):
        if callback_log: callback_log(msg)

    log("Gerando relatório Excel...")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "NFS-e Entrada"

    # ── Paleta de cores ──────────────────────────────────────────────────────
    AZUL_ESC  = "FF0A1929"
    AZUL_MED  = "FF1A3A5C"
    AZUL_CLR  = "FF00C4FF"
    VERDE     = "FF00D084"
    AMARELO   = "FFFFD700"
    VERMELHO  = "FFFF4757"
    LARANJA   = "FFFF8C00"
    CINZA_CLR = "FFF0F4F8"
    CINZA_MED = "FFB0C4D8"
    BRANCO    = "FFFFFFFF"

    # Estilos
    def hdr_fill(cor): return PatternFill("solid", fgColor=cor)
    def fonte(negrito=False, cor="FF000000", tam=10):
        return Font(bold=negrito, color=cor, name="Consolas", size=tam)
    def borda_fina():
        s = Side(style="thin", color="FFB0C4D8")
        return Border(left=s, right=s, top=s, bottom=s)
    fmt_brl = '#,##0.00'
    aln_ctr = Alignment(horizontal="center", vertical="center", wrap_text=True)
    aln_esq = Alignment(horizontal="left",   vertical="center", wrap_text=True)
    aln_dir = Alignment(horizontal="right",  vertical="center")

    # ── Cabeçalho geral ──────────────────────────────────────────────────────
    ws.merge_cells("A1:T1")
    ws["A1"] = f"RELATÓRIO DE NFS-e RECEBIDAS — ANÁLISE DE RETENÇÕES"
    ws["A1"].font      = fonte(negrito=True, cor=BRANCO, tam=13)
    ws["A1"].fill      = hdr_fill(AZUL_ESC)
    ws["A1"].alignment = aln_ctr

    ws.merge_cells("A2:T2")
    ws["A2"] = f"CNPJ Tomador: {cnpj_tomador}    Período: {periodo}    Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws["A2"].font      = fonte(cor=BRANCO, tam=9)
    ws["A2"].fill      = hdr_fill(AZUL_MED)
    ws["A2"].alignment = aln_ctr
    ws.row_dimensions[1].height = 28
    ws.row_dimensions[2].height = 18

    # ── Colunas ──────────────────────────────────────────────────────────────
    COLUNAS = [
        # (titulo, largura, tipo)
        ("Nº Nota",          12, "str"),
        ("Série",             7, "str"),
        ("Data",             12, "str"),
        ("Prestador",        32, "str"),
        ("CNPJ Prestador",   20, "str"),
        ("Regime\nFornecedor",14, "str"),
        ("Cód. Serviço",     12, "str"),
        ("Descrição Serviço",38, "str"),
        ("Vlr. Serviço",     16, "num"),
        # ISS
        ("ISS\nNota",        12, "num"),
        ("ISS\nEsperado",    12, "num"),
        ("ISS\nStatus",      12, "status"),
        # IRRF
        ("IRRF\nNota",       12, "num"),
        ("IRRF\nEsperado",   12, "num"),
        ("IRRF\nStatus",     12, "status"),
        # PIS
        ("PIS\nNota",        12, "num"),
        ("PIS\nEsperado",    12, "num"),
        # COFINS
        ("COFINS\nNota",     12, "num"),
        ("COFINS\nEsperado", 12, "num"),
        # CSLL
        ("CSLL\nNota",       12, "num"),
        ("CSLL\nEsperado",   12, "num"),
        # Total
        ("Total\nRetido",    14, "num"),
        ("Total\nEsperado",  14, "num"),
        # Status e alertas
        ("Status",           14, "status"),
        ("Observações",      50, "str"),
    ]

    ROW_CAB = 4
    ws.row_dimensions[ROW_CAB].height = 36

    for col_idx, (titulo, largura, tipo) in enumerate(COLUNAS, start=1):
        cel = ws.cell(row=ROW_CAB, column=col_idx, value=titulo)
        cel.font      = fonte(negrito=True, cor=BRANCO, tam=9)
        cel.fill      = hdr_fill(AZUL_MED)
        cel.alignment = aln_ctr
        cel.border    = borda_fina()
        ws.column_dimensions[get_column_letter(col_idx)].width = largura

    # ── Dados ────────────────────────────────────────────────────────────────
    ROW_INI = ROW_CAB + 1
    total_ok = total_div = total_sem_cod = 0

    for i, nota in enumerate(notas_analisadas):
        row = ROW_INI + i
        bg_cor = CINZA_CLR if i % 2 == 0 else BRANCO
        status = nota.get("status_geral", "")

        if status == "OK":            bg_linha = "FFE8F5EA"; total_ok  += 1
        elif status == "DIVERGENCIA": bg_linha = "FFFFF3E0"; total_div += 1
        else:                         bg_linha = "FFFFE0E0"; total_sem_cod += 1

        fill_linha = hdr_fill(bg_linha)

        iss_nota   = nota.get("iss_retido_nota",    0)
        irrf_nota  = nota.get("irrf_retido_nota",   0)
        pis_nota   = nota.get("pis_retido_nota",    0)
        cof_nota   = nota.get("cofins_retido_nota", 0)
        csl_nota   = nota.get("csll_retido_nota",   0)
        irrf_esp   = nota.get("irrf_esperado",      0)
        pis_esp    = nota.get("pis_esperado",       0)
        cof_esp    = nota.get("cofins_esperado",    0)
        csl_esp    = nota.get("csll_esperado",      0)
        total_ret  = iss_nota + irrf_nota + pis_nota + cof_nota + csl_nota
        total_esp  = irrf_esp + pis_esp + cof_esp + csl_esp

        regime_map = {
            "SIMPLES_NACIONAL": "Simples Nacional",
            "NORMAL": "Normal",
            "NAO_VERIFICADO": "Não verificado",
        }
        regime_display = regime_map.get(nota.get("regime_prestador", ""), "")

        valores_linha = [
            nota.get("numero", ""),
            nota.get("serie", ""),
            nota.get("data_emissao", ""),
            nota.get("prestador_nome", ""),
            nota.get("prestador_cnpj", ""),
            regime_display,
            nota.get("codigo_servico", ""),
            nota.get("descricao_servico", ""),
            nota.get("valor_servico", 0),
            iss_nota, "–",        # ISS nota, ISS esperado (município)
            "OK" if not nota.get("deve_reter_iss") or iss_nota > 0 else "SEM RETENÇÃO",
            irrf_nota, irrf_esp,
            "OK" if abs(irrf_nota - irrf_esp) <= 0.05 else ("NÃO RETIDO" if irrf_esp > 0 and irrf_nota == 0 else "DIVERGÊNCIA"),
            pis_nota, pis_esp,
            cof_nota, cof_esp,
            csl_nota, csl_esp,
            total_ret, total_esp,
            status if status else "S/COD",
            " | ".join(nota.get("alertas", [])),
        ]

        for col_idx, val in enumerate(valores_linha, start=1):
            cel = ws.cell(row=row, column=col_idx, value=val)
            cel.fill   = fill_linha
            cel.border = borda_fina()
            cel.font   = fonte(tam=9)

            tipo_col = COLUNAS[col_idx-1][2] if col_idx <= len(COLUNAS) else "str"
            if tipo_col == "num" and isinstance(val, (int, float)):
                cel.number_format = fmt_brl
                cel.alignment = aln_dir
            elif tipo_col == "status":
                cel.alignment = aln_ctr
                if "OK" in str(val):
                    cel.font = fonte(negrito=True, cor=VERDE, tam=9)
                elif "NÃO" in str(val) or "DIVER" in str(val):
                    cel.font = fonte(negrito=True, cor=VERMELHO, tam=9)
            else:
                cel.alignment = aln_esq

            if COLUNAS[col_idx-1][0] == "Regime\nFornecedor" and val == "Simples Nacional":
                cel.font = fonte(negrito=True, cor="FF1E88E5", tam=9)

        ws.row_dimensions[row].height = 16

    # ── Aba Resumo ────────────────────────────────────────────────────────────
    ws_res = wb.create_sheet("Resumo")
    ws_res["A1"] = "RESUMO DA ANÁLISE"
    ws_res["A1"].font = fonte(negrito=True, cor=BRANCO, tam=12)
    ws_res["A1"].fill = hdr_fill(AZUL_ESC)
    ws_res.merge_cells("A1:D1")
    ws_res["A1"].alignment = aln_ctr
    ws_res.row_dimensions[1].height = 24

    resumo_dados = [
        ("Total de notas analisadas", len(notas_analisadas), BRANCO),
        ("Notas sem divergência (OK)", total_ok, "FFE8F5EA"),
        ("Notas com divergência de retenção", total_div, "FFFFF3E0"),
        ("Notas com código não encontrado", total_sem_cod, "FFFFE0E0"),
        ("", "", BRANCO),
        ("Total retido nas notas (ISS+IRRF+PIS+COFINS+CSLL)",
         sum(n.get("iss_retido_nota",0)+n.get("irrf_retido_nota",0)+
             n.get("pis_retido_nota",0)+n.get("cofins_retido_nota",0)+
             n.get("csll_retido_nota",0) for n in notas_analisadas), BRANCO),
        ("Total esperado de retenção (IRRF+PIS+COFINS+CSLL)",
         sum(n.get("irrf_esperado",0)+n.get("pis_esperado",0)+
             n.get("cofins_esperado",0)+n.get("csll_esperado",0) for n in notas_analisadas), BRANCO),
        ("Diferença (não retido)", 0, "FFFFE0E0"),
    ]

    for ri, (label, val, bg) in enumerate(resumo_dados, start=3):
        if not label: continue
        ws_res.cell(row=ri, column=1, value=label).font = fonte(tam=10)
        cel_val = ws_res.cell(row=ri, column=2, value=val)
        cel_val.fill = hdr_fill(bg)
        if isinstance(val, float): cel_val.number_format = fmt_brl
        for ci in range(1, 3):
            ws_res.cell(row=ri, column=ci).border = borda_fina()

    ws_res.column_dimensions["A"].width = 52
    ws_res.column_dimensions["B"].width = 20

    # ── Salvar ────────────────────────────────────────────────────────────────
    os.makedirs(pasta_destino, exist_ok=True)
    periodo_safe = periodo.replace("/","-").replace(" ","_")
    nome_arq = f"NFSE_ENTRADA_RETENCOES_{periodo_safe}.xlsx"
    caminho  = os.path.join(pasta_destino, nome_arq)
    wb.save(caminho)
    log(f"Relatório salvo: {caminho}")
    return caminho


def processar(cnpj_tomador: str, empresa: str, filial: str,
              data_inicio: str, data_fim: str,
              pasta_destino: str,
              callback_log=None, callback_progresso=None,
              headless: bool = False) -> dict:
    """
    Função principal — chamada pelo painel.
    Retorna dict com: ok, caminho_relatorio, total_notas, notas_divergentes, mensagem
    """
    def log(msg):
        if callback_log: callback_log(msg)
    def prog(pct, msg=""):
        if callback_progresso: callback_progresso(pct, msg)

    log(f"Iniciando apuração NFS-e de entrada")
    log(f"Empresa: {empresa} | Filial: {filial}")
    log(f"CNPJ: {cnpj_tomador}")
    log(f"Período: {data_inicio} a {data_fim}")
    log("─" * 56)

    try:
        # 1. Buscar notas no portal
        try:
            notas_raw = acessar_portal_nfse(
                cnpj_tomador=cnpj_tomador,
                data_inicio=data_inicio,
                data_fim=data_fim,
                empresa=empresa,
                filial=filial,
                callback_log=callback_log,
                callback_progresso=callback_progresso,
                headless=headless,
            )
        except Exception as ex_auth:
            # Se falhou mesmo com a janela fora da tela (ver comentário acima
            # sobre --window-position), tenta de novo com janela realmente
            # visível e maximizada — último recurso, caso algum certificado
            # específico realmente exija confirmação visual (ex.: PIN de
            # token). Só cai aqui se ainda estava no modo 'fora da tela'.
            if headless and "autenticação" in str(ex_auth).lower():
                log("AVISO: autenticação não completou com o Chrome fora da tela. "
                    "Tentando de novo com o navegador visível...")
                notas_raw = acessar_portal_nfse(
                    cnpj_tomador=cnpj_tomador,
                    data_inicio=data_inicio,
                    data_fim=data_fim,
                    empresa=empresa,
                    filial=filial,
                    callback_log=callback_log,
                    callback_progresso=callback_progresso,
                    headless=False,
                )
            else:
                raise

        if not notas_raw:
            return {"ok": False, "mensagem": "Nenhuma nota encontrada no período informado."}

        prog(85, "Analisando retenções")
        log(f"\nAnalisando retenções de {len(notas_raw)} nota(s)...")

        # 2. Analisar retenções de cada nota
        notas_analisadas = []
        for nota in notas_raw:
            resultado = verificar_retencoes(nota)
            notas_analisadas.append(resultado)
            if resultado["alertas"]:
                log(f"  ⚠ NF {resultado['numero']}: {' | '.join(resultado['alertas'])}")
            else:
                log(f"  ✓ NF {resultado['numero']}: OK")

        # 3. Gerar relatório
        prog(92, "Gerando Excel")
        periodo = f"{data_inicio} a {data_fim}"
        caminho = gerar_relatorio_excel(
            notas_analisadas=notas_analisadas,
            cnpj_tomador=cnpj_tomador,
            periodo=periodo,
            pasta_destino=pasta_destino,
            callback_log=callback_log,
        )

        total_div = sum(1 for n in notas_analisadas if n.get("status_geral") != "OK")
        prog(100, "Concluído")
        log(f"\n{'─'*56}")
        log(f"  Total de notas: {len(notas_analisadas)}")
        log(f"  Com divergência: {total_div}")
        log(f"  Relatório: {os.path.basename(caminho)}")
        log(f"{'─'*56}")

        return {
            "ok": True,
            "caminho_relatorio": caminho,
            "total_notas": len(notas_analisadas),
            "notas_divergentes": total_div,
            "notas": notas_analisadas,
            "mensagem": f"{len(notas_analisadas)} nota(s) processada(s). {total_div} com divergência.",
        }

    except Exception as ex:
        traceback.print_exc()
        return {"ok": False, "mensagem": str(ex)}