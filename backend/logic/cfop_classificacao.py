"""
TABELA DE CFOPs - Classificação para Concessionárias
Fonte: SEFAZ-PE / SPED Fiscal
Atualizado: 2026-05

Estrutura:
    CFOP_MAP[cfop] = (operacao, tipo, regime)
    - operacao : texto da col G
    - tipo     : texto da col H
    - regime   : 'Normal NC' | 'Cumulativo' | 'Zero' | 'Monofasico'
"""

CFOP_MAP = {
    # ─── VENDAS DE MERCADORIAS ────────────────────────────────────────────
    # 5102 / 6102 — Venda de mercadoria adquirida ou recebida de terceiros
    '5102': ('Venda', 'Peças e Acessórios',        'Normal NC'),   # com NCM
    '6102': ('Venda', 'Peças e Acessórios',        'Normal NC'),   # interestadual com NCM
    # sem NCM → Veículo Usado (tratado em classificar_operacao pela ausência de NCM)

    # 5103 / 6103 — Venda de produção do estabelecimento
    '5103': ('Venda', 'Peças e Acessórios',        'Normal NC'),
    '6103': ('Venda', 'Peças e Acessórios',        'Normal NC'),

    # 5104 / 6104 — Venda de mercadoria sujeita ao regime de ST
    '5104': ('Venda', 'Peças e Acessórios',        'Monofasico'),
    '6104': ('Venda', 'Peças e Acessórios',        'Monofasico'),

    # 5105 / 6105 — Venda de produção do estabelecimento sujeita a ST
    '5105': ('Venda', 'Peças e Acessórios',        'Monofasico'),
    '6105': ('Venda', 'Peças e Acessórios',        'Monofasico'),

    # 5109 / 6109 — Venda de produção para não contribuinte
    '5109': ('Venda', 'Peças e Acessórios',        'Normal NC'),
    '6109': ('Venda', 'Peças e Acessórios',        'Normal NC'),

    # 5110 / 6110 — Venda de produção do estabelecimento, destinada a outro estado
    '5110': ('Venda', 'Peças e Acessórios',        'Normal NC'),
    '6110': ('Venda', 'Peças e Acessórios',        'Normal NC'),

    # 5108 / 6108 — Venda de mercadoria adquirida de terceiros, destinada a não contribuinte
    '5108': ('Venda', 'Peças e Acessórios',        'Normal NC'),
    '6108': ('Venda', 'Peças e Acessórios',        'Normal NC'),

    # 5119 / 6119 — Vendas de mercadorias adquiridas por encomenda
    '5119': ('Venda', 'Peças e Acessórios',        'Normal NC'),
    '6119': ('Venda', 'Peças e Acessórios',        'Normal NC'),

    # 5401 / 6401 — Venda de produção sujeita a ST
    '5401': ('Venda', 'Peças e Acessórios',        'Monofasico'),
    '6401': ('Venda', 'Peças e Acessórios',        'Monofasico'),

    # 5402 / 6402 — Venda de produção em operação com ST
    '5402': ('Venda', 'Peças e Acessórios',        'Monofasico'),
    '6402': ('Venda', 'Peças e Acessórios',        'Monofasico'),

    # 5403 — Venda de mercadoria sujeita a ST, com ST retida anteriormente
    '5403': ('Venda', 'Peças e Acessórios',        'Monofasico'),

    # 5405 — Venda com ST já recolhida
    '5405': ('Venda', 'Peças e Acessórios',        'Monofasico'),  # com NCM
    # sem NCM → Veículo Novo

    # ─── VEÍCULOS ─────────────────────────────────────────────────────────
    # 6411 — Devolução de compra para industrialização em operação interestadual
    '6411': ('Venda', 'Peças e Acessórios',        'Monofasico'),

    # ─── ATIVO IMOBILIZADO ────────────────────────────────────────────────
    # 5551 / 6551 — Venda de bem do ativo imobilizado
    '5551': ('Venda', 'Ativo Imobilizado',          'Zero'),
    '6551': ('Venda', 'Ativo Imobilizado',          'Zero'),

    # 5552 / 6552 — Transferência de bem do ativo imobilizado
    '5552': ('Venda', 'Ativo Imobilizado',          'Zero'),
    '6552': ('Venda', 'Ativo Imobilizado',          'Zero'),

    # ─── GARANTIA / DEMONSTRAÇÃO ──────────────────────────────────────────
    # 5949 / 6949 — Outras saídas não especificadas (usado para garantia)
    '5949': ('Garantia', 'Garantia',                'Zero'),
    '6949': ('Garantia', 'Garantia',                'Zero'),

    # 5915 / 6915 — Remessa de mercadoria para demonstração
    '5915': ('Garantia', 'Demonstração',            'Zero'),
    '6915': ('Garantia', 'Demonstração',            'Zero'),

    # 5916 / 6916 — Retorno de mercadoria de demonstração
    '5916': ('Garantia', 'Demonstração',            'Zero'),
    '6916': ('Garantia', 'Demonstração',            'Zero'),

    # ─── DEVOLUÇÕES ───────────────────────────────────────────────────────
    # 5201 / 6201 — Devolução de compra para industrialização
    '5201': ('Devolução', 'Devolução',              'Normal NC'),
    '6201': ('Devolução', 'Devolução',              'Normal NC'),

    # 5202 / 6202 — Devolução de compra para comercialização
    '5202': ('Devolução', 'Devolução',              'Normal NC'),
    '6202': ('Devolução', 'Devolução',              'Normal NC'),

    # 5410 / 6410 — Devolução de compra de mercadoria sujeita a ST
    '5410': ('Devolução', 'Devolução',              'Monofasico'),
    '6410': ('Devolução', 'Devolução',              'Monofasico'),

    # 5411 / 6411 — Devolução de compra em operação com ST
    '5411': ('Devolução', 'Devolução',              'Monofasico'),

    # ─── COMBUSTÍVEIS ─────────────────────────────────────────────────────
    # 5651 / 6651 — Venda de combustível de produção própria
    '5651': ('Venda', 'Combustível',                'Normal NC'),
    '6651': ('Venda', 'Combustível',                'Normal NC'),

    # 5652 / 6652 — Venda de combustível adquirido de terceiros
    '5652': ('Venda', 'Combustível',                'Normal NC'),
    '6652': ('Venda', 'Combustível',                'Normal NC'),

    # 5653 / 6653 — Venda de combustível sujeito a ST
    '5653': ('Venda', 'Combustível',                'Monofasico'),
    '6653': ('Venda', 'Combustível',                'Monofasico'),

    # 5655 — Venda de material de uso e consumo
    '5655': ('Venda', 'Material de Uso e Consumo',  'Normal NC'),
    '6655': ('Venda', 'Material de Uso e Consumo',  'Normal NC'),

    # 5656 / 6656 — Venda de combustível adquirido de terceiros, consumidor final
    '5656': ('Venda', 'Combustível',                'Normal NC'),
    '6656': ('Venda', 'Combustível',                'Normal NC'),

    # ─── MATERIAL DE USO / CONSUMO ────────────────────────────────────────
    # 5157 / 6157 — Transferência de produção do estabelecimento
    '5157': ('Venda', 'Material de Uso e Consumo',  'Normal NC'),
    '6157': ('Venda', 'Material de Uso e Consumo',  'Normal NC'),

    # ─── SERVIÇOS ─────────────────────────────────────────────────────────
    # Sem CFOP — identificado pelo código SERV na col D
    # Classificação vem do arquivo 170.csv:
    #   COMISS* → Comissão
    #   VENDA DIRETA* → Venda Direta
    #   demais → Oficina

    # ─── TRANSFERÊNCIAS ───────────────────────────────────────────────────
    # 5151 / 6151 — Transferência de produção do estabelecimento
    '5151': ('Transferência', 'Transferência',      'Normal NC'),
    '6151': ('Transferência', 'Transferência',      'Normal NC'),

    # 5152 / 6152 — Transferência de mercadoria adquirida de terceiros
    '5152': ('Transferência', 'Transferência',      'Normal NC'),
    '6152': ('Transferência', 'Transferência',      'Normal NC'),

    # ─── REMESSAS ─────────────────────────────────────────────────────────
    # 5901 / 6901 — Remessa para industrialização por encomenda
    '5901': ('Remessa', 'Remessa',                  'Zero'),
    '6901': ('Remessa', 'Remessa',                  'Zero'),

    # 5902 / 6902 — Retorno de mercadoria utilizada em processo de industrialização
    '5902': ('Remessa', 'Remessa',                  'Zero'),
    '6902': ('Remessa', 'Remessa',                  'Zero'),

    # 5906 / 6906 — Remessa para depósito fechado ou armazém geral
    '5906': ('Remessa', 'Remessa',                  'Zero'),
    '6906': ('Remessa', 'Remessa',                  'Zero'),

    # 5922 / 6922 — Lançamento efetuado a título de simples faturamento
    '5922': ('Remessa', 'Remessa',                  'Zero'),
    '6922': ('Remessa', 'Remessa',                  'Zero'),

    # ─── TEST DRIVE / DEMONSTRAÇÃO ────────────────────────────────────────
    # 5910 / 6910 — Remessa em bonificação, doação ou brinde
    '5910': ('Saída', 'Test Drive',                 'Zero'),
    '6910': ('Saída', 'Test Drive',                 'Zero'),

    # 5911 / 6911 — Remessa de amostra grátis
    '5911': ('Saída', 'Amostra',                    'Zero'),
    '6911': ('Saída', 'Amostra',                    'Zero'),

    # 5912 / 6912 — Remessa de mercadoria com fim específico de exportação
    '5912': ('Saída', 'Exportação',                 'Zero'),
    '6912': ('Saída', 'Exportação',                 'Zero'),
}


