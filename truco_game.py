import random
import copy


# -------------------------------
# CONSTANTES DO BARALHO
# -------------------------------

NAIPES = ['P', 'C', 'E', 'O']

SIMBOLO_NAIPE = {
    'P': '♣',
    'C': '♥',
    'E': '♠',
    'O': '♦'
}

VALORES = ['4', '5', '6', '7', 'Q', 'J', 'K', 'A', '2', '3']

ORDEM_NAIPES_MANILHA = ['O', 'E', 'C', 'P']


# -------------------------------
# CONSTANTES DO TRUCO
# -------------------------------

NIVEIS_TRUCO  = [None, 'truco', 'seis', 'nove', 'doze']

PONTOS_NIVEL = {
    None:    1,
    'truco': 3,
    'seis':  6,
    'nove':  9,
    'doze':  12
}

PONTOS_AO_CORRER = {
    'truco': 1,
    'seis':  3,
    'nove':  6,
    'doze':  9
}


# -------------------------------
# FUNÇÕES DO BARALHO
# -------------------------------

def criar_baralho():
    baralho = []

    for naipe in NAIPES:
        for valor in VALORES:
            carta = {'r': valor, 's': naipe}
            baralho.append(carta)

    random.shuffle(baralho)
    return baralho


def nome_da_carta(carta):
    simbolo = SIMBOLO_NAIPE[carta['s']]
    return carta['r'] + simbolo


# -------------------------------
# FUNÇÕES DA MANILHA
# -------------------------------

def calcular_valor_da_manilha(vira):
    indice_vira = VALORES.index(vira['r'])
    indice_manilha = (indice_vira + 1) % 10
    return VALORES[indice_manilha]


def forca_da_carta(carta, vira):
    valor_manilha = calcular_valor_da_manilha(vira)

    if carta['r'] == valor_manilha:
        posicao_naipe = ORDEM_NAIPES_MANILHA.index(carta['s'])
        return 11 + posicao_naipe

    return VALORES.index(carta['r']) + 1


def descricao_manilhas(vira):
    valor_manilha = calcular_valor_da_manilha(vira)

    partes = []
    for naipe in reversed(ORDEM_NAIPES_MANILHA):
        partes.append(valor_manilha + SIMBOLO_NAIPE[naipe])

    return ' > '.join(partes)


# -------------------------------
# FUNÇÕES DE TURNO / OPONENTE
# -------------------------------

def oponente(jogador):
    if jogador == 'p1':
        return 'p2'
    return 'p1'


def proximo_nivel_truco(mao):
    nivel_atual = mao['truco_pendente'] or mao['nivel_truco']
    indice_atual = NIVEIS_TRUCO.index(nivel_atual)

    proximo_indice = indice_atual + 1

    if proximo_indice < len(NIVEIS_TRUCO):
        return NIVEIS_TRUCO[proximo_indice]

    return None


# -------------------------------
# CRIAÇÃO E INICIO DE PARTIDA
# -------------------------------

def novo_jogo():
    return {
        'pontos':  {'p1': 0, 'p2': 0},
        'fase':    'aguardando',
        'mao':     None,
        'dealer':  'p1',
        'vencedor': None,
        'mensagem': 'Aguardando jogadores...'
    }


def iniciar_mao(jogo):
    jogo = copy.deepcopy(jogo)

    baralho = criar_baralho()

    proximo_dealer = oponente(jogo['dealer'])
    jogo['dealer'] = proximo_dealer

    primeiro_a_jogar = oponente(proximo_dealer)

    mao = {
        'cartas':         {'p1': baralho[0:3], 'p2': baralho[3:6]},
        'vira':           baralho[6],
        'mesa':           {'p1': None, 'p2': None},
        'rodadas':        [],
        'vez':            primeiro_a_jogar,
        'precisa':        primeiro_a_jogar,
        'aposta':         1,
        'nivel_truco':    None,
        'truco_pendente': None,
        'quem_pediu':     None,
        'vencedor':       None,
        'mao_de_onze':    None
    }

    jogo['mao'] = mao
    jogo['fase'] = 'jogando'
    jogo['mensagem'] = f'Nova mão! {primeiro_a_jogar} começa.'

    # Verificar se alguém está com 11 pontos (Mão de Onze)
    pontos = jogo['pontos']
    p1_tem_onze = pontos['p1'] == 11
    p2_tem_onze = pontos['p2'] == 11

    if p1_tem_onze or p2_tem_onze:
        jogo['fase'] = 'mao_de_onze'

        decisao_p1 = None if p1_tem_onze else 'jogar'
        decisao_p2 = None if p2_tem_onze else 'jogar'
        mao['mao_de_onze'] = {'p1': decisao_p1, 'p2': decisao_p2}

        mao['aposta'] = 3

        if p1_tem_onze:
            mao['precisa'] = 'p1'
        else:
            mao['precisa'] = 'p2'

        jogo['mensagem'] = 'Mão de onze! Decida se joga ou foge.'

    return jogo


# -------------------------------
# AÇÕES DO JOGO
# -------------------------------

