/* ==========================================================================
   BASE DE CONHECIMENTO LOCAL DO ASSISTENTE — RIOZEN
   Agora organizada por CATEGORIA (o usuário escolhe o assunto num menu
   antes de perguntar). Cada categoria tem sua lista de tópicos; a busca
   por palavra-chave roda só dentro da categoria escolhida.

   Fonte da categoria "rotina_nbs": ROTINA_FISCAL_GERAL_atual.docx.
   ⚠️ A seção de senhas/credenciais do documento original foi
   DELIBERADAMENTE excluída daqui — um assistente por texto nunca deve
   guardar login/senha em conteúdo pesquisável.

   Pra adicionar um tópico novo numa categoria existente: copia o formato
   de uma entrada (id/palavras/resposta) dentro do array certo. Pra criar
   uma categoria nova: adiciona em CATEGORIAS_ASSISTENTE e cria o array
   correspondente aqui embaixo.
   ========================================================================== */

const CATEGORIAS_ASSISTENTE = [
  {
    id: "rotina_nbs",
    rotulo: "📋 Rotina NBS (passo a passo)",
    promptEscolha: "Show! Sobre qual processo da rotina NBS você quer saber? Pode escrever livre — por exemplo \"emissão de nota\", \"cancelamento\", \"apuração de ISS\", \"apuração de ICMS\", \"test drive\", \"impostos retidos\"...",
    semResposta: "Não achei nada na rotina NBS batendo com isso. Tenta descrever de outro jeito, ou digita \"menu\" pra voltar e escolher outro assunto.",
  },
  {
    id: "modulos_sistema",
    rotulo: "🖥️ Onde acho um módulo no painel",
    promptEscolha: "Qual módulo do sistema você está procurando?",
    semResposta: "Não achei esse módulo de cara. Digita \"menu\" pra voltar, ou me conta mais o que você precisa que eu tento te ajudar com IA.",
  },
  {
    id: "sobre_riozen",
    rotulo: "🏢 Sobre a Riozen / o assistente",
    promptEscolha: "Pode perguntar!",
    semResposta: null,
  },
  {
    id: "reforma_tributaria",
    rotulo: "⚖️ Reforma Tributária (LC 214/2025)",
    promptEscolha: "Pode perguntar! Por exemplo: \"calendário de transição\", \"o que é o IBS\", \"imposto seletivo em veículos\", \"crédito\", \"cashback\", \"cesta básica\"...",
    semResposta: "Não achei nada batendo com isso na Reforma Tributária. Tenta descrever de outro jeito, ou digita \"menu\" pra voltar.",
  },
  {
    id: "outro",
    rotulo: "💬 Outro assunto (uso IA de verdade)",
    promptEscolha: "Pode perguntar — vou consultar a IA pra te responder direito.",
    semResposta: null,
    sempreIA: true, // nessa categoria nem tenta a base local, cai direto na IA
  },
];