def classificar_cfop(cfop_str, tem_ncm=True):
    """
    Retorna (operacao, tipo) para um CFOP.
    Aplica regras especiais para 5102/6102 e 5405 baseadas em tem_ncm.
    Retorna ('', '') para CFOPs desconhecidos.
    """
    cfop_str = str(cfop_str).strip()

    # Regras especiais por NCM
    if cfop_str in ('5102', '6102'):
        return ('Venda', 'Peças e Acessórios') if tem_ncm else ('Venda', 'Veículo Usado')
    if cfop_str == '5405':
        return ('Venda', 'Peças e Acessórios') if tem_ncm else ('Venda', 'Veículo Novo')

    entry = CFOP_MAP.get(cfop_str)
    if entry:
        return entry[0], entry[1]

    return '', ''  # CFOP desconhecido — deixar vazio para correção manual


if __name__ == '__main__':
    print("=== TABELA DE CFOPs CADASTRADOS ===")
    print(f"Total: {len(CFOP_MAP)} CFOPs\n")
    grupos = {}
    for cfop, (op, tipo, regime) in sorted(CFOP_MAP.items()):
        key = f"{op} / {tipo}"
        grupos.setdefault(key, []).append(cfop)
    for g, cfops in sorted(grupos.items()):
        print(f"  {g}: {', '.join(cfops)}")