def jogar_carta(jogo, jogador, indice):
    jogo = copy.deepcopy(jogo)
    mao = jogo['mao']

    if jogo['fase'] != 'jogando':
        return jogo, 'Não é hora de jogar carta.'

    if mao['precisa'] != jogador:
        return jogo, 'Não é a sua vez.'

    cartas_do_jogador = mao['cartas'][jogador]

    if indice < 0 or indice >= len(cartas_do_jogador):
        return jogo, 'Índice de carta inválido.'

    carta_jogada = cartas_do_jogador.pop(indice)
    mao['mesa'][jogador] = carta_jogada

    adversario = oponente(jogador)

    # Adversário ainda não jogou nessa rodada
    if mao['mesa'][adversario] is None:
        mao['precisa'] = adversario
        mensagem = f'{jogador} jogou {nome_da_carta(carta_jogada)}. Vez de {adversario}.'
        jogo['mensagem'] = mensagem
        return jogo, mensagem

    # Ambos jogaram, resolver a rodada
    return resolver_rodada(jogo)


def pedir_truco(jogo, jogador, nivel):
    jogo = copy.deepcopy(jogo)
    mao = jogo['mao']

    # Só pode pedir truco quem está na sua vez
    if jogo['fase'] == 'jogando' and mao['precisa'] != jogador:
        return jogo, 'Não é a sua vez.'

    if jogo['fase'] == 'truco':
        if mao['quem_pediu'] == jogador or mao['precisa'] != jogador:
            return jogo, 'Não pode pedir truco agora.'

    if jogo['fase'] not in ('jogando', 'truco'):
        return jogo, 'Não pode pedir truco nesta fase.'

    # Verificar se o nível pedido é o próximo válido
    nivel_base = mao['truco_pendente'] or mao['nivel_truco']
    indice_base = NIVEIS_TRUCO.index(nivel_base)
    indice_pedido = NIVEIS_TRUCO.index(nivel)

    if indice_pedido != indice_base + 1:
        proximo = NIVEIS_TRUCO[indice_base + 1] if indice_base + 1 < len(NIVEIS_TRUCO) else None
        if proximo:
            return jogo, f'O próximo nível disponível é: {proximo}.'
        return jogo, 'Já está no nível máximo.'

    mao['truco_pendente'] = nivel
    mao['quem_pediu'] = jogador
    mao['precisa'] = oponente(jogador)

    jogo['fase'] = 'truco'
    mensagem = f'{jogador} pediu {nivel.upper()}! Vale {PONTOS_NIVEL[nivel]} pontos.'
    jogo['mensagem'] = mensagem
    return jogo, mensagem


def responder_truco(jogo, jogador, aceitar):
    jogo = copy.deepcopy(jogo)
    mao = jogo['mao']

    if jogo['fase'] != 'truco':
        return jogo, 'Não é hora de responder ao truco.'

    if mao['precisa'] != jogador:
        return jogo, 'Não é a sua vez de responder.'

    quem_pediu = mao['quem_pediu']
    nivel_pendente = mao['truco_pendente']

    if aceitar:
        mao['nivel_truco']    = nivel_pendente
        mao['aposta']         = PONTOS_NIVEL[nivel_pendente]
        mao['truco_pendente'] = None
        mao['quem_pediu']     = None

        # Determinar quem joga após o aceite:
        # Se há carta na mesa de algum jogador, o outro ainda precisa jogar.
        # Caso contrário, quem PEDIU o truco joga primeiro (chamou truco no
        # lugar de jogar sua carta, então a vez continua sendo dele).
        carta_p1_na_mesa = mao['mesa']['p1'] is not None
        carta_p2_na_mesa = mao['mesa']['p2'] is not None

        if carta_p1_na_mesa and not carta_p2_na_mesa:
            proximo = 'p2'
        elif carta_p2_na_mesa and not carta_p1_na_mesa:
            proximo = 'p1'
        else:
            proximo = quem_pediu   # mesa limpa: quem pediu truco joga primeiro

        mao['precisa'] = proximo
        mao['vez']     = proximo

        jogo['fase'] = 'jogando'
        mensagem = f'{jogador} aceitou! A mão agora vale {mao["aposta"]} pontos.'

    else:
        pontos_ganhos = PONTOS_AO_CORRER[nivel_pendente]
        jogo['pontos'][quem_pediu] += pontos_ganhos
        mao['vencedor'] = quem_pediu

        jogo['fase'] = 'fim_de_mao'
        jogo = verificar_vitoria(jogo)
        mensagem = f'{jogador} correu! {quem_pediu} ganha {pontos_ganhos} pontos.'

    jogo['mensagem'] = mensagem
    return jogo, mensagem