const BASE_CONHECIMENTO_ASSISTENTE = {

  // ────────────────────────────────────────────────────────────────────
  // ROTINA NBS — passo a passo dos processos fiscais/contábeis no NBS
  // ────────────────────────────────────────────────────────────────────
  rotina_nbs: [
    {
      id: "nbs_cancelar_nf_servico",
      palavras: ["cancelar", "cancelamento", "servico", "nf servico"],
      resposta:
        "Cancelamento de NF de Serviço (sozinha):\n" +
        "1. Peças > NFVendas\n" +
        "2. Ctrl+L pra selecionar a loja correspondente\n" +
        "3. Buscar a nota fiscal — desmarca as caixinhas de data (E. Inicial/E. Final) pra buscar em qualquer posição\n" +
        "4. Se a nota é do mês corrente, é só clicar no botão Cancelar (fica na barra de ferramentas ao lado de Devolver/Estornar)\n\n" +
        "Se a NF de serviço estiver vinculada a uma NF-e de peças ou O.S: em vez do botão Cancelar direto, busca pelo número da NF ou pelo número da O.S no campo \"O.S. Fábrica\", clica com o botão direito do mouse na nota e escolhe \"Cancelar NF Serviço Relacionada a NF-e\" (tem também a opção \"Cancelar NF Serviço na Prefeitura\" logo abaixo dessa, caso seja esse o caso).",
    },
    {
      id: "nbs_cancelar_devolver_nf_pecas",
      palavras: ["cancelar", "devolucao", "devolver", "pecas", "danfe"],
      resposta:
        "Cancelamento/Devolução de NF de Peças (DANFE):\n" +
        "1. Peças > NFVendas\n" +
        "2. Ctrl+L pra selecionar a loja\n" +
        "3. Buscar a nota\n" +
        "4. Se estiver dentro do prazo (até 24h da emissão): botão Cancelar direto\n" +
        "5. Se estiver fora do prazo: usa o botão Devolver/Estornar em vez de cancelar\n\n" +
        "Devolução de peças de fábrica Toyota: o caminho muda um pouco — Peças > Compras > Ctrl+L > buscar a nota > Devolver/Estornar > informar o Motivo da Devolução > marcar (flegar) as opções necessárias > confirmar. Depois de confirmar, anota a numeração da nota gerada e gera o PDF junto com o XML pra enviar por e-mail.\n\n" +
        "Devolução com nota do fornecedor (peças): Peças > NFVendas > Ctrl+L > buscar nota > Devolver/Estornar > Devolução > marca a opção \"Usar número de nota do fornecedor\" > informa número da nota, série, data de emissão e chave de acesso da nota do fornecedor.",
    },
    {
      id: "nbs_devolucao_veiculo",
      palavras: ["devolucao", "devolver", "veiculo", "danfe"],
      resposta:
        "Devolução de NF de Veículos (DANFE) com nota do fornecedor:\n" +
        "1. Peças > Compras > Incluir > Outras Operações > Operação 28\n" +
        "2. Informar o chassi e Aceitar\n" +
        "3. Confirmar o cliente e preencher com as informações da nota do cliente\n" +
        "4. Natureza: Devolução Veículo Novo usa CFOP 1411, Veículo Usado usa CFOP 1202\n" +
        "5. Aba Faturamento (1/1/1) e clicar em Gerar\n" +
        "6. Aba Situações Especiais: preencher o campo \"Chave NF-e/CT-e\" com a chave de acesso da nota\n" +
        "7. Confirmar e dar OK\n\n" +
        "Resumo enxuto do caminho (peças > compras > diversos > outras operações > operação 28 > informar chassi > aceitar > confirmar cliente > natureza (CFOP 1411 ou 1202) > aba faturamento 1/1/1 > confirma).",
    },
    {
      id: "nbs_carta_correcao",
      palavras: ["carta", "correcao", "cce", "cc-e", "errata"],
      resposta:
        "Errata (Carta de Correção - CC-e):\n" +
        "1. NFVendas > buscar a nota fiscal\n" +
        "2. Clicar no botão \"Gerar CC-e\" (fica no rodapé da tela)\n" +
        "3. Na tela \"Carta de Correção Eletrônica\", escolher em Especificações o campo que precisa corrigir (ex: Razão Social, Endereço, Natureza da Operação, Data de Emissão, Descrição dos Produtos, etc.) e mover pra Correções, preenchendo a descrição da correção\n" +
        "4. Preencher conforme a alteração pedida no e-mail e Confirmar\n" +
        "5. Depois, consultar a nota de novo, botão direito do mouse > \"Consultar Carta de Correção\" > imprimir e enviar por e-mail\n\n" +
        "⚠️ Atenção ao que a Carta de Correção NÃO pode alterar (regra do §1º-A do art. 7º do Convênio S/N, de 15/12/1970): não pode ser usada se o erro envolver variáveis que determinam o valor do imposto (base de cálculo, alíquota, diferença de preço, quantidade, valor da operação/prestação), correção de dados cadastrais que mude o remetente ou destinatário, ou a data de emissão/saída. Esses casos precisam de outro procedimento, não de CC-e.",
    },
    {
      id: "nbs_emissao_comissao",
      palavras: ["emissao", "emitir", "nota", "comissao"],
      resposta:
        "Emissão de Nota de Comissão:\n" +
        "1. Peças > NFVendas > Ctrl+L (selecionar a loja)\n" +
        "2. Saída Diversas\n" +
        "3. Tipo: Operação 23 - Diversos Serviços - Diversos\n" +
        "4. Preencher CPF ou CNPJ do cliente\n" +
        "5. Aba \"Fins Diversos\": selecionar a natureza do serviço (ISS: Serviços Comissões, código 6933/5933) e o tipo de serviço diverso\n" +
        "   • Se não vier especificado o tipo de comissão no pedido, usar: Intermediação de Vendas\n" +
        "   • Se for comissão de venda direta de veículo, existe o checkbox \"É Comissão de Venda Direta (TIPI 87.03 e 87.04)\" — marcar quando for o caso\n" +
        "6. Informar o Valor Serviço (valor bruto) e Salvar\n" +
        "7. Ir pra aba Pagamento: na lista de Formas de Pagamento selecionar \"Comissões\" (código 303) e clicar na seta pra mover pra \"Formas/Condições Escolhidas\"\n" +
        "8. Confirmar o valor no popup que abre e depois Confirmar a nota inteira\n" +
        "9. Anotar a numeração da NF que foi gerada",
    },
    {
      id: "nbs_emissao_venda_sucata",
      palavras: ["emissao", "emitir", "nota", "venda", "sucata", "pneu", "oleo", "remessa"],
      resposta:
        "Emissão de Nota de Venda (sucata/pneu/óleo):\n" +
        "1. NF Vendas > Saída Diversas\n" +
        "2. Tipo: Operação 21 - Saída sem retirada do estoque\n" +
        "3. Preencher CPF ou CNPJ do cliente\n" +
        "4. Aba \"Itens\": no campo de código digitar \"USD\" que traz as opções — os códigos padrão são USD2024001 (filtro de óleo contaminado), USD2024002 (óleo usado), USD2024003 (pneu usado), USD2024004 (alumínio), USD2024005 (sucata)\n" +
        "5. Selecionar o item, clicar na seta vermelha, informar a quantidade pedida e confirmar\n" +
        "6. Voltar (ícone anterior) e informar o valor nos campos \"Preço Unitário Nota\" e \"Preço Unit. Líquido\"\n" +
        "7. Salvar e ir pra aba Natureza, selecionando o CFOP de acordo com a operação\n" +
        "8. Aba Pagamento: se for venda, selecionar \"A Prazo\"\n" +
        "9. Confirmar e anotar a numeração da NF gerada\n\n" +
        "Nota de Remessa (filtro de óleo): é o mesmo passo a passo da venda de sucata — o que muda é o código do item e a Natureza usada.",
    },
    {
      id: "nbs_apuracao_iss",
      palavras: ["apuracao", "iss", "livro fiscal"],
      resposta:
        "Apuração de ISS:\n" +
        "1. Gerar o Livro Fiscal: Adm Back Office > NBS Fiscal > Livros Fiscais > Manutenção > repetir em Nota Fiscal de Entrada e Nota Fiscal de Saída\n" +
        "2. Clicar no ícone de atualizar, depois \"Gerar Livro Fiscal\" (ou \"Cancelar Livro Fiscal\" se precisar refazer)\n" +
        "3. Preencher a data de acordo com o fechamento e confirmar\n" +
        "4. Pra tirar o livro em si: Livros Fiscais > Relatórios > Livros Fiscais > Livro de ISS. Preenche o período (Inicial/Final) e confirma\n" +
        "5. Salvar o PDF gerado na pasta: SKYBOX > Contabilidade > Fiscal > ISS > escolher loja e mês\n\n" +
        "Consulta da parte contábil do ISS: Adm Back Office > Contab > Ctrl+L (escolher a loja) > Razão > F5 no campo Conta > buscar por descrição \"ISS\" > selecionar a conta ISS A PAGAR (código reduzido 232, conta completa 2.1.2.03.02.001).\n\n" +
        "Gerar o financeiro/compromisso do ISS: Adm Back Office > SISFIN > Contas a Pagar > Compromisso. Fornecedor é a Prefeitura correspondente; Natureza \"IM_ISS A PAGAR\"; contabilização padrão código 17 (FIS-ISSQN A RECOLHER). Preencher valor, tipo de pagamento (normalmente A Prazo) e dar OK.",
    },
    {
      id: "nbs_midia_cooperada",
      palavras: ["midia", "cooperada", "reembolso"],
      resposta:
        "Lançamento de Mídia Cooperada (contabilidade):\n" +
        "1. Skybox > Garantias > pasta do ano\n" +
        "2. Verificar em cada loja se houve reembolso de mídia cooperada (o lançamento costuma aparecer como \"Reemb Mídia Conjunta (50%)\" com o mês de referência)\n" +
        "3. Depois de verificar todas as lojas, fazer o lançamento contábil: Adm Back Office > Contab > Lançamento > Manutenção > Criar Lote\n" +
        "   • Débito: 1120112006\n" +
        "   • Crédito: 6110801011\n" +
        "   • CC: 51\n" +
        "   • Histórico: 91",
    },
    {
      id: "nbs_apuracao_icms",
      palavras: ["apuracao", "icms", "conciliacao", "fecp"],
      resposta:
        "Apuração de ICMS:\n" +
        "1. NBS Fiscal > Livros Fiscais > Relatórios > Livros Fiscais\n" +
        "2. Gerar Livro Entrada ICMS, Gerar Livro Saída ICMS e Gerar Livro Apuração (nessa ordem)\n" +
        "3. Na tela de apuração tem as abas Débito, Crédito, Saldo e Informações Complementares — o Débito mostra \"001 - Por Saída/Prestação com Débito do Imposto\", \"002 - Outros Débitos\" e \"003 - Estorno de Créditos\"\n\n" +
        "Depois disso, conferir o razão das contas: 2120301001 (ICMS), 1120205001 (ICMS a Recuperar), 2120301002 (ICMS ST), 2120301003 (DIFAL).\n\n" +
        "Conciliação — o que analisar:\n" +
        "• Entradas CFOP 1102 | 2102 | 1202: abrir cada nota fiscal no Via Nuvem e conferir CFOP e valor do imposto\n" +
        "• Saídas com CFOP 6108 e 6404: fazer o processo de guias do ST\n" +
        "• CFOP 6411: estorno dos valores creditados só no livro, como estorno de débito\n" +
        "• CFOP 5949 com valor creditado: estorno de débito no contábil E no livro fiscal\n" +
        "• Venda de Ativo Imobilizado (CFOP 5551): conferir o cálculo — essas vendas não contabilizam o valor do FECP automaticamente, precisa de lançamento manual\n\n" +
        "Cálculo do FECP: (Valor Total Base ICMS Saídas CFOP-5 − Valor Total Base ICMS Entrada CFOP-1) × 2% = FECP.\n\n" +
        "Estorno de NF de entrada (ativo imobilizado): Débito 2120301001 / Crédito 1120101001.",
    },
    {
      id: "nbs_efd_icms",
      palavras: ["efd", "sped", "icms", "bloco c"],
      resposta:
        "Gerar EFD ICMS (SPED Fiscal):\n" +
        "1. NBS Fiscal > Outros > SPED ICMS > SPED Fiscal\n" +
        "2. Nomear o arquivo pra salvar na máquina e depois exportar pra área de trabalho\n" +
        "3. Na aba Bloco C, marcar (flegar) TODAS as opções:\n" +
        "   • Não levar Base Pis/Cofins no Registro C170 quando alíq=0 (compra e venda)\n" +
        "   • Gerar Registro C175 (somente NF-e de Entrada)\n" +
        "   • Gerar Registro C191\n" +
        "   • Gerar a Descrição do Produto no Registro C170 (NF-e Entrada) com a mesma descrição da NF-e do fornecedor\n" +
        "4. Clicar em Gerar — o TXT fica salvo no PC, pronto pra subir no aplicativo do SPED.",
    },
    {
      id: "nbs_efd_contribuicoes",
      palavras: ["efd", "sped", "contribuicoes", "bloco f"],
      resposta:
        "Gerar EFD Contribuições (SPED PIS/COFINS):\n" +
        "1. NBS Fiscal > Outros > SPED PIS/COFINS > SPED Fiscal PIS/COFINS\n" +
        "2. Confirmar \"OK\" no consolidado\n" +
        "3. Preencher só o Bloco F — informar todos os créditos da apuração que vêm da planilha de saída, no valor proporcional: Receita Financeira, Receita Sem NF, Depreciação e Despesas\n" +
        "4. Depois é só Gerar — o TXT fica salvo no PC, pronto pra subir no aplicativo.",
    },
    {
      id: "nbs_apuracao_pis_cofins_extracao",
      palavras: ["pis", "cofins", "relatorio", "extracao", "creditos", "recolher"],
      resposta:
        "Apuração e extração de relatórios pra PIS e COFINS (dentro do NBS):\n" +
        "1. NBS Fiscal > Livros Fiscais > Relatórios > Relatório de PIS/COFINS\n" +
        "2. \"Lista PIS/COFINS a Recolher\" — pra gerar o débito (saída). Dá pra filtrar por operação, período, mostrar itens da nota, exportar pra Excel, mostrar Base e Valor ICMS, consolidar filiais e mostrar Faturamento Bruto\n" +
        "3. \"Lista Créditos de PIS/Cofins\" — pra gerar o crédito (entrada). Essa tela NÃO deixa consolidar filiais — por isso o crédito sempre sai um arquivo separado por filial. Dá pra filtrar notas Com PIS/Cofins, mostrar Base e Descrição dos Itens e exportar pra planilha\n\n" +
        "As planilhas prontas de cada mês também ficam salvas em: Skybox > Contabilidade > Fiscal > PIS e COFINS > pasta do ano > pasta do mês.",
    },
    {
      id: "nbs_escrituracao_test_drive",
      palavras: ["escrituracao", "cadastrar", "patrimonio", "test", "drive"],
      resposta:
        "Escrituração de Test Drive (cadastro de patrimônio):\n" +
        "1. Peças > Compras > Incluir > Patrimônio > Compra\n" +
        "2. Preencher de acordo com a nota fiscal, na aba Capa Nota Fiscal (dados do fornecedor, número/série, chave NF-e, base de cálculo, valores de ICMS/IPI)\n" +
        "3. Na aba Itens Nota: clicar em \"Cadastrar Novo Patrimônio\" > Yes\n" +
        "4. Código de patrimônio padrão: PT + mês + ano + final do chassi. Exemplo: PT022026T0757997\n" +
        "5. Aba \"Dados do Veículo\": preencher tudo de acordo com a nota fiscal (chassi, cor, motor, renavam, placa quando houver)\n" +
        "6. Aba Financeiro: condição de pagamento a prazo, gerar a parcela\n" +
        "7. Aba \"Total Nota\": clicar em Recálculo pra conferir se o \"Imposto Digitado\" bate com a \"Soma Imposto dos Itens\"\n" +
        "8. Aba \"Locações\": local Patrimônio, e só confirmar\n" +
        "9. Depois do lançamento no NBS, informar esse veículo na planilha de controle do Skybox: Skybox > Test Drive > Riozen ou BYD (de acordo com a nota fiscal) — a planilha tem colunas de Veículo, Cor, Ano/Modelo, Placa, Chassis, dados da Nota Fiscal e Usuário.",
    },
    {
      id: "nbs_liberacao_test_drive",
      palavras: ["liberacao", "liberar", "disponibilizar", "test", "drive"],
      resposta:
        "Liberação de Test Drive no sistema:\n" +
        "⏱ Prazo: Toyota libera 1 ano depois da escrituração; BYD libera 6 meses depois.\n\n" +
        "1. Adm Back Office > NBS CIAP > Ctrl+L (escolher a loja) > Patrimônio > Cadastro de Patrimônio\n" +
        "2. Consultar a planilha do Skybox pra achar o número da nota fiscal de fábrica e informar no campo \"N.º Nota Compra\"\n" +
        "3. Ir pra aba Cadastro > Dados Veículo, clicar em Alteração antes de tudo\n" +
        "4. Informar o Renavam e a Placa que devem estar no corpo do e-mail da solicitação\n" +
        "5. Dar OK, voltar pra aba Dados do Veículo, clicar em Alteração de novo\n" +
        "6. Clicar em \"Disponibilizar p/Venda\"\n" +
        "7. Selecionar: Pátio (de acordo com a planilha do test drive), Situação = Sempre Disponível, Tipo = Normal\n" +
        "8. Campo Preço de Venda: informar o valor descrito no e-mail da solicitação\n" +
        "9. Confirmar e tirar print da tela que confirma \"Veículo disponibilizado para venda.\"\n" +
        "10. Dar baixa na planilha de controle, movendo as informações do veículo pra aba de Vendidos.",
    },
    {
      id: "nbs_impostos_retidos",
      palavras: ["impostos", "retidos", "retencao", "reinf", "darf"],
      resposta:
        "Impostos Retidos (consolidado):\n" +
        "1. Adm Back > Contab > Razão > F5 no campo Conta, e buscar pelas contas de retenção:\n" +
        "   • 2120309001 — Retenção IR Nota Fiscal\n" +
        "   • 2120309003 — Retenção IR Aluguel\n" +
        "   • 2120311001 — Retenção PIS/COFINS/CSLL\n" +
        "   • 2120310001 — Retenção INSS\n" +
        "2. Buscar as notas em PDF e salvar na pasta do Skybox (Contabilidade > Fiscal > Impostos Retidos)\n" +
        "3. Com as notas salvas, preencher a planilha de controle (que já vem sempre na pasta do mês anterior)\n" +
        "4. Provisionar os impostos: NBS Fiscal > Outros > Impostos a Recolher — filtrar por Entrada e o período, marcar \"Vai Gerar Imposto\" e \"Vai Gerar Darf\", selecionar o imposto e clicar na seta vermelha\n" +
        "5. Aba Compromisso: preencher com o vencimento padrão do imposto e gerar o compromisso financeiro\n" +
        "6. Preencher de acordo com o imposto e o órgão responsável (ex: Prefeitura do Rio de Janeiro pro ISS)\n" +
        "7. Aba Contabilização e confirmar — salvar o arquivo financeiro que aparece depois de confirmar\n\n" +
        "Contabilização padrão por imposto:\n" +
        "• IR: código 11\n" +
        "• PIS/COFINS/CSLL: código 20\n" +
        "• INSS: código 18\n" +
        "• IR Aluguel: código 117\n" +
        "• ISS: código 17 (a recolher) ou 19 (retido)\n\n" +
        "A pasta dos retidos deve conter: Razão, Financeiro, Notas Fiscais, Planilha de Controle e o DARF, depois da declaração na REINF.\n\n" +
        "Relatório financeiro de impostos retidos: Adm Back Office > SISFIN > Pagar, filtrar (página 1: vencimento da provisão; página 4: filtrar o imposto) e usar \"Imprime Consulta\" (com ou sem subtotal, ou com observação) pelo botão direito do mouse.",
    },
    {
      id: "nbs_saida_retorno_demonstracao",
      palavras: ["saida", "retorno", "demonstracao"],
      resposta:
        "Saída e Retorno de Demonstração:\n\n" +
        "Retorno: Peças > Compras > Diversos > Outras Operações > Operação 33. Buscar o cliente e Aceitar, informar a Natureza (CFOP), Confirmar, informar o final do chassi, Aceitar, e responder \"Sim\" quando perguntar se é retorno.\n\n" +
        "Saída: Peças > NF Vendas > Saídas Diversas > Operação 32 (Demonstração). Informar o final do chassi, Aceitar, escolher a Natureza (CFOP) e Confirmar.",
    },
    {
      id: "nbs_certidoes",
      palavras: ["certidoes", "certificados"],
      resposta:
        "Certidões — controle de certificados:\n" +
        "Skybox > Certidões > Planilha de Controle. É lá que fica a planilha usada pra acompanhar a validade das certidões da empresa.",
    },
  ],

  // ────────────────────────────────────────────────────────────────────
  // REFORMA TRIBUTÁRIA (LC 214/2025) — IBS, CBS, IS
  // Fonte: LC214_2025_Reforma_Tributaria_Riozen.pdf (síntese interna) +
  // conferência direta com o texto oficial da LC 214/2025 nos pontos
  // mais sensíveis (base de cálculo, regra de crédito).
  // ⚠️ O resumo interno tem um erro que foi corrigido aqui: ele diz que
  // o IBS/CBS é calculado "por dentro", mas o art. 12, §2º, I da lei diz
  // o contrário — o imposto NÃO integra a própria base ("por fora").
  // ────────────────────────────────────────────────────────────────────
  reforma_tributaria: [
    {
      id: "rt_visao_geral",
      palavras: ["reforma", "tributaria", "novos tributos", "pis cofins icms iss"],
      resposta:
        "A Reforma Tributária (EC 132/2023, regulamentada pela LC 214/2025) cria três tributos novos que vão substituir PIS, COFINS, IPI, ICMS e ISS:\n" +
        "• IBS (Imposto sobre Bens e Serviços) — de Estados e Municípios\n" +
        "• CBS (Contribuição Social sobre Bens e Serviços) — da União\n" +
        "• IS (Imposto Seletivo) — da União, sobre bens/serviços prejudiciais à saúde ou ao meio ambiente\n\n" +
        "A transição é gradual, de 2026 a 2033, com extinção completa dos tributos antigos em 2033.\n\n" +
        "Princípios: neutralidade (não distorcer decisão de compra), não cumulatividade plena (crédito amplo, sem lista restritiva), tributação no destino (onde o consumo acontece), mesma alíquota pra quase tudo (com exceções dos regimes diferenciados), declaração única, e imposto sempre destacado na nota, visível pro consumidor.",
    },
    {
      id: "rt_calendario",
      palavras: ["calendario", "transicao", "cronograma", "quando comeca", "prazo reforma"],
      resposta:
        "Calendário de transição (LC 214/2025):\n\n" +
        "2026 (ano atual) — CBS a 0,9% (art. 346) e IBS a 0,1% estadual (art. 343). MAS: o recolhimento de IBS e CBS em 2026 é DISPENSADO pra quem cumprir as obrigações acessórias (emitir DF-e com IBS/CBS destacado corretamente) — art. 348, §1º. Ou seja, na prática, empresa em dia com a nota fiscal não paga IBS/CBS em 2026, só declara. Se pagar mesmo assim, o valor é compensado com PIS/COFINS do mesmo período.\n\n" +
        "2027-2028 — CBS na alíquota de referência menos 0,1pp (art. 347; a Riozen usa 8,4% de referência pra 2027 como estimativa de trabalho). IBS a 0,05% estadual + 0,05% municipal = 0,1% total (art. 344) — aqui não tem mais a dispensa de 2026, já é recolhimento normal. PIS/COFINS ainda vigentes, com redução progressiva.\n\n" +
        "2029 — Grande virada: PIS e COFINS são extintos. IBS entra na alíquota de referência calculada (não é mais o valor fixo de teste). ICMS e ISS caem 10%.\n\n" +
        "2030 a 2032 — IBS na alíquota de referência crescente. ICMS e ISS caem mais 20%, 30% e 40% (acumulado) nesses anos.\n\n" +
        "2033 — Sistema novo 100% em vigor: ICMS e ISS extintos, IBS e CBS plenos. O IPI continua só pra produtos sem similar na Zona Franca de Manaus.",
    },
    {
      id: "rt_base_calculo",
      palavras: ["base", "calculo", "aliquota", "fora", "dentro"],
      resposta:
        "Base de cálculo do IBS/CBS: é o valor da operação (preço cobrado), incluindo juros, multas, encargos, frete cobrado pelo fornecedor, seguros e taxas. NÃO entram na base: o próprio IBS, o próprio CBS, o IPI, descontos incondicionais, ITCD, ITBI e — durante a transição — os tributos que ainda vão ser extintos (ICMS, ISS, PIS, COFINS).\n\n" +
        "⚠️ Ponto importante: o imposto é calculado \"por fora\" — ele NÃO integra a própria base de cálculo (art. 12, §2º, I da LC 214/2025). Ou seja, primeiro calcula o valor da operação sem o IBS/CBS, depois aplica a alíquota, e o resultado é somado ao preço.\n\n" +
        "Alíquotas: cada ente federativo (União pra CBS; Estados e Municípios pro IBS) fixa a própria alíquota por lei. Na falta de lei própria, vale a alíquota de referência publicada por Resolução do Senado Federal — que ainda não está totalmente definida pra todos os anos, só 2026 (CBS 0,9% fixo em lei) tem número certo por enquanto.",
    },
    {
      id: "rt_credito",
      palavras: ["credito", "cumulatividade", "vedacao", "direito"],
      resposta:
        "Crédito de IBS/CBS: é bem mais amplo que o crédito atual de PIS/COFINS. O contribuinte pode aproveitar crédito de praticamente qualquer aquisição usada na atividade econômica, desde que tenha sido tributada e paga (art. 47) — inclui mercadorias, insumos, serviços, e até ativo imobilizado de forma integral e imediata (diferente do PIS/COFINS de hoje, que restringe).\n\n" +
        "O que NÃO gera crédito, por ser considerado \"uso ou consumo pessoal\" (art. 57): joias, pedras e metais preciosos; obras de arte e antiguidades; bebidas alcoólicas; derivados de tabaco; armas e munições; bens/serviços recreativos, esportivos e estéticos. Também não gera crédito o que for dado sem cobrar (ou por valor abaixo do mercado) pra sócios, administradores, empregados ou parentes deles — e a lei cita expressamente **veículo e os gastos de manutenção dele (inclusive seguro e combustível)** como exemplo disso (§1º, II) — relevante pra carro de uso de diretoria/funcionário, não pro veículo em estoque pra revenda.\n\n" +
        "A apuração é mensal. Saldo credor pode ser compensado com outros débitos de IBS ou ressarcido em dinheiro — prazo de até 60 dias pra contribuinte adimplente, com prioridade pra exportadores.",
    },
    {
      id: "rt_regimes_diferenciados",
      palavras: ["regime", "diferenciado", "reducao", "educacao", "saude", "medicamento", "cesta", "basica"],
      resposta:
        "Regimes diferenciados: setores com alíquota reduzida em 60% (educação, saúde, dispositivos médicos, medicamentos registrados na Anvisa, produções culturais/artísticas, atividades desportivas, segurança nacional/cibernética) ou com alíquota zero (Cesta Básica Nacional de Alimentos — arroz, feijão, farinha, óleo de soja, leite em pó, carnes, ovos, entre outros).\n\n" +
        "Também tem regimes específicos com regra própria: combustíveis (tributação monofásica, uma vez só na refinaria/distribuição), serviços financeiros (incide sobre a margem/spread, não o valor total), planos de saúde (sobre prêmio menos indenização), bens imóveis (sobre a margem de valorização) e cooperativas (crédito presumido ou alíquota reduzida conforme o tipo).",
    },
    {
      id: "rt_cashback",
      palavras: ["cashback", "devolucao", "personalizada", "cadunico"],
      resposta:
        "Cashback (devolução personalizada): famílias inscritas no CadÚnico com renda per capita de até meio salário mínimo recebem de volta parte do IBS e CBS que pagaram. O consumidor paga o imposto embutido no preço normalmente, o sistema identifica que ele está no CadÚnico, e devolve um percentual — podendo ser na hora da compra ou periodicamente. O percentual exato de devolução é definido por legislação específica de cada ente federativo.",
    },
    {
      id: "rt_imposto_seletivo",
      palavras: ["imposto", "seletivo", "eletrico", "hibrido"],
      resposta:
        "Imposto Seletivo (IS): imposto federal extrafiscal (não é pra arrecadar, é pra desestimular consumo) sobre bens/serviços prejudiciais à saúde ou ao meio ambiente — veículos, cigarros, bebidas alcoólicas, bebidas açucaradas, carvão mineral, e apostas/fantasy sport.\n\n" +
        "Pra concessionária (Riozen): automóveis, motocicletas, embarcações e aeronaves têm IS com alíquota diferenciada por eficiência energética, emissão de CO2 e tipo de combustível. Veículos elétricos e híbridos (linha BYD) tendem a ter IS reduzido ou zero; veículos a combustão convencional pagam mais.\n\n" +
        "Detalhe técnico importante: o IS não gera crédito de IBS/CBS pro comprador na etapa seguinte, e o IPI continua sendo cobrado separadamente até 2033 (o IS não substitui o IPI).",
    },
    {
      id: "rt_veiculo_usado",
      palavras: ["veiculo", "carro", "usado", "usados", "revenda", "margem", "seminovo"],
      resposta:
        "Regime de veículos usados no IBS/CBS (arts. 406 e 407) — muito relevante pra Riozen: o imposto incide só sobre a MARGEM (diferença entre o preço de venda e o valor líquido de aquisição do veículo), não sobre o valor cheio, parecido com o espírito do regime de ICMS/PIS-COFINS de hoje pra usados.\n\n" +
        "Regra principal (art. 406): vale pra veículo que ficou no ativo imobilizado do vendedor por mais de 12 meses e foi comprado com nota fiscal idônea, até 31/12/2032. A alíquota fica ZERO na parte do valor de venda até o valor líquido de aquisição, e só incide normalmente na parte que EXCEDE esse valor.\n\n" +
        "Pra revenda direta de usados (art. 407, mais comum no dia a dia): mesma lógica de tributar só o que exceder o valor líquido de aquisição — mas só vale pra veículo comprado E revendido com documento fiscal idôneo, por contribuinte do regime regular. Atenção: essa regra específica do §2º NÃO vale pra veículo comprado de pessoa física (§3º) — nesse caso a regra é outra.\n\n" +
        "Valor líquido de aquisição: pra veículo comprado até 31/12/2026, é o valor de compra menos o ICMS/PIS/COFINS que geraram crédito na aquisição (se não tiver essa informação, a lei manda usar 1,65% de PIS e 7,6% de COFINS como padrão pra fazer a conta). Pra veículo comprado de 2027 em diante, é a base de cálculo do IBS/CBS da compra, mais o ICMS que não gerou crédito.",
    },
    {
      id: "rt_impacto_concessionaria",
      palavras: ["concessionaria", "impacto", "oficina"],
      resposta:
        "Principais impactos da Reforma pra concessionárias (Riozen — Toyota, Lexus, BYD):\n\n" +
        "1. Imposto Seletivo sobre veículos (ver tópico específico) — elétricos/híbridos tendem a sair melhor\n" +
        "2. Crédito amplo nas aquisições: veículos pra revenda, peças, serviços de oficina, aluguel de espaço, seguros — tudo passa a gerar crédito, sem as restrições que o PIS/COFINS tem hoje\n" +
        "3. Tributação por destino: o IBS vai pro Estado/Município de onde o veículo é emplacado (domicílio do comprador), não de onde fica a loja — pra Riozen (filiais no RJ) isso tende a simplificar, já que a maioria das vendas fica dentro do próprio estado\n" +
        "4. Fim do ICMS-ST em veículos, de forma gradual — os créditos acumulados de ICMS-ST precisam ser levantados e monitorados até 31/12/2032 (depois disso, o saldo que sobrar é ressarcido em 20 parcelas anuais)\n" +
        "5. Oficina e peças passam a ter tributação uniforme (hoje oficina é ISS e peças são ICMS, gerando conflito — com o IBS/CBS vira um imposto só pra operação inteira)\n" +
        "6. Se usar plataforma digital/marketplace pra vender veículos, peças ou serviços, a plataforma pode responder solidariamente pelo IBS/CBS se a nota não for emitida direito",
    },
    {
      id: "rt_ambiente_beta",
      palavras: ["beta", "portal", "piloto", "consumo.tributos", "acessar"],
      resposta:
        "Ambiente de Produção Beta (Receita Federal): plataforma oficial onde qualquer empresa (não precisa de convite) pode acompanhar a simulação da CBS, desde 12/01/2026 até dezembro/2026. Acesso pelo navegador em https://consumo.tributos.gov.br, fazendo login com conta gov.br (como representante legal ou procurador do CNPJ).\n\n" +
        "Diferente do \"Piloto RTC\" (esse sim só por convite, começou em jul/2025, é um ambiente isolado de teste sem ligação com documentos reais) — o Ambiente Beta é conectado de verdade aos sistemas de produção: as notas fiscais reais emitidas pela empresa (NF-e, NFC-e, CT-e, CT-e OS, NFS-e, NFCom, NF3e, BP-e) com CST 000 ou 200 são carregadas automaticamente ali, e a Apuração Assistida roda em cima delas.\n\n" +
        "Não há pagamento real de CBS/IBS nesse período — é só acompanhamento e simulação, confirmando o que já vimos na lei e no glossário.",
    },
    {
      id: "rt_apuracao_assistida",
      palavras: ["apuracao", "assistida", "debito", "periodo", "ajuste"],
      resposta:
        "Apuração Assistida (AA): é a mudança mais radical de modelo trazida pela Reforma — o fisco calcula o tributo devido automaticamente, com base nas notas fiscais emitidas, sem o contribuinte precisar declarar nada manualmente. Se precisar corrigir algo, é só emitir um novo documento fiscal, não uma retificadora.\n\n" +
        "Período de apuração: definido pela data de emissão dos documentos fiscais (ex: apuração de Jan/2026 = notas emitidas em janeiro). Passa por 3 fases: \"Em Andamento\" (do dia 1 ao último dia do mês), \"Período de Ajuste\" (do dia 1 ao dia 25 do mês seguinte — ainda dá pra corrigir), \"Concluída\" (a partir do dia 26 do mês seguinte).\n\n" +
        "Contas principais que aparecem na apuração: Débitos (CBS destacada nas notas de saída), Créditos de CBS apropriados (das notas de entrada), Pagamentos Utilizados (Split Payment/RAD/pagamento direto), e o Resultado do Período (débitos menos créditos). Depois de concluída, vira \"Saldo Atualizado\", que muda se aparecer novo débito, redutor, pagamento ou compensação depois.\n\n" +
        "Detalhe curioso: mesmo empresa do Simples Nacional (que normalmente não tem direito a crédito de CBS) vê a simulação \"como se\" estivesse no regime regular — é só informativo, não muda o enquadramento dela.",
    },
    {
      id: "rt_devolucoes",
      palavras: ["ressarcimento", "restituicao", "transferencia", "split", "rad", "pcont"],
      resposta:
        "Formas de devolução de valores no novo sistema:\n\n" +
        "• Ressarcimento — quando sobra crédito no fim do período (créditos > débitos). Só acontece se o contribuinte pedir, no próprio ambiente da Apuração Assistida, total ou parcial. Gera um PER/DCOMP automático.\n\n" +
        "• Restituição — quando teve pagamento indevido ou a maior (ex: pagou em duplicidade, ou pagou R$120 devendo R$100). Também só a pedido do contribuinte.\n\n" +
        "• Transferência — é diferente das duas de cima: é automática, não precisa pedir, e acontece em até 3 dias úteis. Ocorre quando há excesso de recolhimento via Split Payment, RAD ou pagamento direto do contribuinte (PCONT).\n\n" +
        "Termos usados: Split Payment é a separação automática do valor do tributo no momento do pagamento eletrônico, feita pela própria operadora de pagamento. RAD é o recolhimento feito pelo adquirente (quem compra). PCONT é o pagamento feito diretamente pelo próprio contribuinte.",
    },
    {
      id: "rt_calculadora_oficial",
      palavras: ["calculadora", "motor", "aberto", "erp"],
      resposta:
        "Calculadora de Tributos: é o motor de cálculo oficial da Receita Federal, de código aberto, que já embute todas as regras da CBS e do IS conforme a LC 214/2025. É a mesma versão usada tanto pela Receita quanto pelos contribuintes — dá pra rodar offline (baixando o componente, precisa de Java 21) ou via API.\n\n" +
        "Vale a pena avaliar integrar essa Calculadora direto no ERP da Riozen (NBS), já que ela garante que os documentos fiscais já saiam calculados certinho, sem risco de divergência com o que a Receita vai calcular na Apuração Assistida.\n\n" +
        "Mais informações e download em: https://piloto-cbs.tributos.gov.br/servico/calculadora-consumo/calculadora",
    },
    {
      id: "rt_comite_gestor",
      palavras: ["comite", "gestor", "cgibs"],
      resposta:
        "Comitê Gestor do IBS (CGIBS): entidade pública técnica e operacional, independente, sediada no DF, criada em 31/12/2025. Cuida de regulamentar e administrar o IBS de forma centralizada pra todos os Estados e Municípios, edita o Regulamento Único do IBS, gerencia a arrecadação e distribuição entre os entes, e cuida da fiscalização e do contencioso administrativo do IBS. Trabalha junto com a Receita Federal (que cuida da CBS) e a PGFN.",
    },
    {
      id: "rt_zona_franca",
      palavras: ["zona", "franca", "manaus", "zfm"],
      resposta:
        "Zona Franca de Manaus (ZFM): os benefícios são mantidos até 2073. A LC 214/2025 preserva vantagens equivalentes às que já existiam com IPI/PIS/COFINS: suspensão de IBS/CBS nas remessas pra ZFM (virando alíquota zero no destino), crédito presumido pra quem compra insumos de fornecedores da ZFM, e o IPI continua sendo cobrado sobre produtos da ZFM pra sempre (é proteção constitucional).",
    },
  ],

  // ────────────────────────────────────────────────────────────────────
  // MÓDULOS DO SISTEMA — onde achar cada coisa no painel web
  // ────────────────────────────────────────────────────────────────────
  modulos_sistema: [
    {
      id: "nav_icms",
      palavras: ["icms"],
      resposta: "A apuração de ICMS fica em Fiscal › Apuração › ICMS. Já está funcionando no sistema web — sobe os PDFs do Livro Fiscal, Livro de Entrada e Livro de Saída, e ele compara nota a nota com o que o NBS gerou.",
    },
    {
      id: "nav_pis_cofins",
      palavras: ["pis", "cofins", "apuracao pis", "apuracao cofins"],
      resposta: "A apuração de PIS/COFINS fica em Fiscal › Apuração › PIS/COFINS. Já está funcionando no sistema web: sobe a Planilha de Débitos, a planilha de Créditos (NBS, uma por filial), o Balancete e o Arquivo 170, e ele gera os 3 arquivos (Débitos, Créditos e Apuração) em sequência.",
    },
    {
      id: "nav_cbs_ibs",
      palavras: ["cbs", "ibs", "reforma tributaria apuracao", "apuracao cbs ibs"],
      resposta: "A apuração de CBS/IBS fica em Fiscal › Apuração › CBS/IBS. Você escolhe o período e as alíquotas de débito e crédito (já vêm pré-preenchidas pelo ano, mas dá pra editar), sobe as planilhas de Saída e Entrada, e ele calcula débito menos crédito automaticamente, gerando o relatório em Excel.",
    },
    {
      id: "nav_reforma_tributaria",
      palavras: ["reforma", "tributaria", "simulador"],
      resposta: "A ferramenta de Reforma Tributária (com plano de ação, linha do tempo e calculadoras por setor) fica em Geral › Reforma Tributária, abre numa aba nova. Tem também o Simulador IBS/CBS separado, em Geral › Simulador IBS/CBS, pra rodar cenários gerenciais.",
    },
    {
      id: "nav_cadastro_regime",
      palavras: ["cadastro", "cliente", "fornecedor", "regime"],
      resposta: "O cadastro de Clientes e Fornecedores (com o regime tributário de cada CNPJ) fica em Geral › Clientes ou Geral › Fornecedores — as duas entradas de menu abrem a mesma tela, porque é o mesmo cadastro compartilhado.",
    },
    {
      id: "nav_ncm",
      palavras: ["ncm", "classificacao fiscal", "codigo ncm"],
      resposta: "A consulta de NCM fica em Geral › NCM e cClassTrib › NCM, na barra lateral. Esse módulo ainda está em desenvolvimento no sistema web.",
    },
    {
      id: "nav_cclasstrib",
      palavras: ["cclasstrib", "cst", "classificacao tributaria"],
      resposta: "cClassTrib/CST fica em Geral › NCM e cClassTrib › cClassTrib/CST, na barra lateral. Esse módulo ainda está em desenvolvimento no sistema web.",
    },
    {
      id: "nav_nfse",
      palavras: ["nfse", "nfs-e"],
      resposta: "NFS-e Entrada e NFS-e Saída ficam em Fiscal › Análise Fiscal, na barra lateral. Esses módulos ainda estão em desenvolvimento no sistema web.",
    },
    {
      id: "nav_folha",
      palavras: ["folha", "pagamento", "folha de pagamento"],
      resposta: "Folha de Pagamento fica em Contábil › Folha, na barra lateral. Esse módulo ainda está em desenvolvimento no sistema web.",
    },
    {
      id: "voltar_painel",
      palavras: ["voltar", "painel", "inicio", "home"],
      resposta: "Pra voltar ao painel principal, usa o botão Início que aparece no topo de qualquer tela.",
    },
  ],

  // ────────────────────────────────────────────────────────────────────
  // SOBRE A RIOZEN / O ASSISTENTE
  // ────────────────────────────────────────────────────────────────────
  sobre_riozen: [
    {
      id: "sobre_riozen_empresa",
      palavras: ["riozen", "endereco", "onde fica", "empresa", "matriz"],
      resposta: "A Riozen é um grupo com concessionárias Toyota e BYD, na Av. das Américas, 5655, Barra da Tijuca, Rio de Janeiro.",
    },
    {
      id: "quem_e_voce",
      palavras: ["quem e voce", "quem e vc", "seu nome", "o que voce faz", "quem voce e"],
      resposta: "Sou o assistente do Sistema Riozen! Posso te ajudar com o passo a passo da rotina no NBS, achar módulos no painel, ou responder dúvidas gerais — é só escolher o assunto no menu.",
    },
  ],
};

/* Confiança mínima (número de palavras batendo) pra usar a resposta local
   em vez de cair pra IA. 1 = qualquer palavra única já basta. */
const CONFIANCA_MINIMA_KB = 1;

/**
 * Busca dentro de UMA categoria específica (a que o usuário escolheu no
 * menu). Retorna a resposta em texto, ou null se nada bateu o suficiente.
 */
function buscarRespostaLocal(pergunta, categoriaId) {
  const lista = BASE_CONHECIMENTO_ASSISTENTE[categoriaId];
  if (!lista) return null;

  const normalizada = pergunta
    .toLowerCase()
    .normalize("NFD").replace(/[\u0300-\u036f]/g, ""); // remove acentos

  let melhor = null;
  let melhorPontuacao = 0;

  lista.forEach((item) => {
    let pontuacao = 0;
    item.palavras.forEach((palavra) => {
      const p = palavra.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
      if (normalizada.includes(p)) pontuacao++;
    });
    if (pontuacao > melhorPontuacao) {
      melhorPontuacao = pontuacao;
      melhor = item;
    }
  });

  if (melhor && melhorPontuacao >= CONFIANCA_MINIMA_KB) {
    return melhor.resposta;
  }
  return null;
}