def decidir_mao_de_onze(jogo, jogador, vai_jogar):
    jogo = copy.deepcopy(jogo)
    mao = jogo['mao']

    if jogo['fase'] != 'mao_de_onze':
        return jogo, 'Não é hora de decidir mão de onze.'

    if mao['precisa'] != jogador:
        return jogo, 'Não é a sua vez de decidir.'

    decisoes = mao['mao_de_onze']
    decisoes[jogador] = 'jogar' if vai_jogar else 'fugir'

    adversario = oponente(jogador)

    # Adversário ainda não decidiu
    if decisoes[adversario] is None:
        mao['precisa'] = adversario
        mensagem = f'{jogador} decidiu. Aguardando {adversario}...'
        jogo['mensagem'] = mensagem
        return jogo, mensagem

    # Ambos decidiram, avaliar resultado
    decisao_p1 = decisoes['p1']
    decisao_p2 = decisoes['p2']

    if decisao_p1 == 'fugir' and decisao_p2 == 'fugir':
        jogo['fase'] = 'fim_de_mao'
        mensagem = 'Ambos fugiram. Nenhum ponto distribuído.'

    elif decisao_p1 == 'fugir':
        jogo['pontos']['p2'] += 1
        mao['vencedor'] = 'p2'
        jogo['fase'] = 'fim_de_mao'
        jogo = verificar_vitoria(jogo)
        mensagem = 'p1 fugiu. p2 ganha 1 ponto.'

    elif decisao_p2 == 'fugir':
        jogo['pontos']['p1'] += 1
        mao['vencedor'] = 'p1'
        jogo['fase'] = 'fim_de_mao'
        jogo = verificar_vitoria(jogo)
        mensagem = 'p2 fugiu. p1 ganha 1 ponto.'

    else:
        jogo['fase'] = 'jogando'
        mao['precisa'] = mao['vez']
        mensagem = 'Ambos decidiram jogar! A mão vale 3 pontos.'

    jogo['mensagem'] = mensagem
    return jogo, mensagem


# -------------------------------
# RESOLUÇÃO DE RODADA
# -------------------------------

def resolver_rodada(jogo):
    mao = jogo['mao']

    carta_p1 = mao['mesa']['p1']
    carta_p2 = mao['mesa']['p2']

    forca_p1 = forca_da_carta(carta_p1, mao['vira'])
    forca_p2 = forca_da_carta(carta_p2, mao['vira'])

    if forca_p1 > forca_p2:
        vencedor_rodada = 'p1'
    elif forca_p2 > forca_p1:
        vencedor_rodada = 'p2'
    else:
        vencedor_rodada = 'empate'

    mao['rodadas'].append({
        'p1':      carta_p1,
        'p2':      carta_p2,
        'vencedor': vencedor_rodada
    })

    # Limpar mesa
    mao['mesa'] = {'p1': None, 'p2': None}

    resultado_texto = (
        f'Rodada {len(mao["rodadas"])}: '
        f'{nome_da_carta(carta_p1)} vs {nome_da_carta(carta_p2)} '
        f'→ {vencedor_rodada}'
    )

    # Verificar se a mão já tem um vencedor
    vencedor_mao = calcular_vencedor_da_mao(mao)

    if vencedor_mao is not None:
        mao['vencedor'] = vencedor_mao

        if vencedor_mao != 'empate':
            jogo['pontos'][vencedor_mao] += mao['aposta']

        jogo['fase'] = 'fim_de_mao'
        jogo = verificar_vitoria(jogo)

        if vencedor_mao == 'empate':
            complemento = f'; Empate na mão!'
        else:
            complemento = f'; {vencedor_mao} venceu a mão! +{mao["aposta"]} pontos.'

    else:
        # Mão continua: próximo a jogar é quem ganhou a rodada (ou quem jogou primeiro em empate)
        if vencedor_rodada != 'empate':
            proximo = vencedor_rodada
        else:
            proximo = mao['vez']

        mao['vez'] = proximo
        mao['precisa'] = proximo
        complemento = f'; Vez de {proximo}.'

    mensagem = resultado_texto + complemento
    jogo['mensagem'] = mensagem
    return jogo, mensagem


def calcular_vencedor_da_mao(mao):
    contagem = {'p1': 0, 'p2': 0, 'empate': 0}

    for rodada in mao['rodadas']:
        contagem[rodada['vencedor']] += 1

    # Alguém ganhou 2 rodadas
    if contagem['p1'] >= 2:
        return 'p1'

    if contagem['p2'] >= 2:
        return 'p2'

    numero_rodadas = len(mao['rodadas'])

    # Após 2 rodadas: quem ganhou 1 e empatou 1 vence
    if numero_rodadas >= 2:
        if contagem['p1'] == 1 and contagem['empate'] >= 1:
            return 'p1'
        if contagem['p2'] == 1 and contagem['empate'] >= 1:
            return 'p2'

    # Após 3 rodadas: desempate
    if numero_rodadas == 3:
        if contagem['p1'] > contagem['p2']:
            return 'p1'
        if contagem['p2'] > contagem['p1']:
            return 'p2'

        # Tudo empatado: quem ganhou a primeira rodada vence
        for rodada in mao['rodadas']:
            if rodada['vencedor'] != 'empate':
                return rodada['vencedor']

        return 'empate'

    return None


def verificar_vitoria(jogo):
    for jogador in ('p1', 'p2'):
        if jogo['pontos'][jogador] >= 12:
            jogo['fase'] = 'fim_de_jogo'
            jogo['vencedor'] = jogador

    return jogo