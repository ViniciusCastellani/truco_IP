import socket
import json
import time
import os
import threading
import copy
import truco_game as tg


# -------------------------------
# IDENTIFICAÇÃO DOS JOGADORES
# -------------------------------

EU  = 'p1'
ADV = 'p2'


# -------------------------------
# CONFIGURAÇÃO DE REDE
# -------------------------------

PORTA       = 5000
BUFFER_SIZE = 65535


# -------------------------------
# TABELA DE CRIPTOGRAFIA
# -------------------------------

CHAVE_CRIPTO = {
    "A": 29, "B": 49, "C": 58, "D": 72, "E": 13,
    "F": 28, "G": 48, "H": 57, "I": 71, "J": 12,
    "K": 27, "L": 47, "M": 56, "N": 70, "O": 11,
    "P": 26, "Q": 46, "R": 55, "S": 69, "T": 10,
    "U": 25, "V": 45, "W": 24, "X": 54, "Y": 68, "Z": 9,

    "a": 19, "b": 34, "c": 40, "d": 63, "e":  4,
    "f": 18, "g": 33, "h": 39, "i": 62, "j":  3,
    "k": 17, "l": 32, "m": 38, "n": 61, "o":  2,
    "p": 16, "q": 31, "r": 37, "s": 60, "t":  1,
    "u": 15, "v": 30, "w": 14, "x": 36, "y": 59,
    "z":  0,

    "0": 51, "1": 65, "2":  6, "3": 21, "4": 41,
    "5": 50, "6": 64, "7":  5, "8": 20, "9": 35,

    ".": 44, ",": 53, "!": 67, "?":  8,
    "$": 23, "#": 43, "%": 52, "*": 66,
    "+":  7, "-": 22, "/": 42,
    " ": 73, ";": 74,

    "{": 75, "}": 76, "[": 77, "]": 78,
    ":": 79, '"': 80, "_": 81,

    "♣": 82, "♥": 83, "♠": 84, "♦": 85,

    "\\": 86
}

CHAVE_DECRIPTO = {valor: char for char, valor in CHAVE_CRIPTO.items()}

TAMANHO_BLOCO = 5


# -------------------------------
# CHAVES PRÉ-CONFIGURADAS (OPCIONAL)
# -------------------------------
# Preencha os valores abaixo para pular a geração interativa.
# Deixe None para gerar as chaves ao iniciar o programa.
#
# Exemplo:
#   CHAVE_PUBLICA_P1  = [17, 143]   # [E, N]
#   CHAVE_PRIVADA_P1  = [113, 143]  # [D, N]

CHAVE_PUBLICA_P1  = [31, 551]   # [E, N]
CHAVE_PRIVADA_P1  = [439, 551]  # [D, N]


# -------------------------------
# VARIÁVEIS DE ESTADO (RUNTIME)
# -------------------------------

minha_chave_publica  = None
minha_chave_privada  = None
chave_publica_do_adv = None   # recebida no handshake

endereco_p2 = None

_lock_estado = threading.Lock()
_estado      = tg.novo_jogo()
_evento      = threading.Event()


# -------------------------------
# FUNÇÕES AUXILIARES - PRIMOS
# -------------------------------

def eh_primo(numero):
    """Retorna True se o número for primo, False caso contrário.

    Testa divisibilidade de 2 até a raiz quadrada do número.
    """
    if numero < 2:
        return False

    for i in range(2, int(numero ** 0.5) + 1):
        if numero % i == 0:
            return False

    return True


def gerar_lista_primos(limite):
    """Retorna uma lista com todos os números primos menores que limite."""
    lista = []

    for numero in range(2, limite):
        if eh_primo(numero):
            lista.append(numero)

    return lista


# -------------------------------
# GERAÇÃO DAS CHAVES RSA
# -------------------------------

def escolher_p_e_q(lista_primos):
    """Solicita ao usuário a escolha dos primos P e Q para o RSA.

    Valida que ambos pertencem à lista de primos fornecida, são distintos
    entre si e que P * Q é maior que o maior índice da tabela de
    substituição, garantindo que todos os caracteres possam ser cifrados.

    Retorna a tupla (p, q).
    """
    VALOR_MAXIMO_TABELA = max(CHAVE_CRIPTO.values())

    print(f"\nPrimos disponíveis:\n{lista_primos}\n")

    while True:
        try:
            p = int(input("Primeiro primo (P): "))
            q = int(input("Segundo primo  (Q): "))

            if p not in lista_primos or q not in lista_primos:
                print("\nOs valores precisam estar na lista de primos\n")
                continue

            if p == q:
                print("\nP e Q precisam ser diferentes\n")
                continue

            if p * q <= VALOR_MAXIMO_TABELA:
                print(f"\nP * Q = {p * q} é muito pequeno, precisa ser maior que {VALOR_MAXIMO_TABELA}\n")
                continue

            return p, q

        except ValueError:
            print("\nDigite apenas números inteiros\n")


def calcular_n_e_totiente(p, q):
    """Calcula e exibe o módulo N e o totiente de Euler a partir de P e Q.

    N = P * Q é o módulo público do RSA.
    totiente = (P-1) * (Q-1) é usado para derivar os expoentes E e D.

    Retorna a tupla (n, totiente).
    """
    n        = p * q
    totiente = (p - 1) * (q - 1)

    print(f"\nN (módulo)  = {n}")
    print(f"Totiente    = {totiente}")

    return n, totiente


def escolher_e(q, totiente):
    """Solicita ao usuário a escolha do expoente público E.

    Apresenta os candidatos válidos: primos maiores que Q e coprimos com
    o totiente (mdc(E, totiente) = 1). Valida a escolha do usuário.

    Retorna o valor de E escolhido.
    """
    candidatos = [x for x in gerar_lista_primos(totiente) if x > q]

    print(f"\nCandidatos para E (primo > Q={q}):")
    print(f"{candidatos[:30]}{'...' if len(candidatos) > 30 else ''}\n")

    while True:
        try:
            e = int(input("E: "))

            if e in candidatos:
                return e

            print("\nE deve estar na lista acima\n")

        except ValueError:
            print("\nDigite apenas números inteiros\n")


def calcular_d(e, totiente):
    """Calcula o expoente privado D por busca incremental.

    Encontra D tal que (E * D) mod totiente == 1, satisfazendo a
    condição de inverso modular necessária para o RSA.

    Retorna o valor de D.
    """
    d = 1

    while True:
        d += 1
        if (e * d) % totiente == 1:
            return d


def gerar_chaves_rsa():
    """Conduz o fluxo interativo completo de geração de chaves RSA.

    Guia o usuário pela escolha de P, Q e E, calcula N, totiente e D, e
    exibe as chaves resultantes no terminal.

    Retorna a tupla (chave_publica, chave_privada), onde cada chave é
    uma lista [expoente, modulo].
    """
    LIMITE_PRIMOS = 1000

    lista_primos = gerar_lista_primos(LIMITE_PRIMOS)

    p, q         = escolher_p_e_q(lista_primos)
    n, totiente  = calcular_n_e_totiente(p, q)
    e            = escolher_e(q, totiente)
    d            = calcular_d(e, totiente)

    chave_publica = [e, n]
    chave_privada = [d, n]

    print(f"\nChave pública  [E, N] = {chave_publica}")
    print(f"Chave privada  [D, N] = {chave_privada}")

    return chave_publica, chave_privada


# -------------------------------
# CRIPTOGRAFIA E DESCRIPTOGRAFIA
# -------------------------------

def criptografar(texto, chave_publica):
    """Cifra um texto usando RSA com a chave pública fornecida.

    Para cada caractere do texto, consulta seu índice em CHAVE_CRIPTO,
    aplica c = m^E mod N e formata o resultado como um bloco de 5 dígitos.
    Também exibe no terminal os valores intermediários de cada cifragem.

    Retorna a string cifrada como concatenação de blocos de 5 dígitos.
    """
    e, n   = chave_publica
    cifrado = ""

    for char in texto:
        valor_tabela = CHAVE_CRIPTO[char]
        valor_cifrado = pow(valor_tabela, e, n)
        print(f"  [CRIPTO] '{char}' -> m={valor_tabela} -> c={valor_cifrado} -> bloco={valor_cifrado:05d}")
        cifrado += f"{valor_cifrado:05d}"

    return cifrado


def descriptografar(texto_cifrado, chave_privada):
    """Decifra um texto cifrado usando RSA com a chave privada fornecida.

    Segmenta o texto em blocos de TAMANHO_BLOCO dígitos, aplica
    m = c^D mod N sobre cada bloco e consulta CHAVE_DECRIPTO para
    recuperar o caractere original.

    Retorna o texto original decifrado.
    """
    d, n    = chave_privada
    decifrado = ""

    for i in range(0, len(texto_cifrado), TAMANHO_BLOCO):
        bloco     = texto_cifrado[i:i + TAMANHO_BLOCO]
        valor_cod = int(bloco)
        valor_dec = pow(valor_cod, d, n)
        decifrado += CHAVE_DECRIPTO[valor_dec]

    return decifrado


def empacotar(dados):
    """Serializa um dicionário para JSON, cifra com a chave pública do adversário e codifica em bytes.

    Retorna os bytes prontos para envio via socket UDP.
    """
    texto_json  = json.dumps(dados, ensure_ascii=True)
    texto_cifrado = criptografar(texto_json, chave_publica_do_adv)
    return texto_cifrado.encode()


def desempacotar(dados_brutos):
    """Decodifica bytes recebidos, decifra com a chave privada local e desserializa o JSON.

    Retorna o dicionário Python original da mensagem.
    """
    texto_cifrado = dados_brutos.decode()
    texto_json    = descriptografar(texto_cifrado, minha_chave_privada)
    return json.loads(texto_json)


# -------------------------------
# FUNÇÕES DE ESTADO DO JOGO
# -------------------------------

def obter_estado():
    """Retorna uma cópia profunda do estado atual do jogo de forma thread-safe."""
    with _lock_estado:
        return copy.deepcopy(_estado)


def salvar_estado(novo_estado):
    """Substitui o estado global pelo novo estado de forma thread-safe e sinaliza o evento."""
    global _estado
    with _lock_estado:
        _estado = novo_estado
    _evento.set()


def enviar_estado_para_p2(sock, estado, tipo='ESTADO'):
    """Envia o estado atual do jogo para o Jogador 2 via UDP, se o endereço já for conhecido."""
    if endereco_p2 is not None:
        enviar(sock, endereco_p2, {'t': tipo, 'st': estado})


# -------------------------------
# FUNÇÕES DE REDE
# -------------------------------

def enviar(sock, endereco, dados):
    """Empacota e envia um dicionário de dados para o endereço UDP informado.

    Em caso de erro no envio, exibe a mensagem de erro no terminal.
    """
    try:
        sock.sendto(empacotar(dados), endereco)
    except Exception as erro:
        print(f"[ERRO AO ENVIAR] {erro}")


def definir_chave_publica_do_adv(chave):
    """Armazena a chave pública recebida do adversário na variável global."""
    global chave_publica_do_adv
    chave_publica_do_adv = chave


# -------------------------------
# HANDSHAKE RSA
# -------------------------------

def realizar_handshake(sock):
    """Executa o handshake de seis etapas para estabelecer a comunicação cifrada.

    Etapa 1 (pré-condição): aguarda mensagem INICIO de p2, registrando seu endereço.
    Etapa 2: envia a chave pública de p1 em texto plano.
    Etapa 3: aguarda e registra a chave pública de p2 em texto plano.
    Etapa 4: envia confirmação INICIO cifrada com RSA, marcando início da comunicação segura.
    Etapa 5: aguarda mensagem SYNC de p2, confirmando que sua thread de recepção está ativa.
    Etapa 6 (implícita): p1 inicia a primeira mão ao retornar desta função.
    """
    global endereco_p2

    print(f"\n[REDE] Aguardando p2 na porta {PORTA}...")

    # Fase 1: aguardar INICIO de p2 (mensagem sem cifra)
    while endereco_p2 is None:
        sock.settimeout(1.0)
        try:
            dados_brutos, endereco = sock.recvfrom(BUFFER_SIZE)
        except socket.timeout:
            continue

        try:
            mensagem = json.loads(dados_brutos.decode())
        except:
            continue

        if mensagem.get('t') == 'INICIO':
            endereco_p2 = endereco
            print(f"[REDE] p2 conectado: {endereco}")

            # Fase 2: enviar chave pública de p1 (sem cifra ainda)
            resposta = json.dumps({'t': 'CHAVE', 'pub': minha_chave_publica})
            sock.sendto(resposta.encode(), endereco)
            print(f"[REDE] Chave pública de p1 enviada: {minha_chave_publica}")

    # Fase 3: aguardar chave pública de p2 (ainda sem cifra)
    print("[REDE] Aguardando chave pública de p2...")

    while chave_publica_do_adv is None:
        sock.settimeout(1.0)
        try:
            dados_brutos, endereco = sock.recvfrom(BUFFER_SIZE)
        except socket.timeout:
            continue

        if endereco != endereco_p2:
            continue

        try:
            mensagem = json.loads(dados_brutos.decode())
        except:
            continue

        if mensagem.get('t') == 'CHAVE' and 'pub' in mensagem:
            definir_chave_publica_do_adv(mensagem['pub'])
            print(f"[REDE] Chave pública de p2 recebida: {chave_publica_do_adv}")

            # Fase 4: confirmar handshake — agora com cifra RSA
            enviar(sock, endereco_p2, {'t': 'INICIO', 'ok': True})
            print("[REDE] Handshake concluído — comunicação cifrada iniciada.")
            input("\n  [Pressione Enter para continuar...]\n")

    # Fase 5: aguardar SYNC do cliente (confirma que a thread de recepção está ativa)
    print("[REDE] Aguardando SYNC de p2...")

    while True:
        sock.settimeout(1.0)
        try:
            dados_brutos, endereco = sock.recvfrom(BUFFER_SIZE)
        except socket.timeout:
            continue

        if endereco != endereco_p2:
            continue

        try:
            mensagem = desempacotar(dados_brutos)
        except:
            continue

        if mensagem.get('t') == 'SYNC':
            break


# -------------------------------
# THREAD DO SERVIDOR (recebe ações de p2)
# -------------------------------

def thread_servidor(sock):
    """Thread responsável pelo handshake e pelo recebimento das ações do Jogador 2.

    Após concluir o handshake, inicia a primeira mão e entra em loop
    aguardando mensagens de p2. Processa ações do tipo ACAO (jogar_carta,
    truco, resp_truco, mao_de_onze), atualiza o estado global e reenvia
    o estado atualizado para p2. Encerra quando a fase 'fim_de_jogo' é
    atingida.
    """
    realizar_handshake(sock)

    # Iniciar a primeira mão
    estado = tg.iniciar_mao(obter_estado())
    salvar_estado(estado)
    enviar_estado_para_p2(sock, estado)

    print(f"[JOGO] Partida iniciada. Vira: {tg.nome_da_carta(estado['mao']['vira'])}")

    while True:
        sock.settimeout(0.2)
        try:
            dados_brutos, endereco = sock.recvfrom(BUFFER_SIZE)
        except socket.timeout:
            continue

        if endereco != endereco_p2:
            continue

        try:
            mensagem = desempacotar(dados_brutos)
        except:
            continue

        # p2 pediu sincronização do estado
        if mensagem.get('t') == 'SYNC':
            enviar_estado_para_p2(sock, obter_estado())
            continue

        if mensagem.get('t') != 'ACAO':
            continue

        estado = obter_estado()
        mao    = estado.get('mao') or {}
        acao   = mensagem.get('a')

        if acao == 'jogar_carta' and mao.get('precisa') == ADV:
            estado, _ = tg.jogar_carta(estado, ADV, mensagem['idx'])

        elif acao == 'truco':
            estado, _ = tg.pedir_truco(estado, ADV, mensagem['nivel'])

        elif acao == 'resp_truco':
            estado, _ = tg.responder_truco(estado, ADV, mensagem['aceitar'])

        elif acao == 'mao_de_onze':
            estado, _ = tg.decidir_mao_de_onze(estado, ADV, mensagem['jogar'])

        else:
            continue

        salvar_estado(estado)

        tipo_envio = 'FIM' if estado['fase'] == 'fim_de_jogo' else 'ESTADO'
        enviar_estado_para_p2(sock, estado, tipo_envio)

        if estado['fase'] == 'fim_de_jogo':
            break

    print("[REDE] Thread do servidor encerrada.")


# -------------------------------
# DISPLAY DO JOGO
# -------------------------------

def limpar_tela():
    """Limpa o terminal, compatível com sistemas Unix e Windows."""
    os.system('clear' if os.name != 'nt' else 'cls')


def mostrar_carta(carta):
    """Retorna a representação visual de uma carta para exibição na mesa.

    Retorna '[valor+naipe]' se a carta existir, ou '[ - ]' se for None.
    """
    if carta:
        return f"[{tg.nome_da_carta(carta)}]"
    return "[ - ]"


def exibir_estado(estado):
    """Renderiza no terminal o estado atual do jogo para o Jogador 1.

    Exibe placar, carta vira, manilhas, histórico de rodadas, cartas na
    mesa, aposta em vigor, cartas na mão e a mensagem de status atual.
    """
    limpar_tela()

    pontos = estado['pontos']
    mao    = estado.get('mao')

    separador = '─' * 50
    print(separador)
    print(f"  TRUCO PAULISTA [HOST / p1]   Placar: p1={pontos['p1']}  p2={pontos['p2']}")
    print(separador)

    if not mao:
        print(f"\n  {estado.get('mensagem', '')}")
        return

    print(f"  Vira: {tg.nome_da_carta(mao['vira'])}   Manilha: {tg.descricao_manilhas(mao['vira'])}")

    if mao['rodadas']:
        print("\n  Rodadas:")
        for i, rodada in enumerate(mao['rodadas'], 1):
            if rodada['vencedor'] == EU:
                quem_ganhou = 'você'
            elif rodada['vencedor'] == ADV:
                quem_ganhou = 'adv'
            else:
                quem_ganhou = 'empate'

            carta_eu  = tg.nome_da_carta(rodada[EU])
            carta_adv = tg.nome_da_carta(rodada[ADV])
            print(f"    {i}. {carta_eu} vs {carta_adv} → {quem_ganhou}")

    carta_na_mesa_eu  = mao['mesa'].get(EU)
    carta_na_mesa_adv = mao['mesa'].get(ADV)
    print(f"\n  Mesa:  Adv: {mostrar_carta(carta_na_mesa_adv)}   Você: {mostrar_carta(carta_na_mesa_eu)}")

    if mao.get('nivel_truco'):
        label_aposta = mao['nivel_truco'].upper()
    else:
        label_aposta = 'normal'

    print(f"  Aposta: {label_aposta} ({mao['aposta']} pt)")

    if estado['fase'] == 'truco' and mao.get('quem_pediu') == ADV:
        nivel_pend  = mao['truco_pendente']
        pontos_pend = tg.PONTOS_NIVEL[nivel_pend]
        print(f"  !!! {ADV} pediu {nivel_pend.upper()}! ({pontos_pend} pts) !!!")

    cartas_na_mao = mao['cartas'].get(EU, [])
    if cartas_na_mao:
        exibicao_cartas = '  '.join(
            f"[{i + 1}] {tg.nome_da_carta(c)}"
            for i, c in enumerate(cartas_na_mao)
        )
    else:
        exibicao_cartas = '(nenhuma)'

    print(f"\n  {exibicao_cartas}")
    print(f"  {ADV} tem {len(mao['cartas'].get(ADV, []))} carta(s).")
    print(f"\n  >> {estado.get('mensagem', '')}")


# -------------------------------
# CAPTURA DE AÇÃO DO JOGADOR
# -------------------------------

def capturar_acao(estado):
    """Lê e retorna a ação do Jogador 1 a partir da entrada do terminal.

    Exibe o menu adequado conforme a fase e o turno atual:
    - 'mao_de_onze': opções [j] Jogar / [f] Fugir.
    - 'truco': opções [a] Aceitar / [c] Correr / [r] Aumentar.
    - 'jogando': opções numéricas para jogar carta / [t] Pedir truco.

    Retorna uma tupla (tipo_acao, argumento) ou None se não for a vez do jogador.
    """
    mao   = estado['mao']
    fase  = estado['fase']

    # Mão de onze
    if fase == 'mao_de_onze' and mao.get('precisa') == EU:
        print("\n  Mão de Onze: [j] Jogar    [f] Fugir")

        while True:
            resposta = input("  > ").strip().lower()

            if resposta == 'j':
                return ('mao_de_onze', True)
            if resposta == 'f':
                return ('mao_de_onze', False)

    # Responder truco
    if fase == 'truco' and mao.get('precisa') == EU:
        proximo_nivel = tg.proximo_nivel_truco(mao)

        opcao_aumentar = ''
        if proximo_nivel:
            opcao_aumentar = f"  [r] → {proximo_nivel.upper()} ({tg.PONTOS_NIVEL[proximo_nivel]} pt)"

        print(f"\n  [a] Aceitar    [c] Correr{opcao_aumentar}")

        while True:
            resposta = input("  > ").strip().lower()

            if resposta == 'a':
                return ('responder', True)
            if resposta == 'c':
                return ('responder', False)
            if resposta == 'r' and proximo_nivel:
                return ('pedir_truco', proximo_nivel)

    # Jogar carta
    if fase == 'jogando' and mao.get('precisa') == EU:
        cartas        = mao['cartas'].get(EU, [])
        quantidade    = len(cartas)
        proximo_nivel = tg.proximo_nivel_truco(mao)

        opcao_truco = ''
        if proximo_nivel:
            opcao_truco = f"  [t] Truco → {proximo_nivel.upper()}"

        print(f"\n  Jogar: [1-{quantidade}]{opcao_truco}")

        while True:
            resposta = input("  > ").strip().lower()

            if resposta.isdigit():
                indice = int(resposta) - 1
                if 0 <= indice < quantidade:
                    return ('jogar', indice)

            if resposta == 't' and proximo_nivel:
                return ('pedir_truco', proximo_nivel)

    return None


# -------------------------------
# APLICAR AÇÃO DO JOGADOR 1 (LOCAL)
# -------------------------------

def aplicar_acao_p1(acao, sock):
    """Aplica a ação capturada do Jogador 1 ao estado do jogo e envia o estado atualizado para p2.

    Suporta os tipos: 'jogar', 'pedir_truco', 'responder' e 'mao_de_onze'.
    Após atualizar o estado, envia mensagem ESTADO ou FIM conforme a fase resultante.
    """
    estado = obter_estado()
    tipo_acao = acao[0]

    if tipo_acao == 'jogar':
        estado, _ = tg.jogar_carta(estado, EU, acao[1])

    elif tipo_acao == 'pedir_truco':
        estado, _ = tg.pedir_truco(estado, EU, acao[1])

    elif tipo_acao == 'responder':
        estado, _ = tg.responder_truco(estado, EU, acao[1])

    elif tipo_acao == 'mao_de_onze':
        estado, _ = tg.decidir_mao_de_onze(estado, EU, acao[1])

    salvar_estado(estado)

    tipo_envio = 'FIM' if estado['fase'] == 'fim_de_jogo' else 'ESTADO'
    enviar_estado_para_p2(sock, estado, tipo_envio)


# -------------------------------
# MAIN
# -------------------------------

def main():
    """Ponto de entrada do Jogador 1 (servidor).

    Detecta o IP local, carrega ou gera as chaves RSA, cria o socket UDP,
    inicia a thread do servidor e entra no loop principal do jogo. O loop
    exibe o estado, aguarda a ação do jogador local e a aplica. Encerra
    ao atingir a fase 'fim_de_jogo'.
    """
    global minha_chave_publica, minha_chave_privada

    limpar_tela()

    # Descobrir IP local para repassar ao Jogador 2
    try:
        aux = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        aux.connect(("8.8.8.8", 80))
        ip_local = aux.getsockname()[0]
        aux.close()
    except:
        ip_local = "127.0.0.1"

    print(f"  IP: {ip_local}   Porta: {PORTA}")
    print(f"  Passe esse IP para o Jogador 2.\n")

    # Carregar ou gerar chaves RSA
    if CHAVE_PUBLICA_P1 and CHAVE_PRIVADA_P1:
        minha_chave_publica = CHAVE_PUBLICA_P1
        minha_chave_privada = CHAVE_PRIVADA_P1
        print(f"  Chave pública  [E, N] = {minha_chave_publica}")
        print(f"  Chave privada  [D, N] = {minha_chave_privada}")
    else:
        print("  === GERAÇÃO DAS CHAVES RSA (Jogador 1) ===")
        minha_chave_publica, minha_chave_privada = gerar_chaves_rsa()

    # Criar socket UDP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', PORTA))

    # Iniciar thread do servidor (handshake + recepção de ações de p2)
    thread = threading.Thread(target=thread_servidor, args=(sock,), daemon=True)
    thread.start()

    # Aguardar conexão e início da partida
    while endereco_p2 is None:
        time.sleep(0.2)

    while chave_publica_do_adv is None:
        time.sleep(0.2)

    while obter_estado().get('fase') in ('aguardando', 'pronto', None):
        time.sleep(0.2)

    # Loop principal do jogo
    while True:
        _evento.wait(0.5)
        _evento.clear()

        estado = obter_estado()
        fase   = estado.get('fase', '')

        exibir_estado(estado)

        if fase == 'fim_de_jogo':
            vencedor = estado.get('vencedor')
            if vencedor == EU:
                print("\n  FIM! VOCÊ VENCEU! 🎉")
            else:
                print("\n  FIM! Você perdeu.")
            print(f"  Placar final: p1 {estado['pontos']['p1']} × {estado['pontos']['p2']} p2")
            break

        if fase == 'fim_de_mao':
            input("\n  [Enter] para iniciar a próxima mão...")
            estado = tg.iniciar_mao(obter_estado())
            salvar_estado(estado)
            enviar_estado_para_p2(sock, estado)
            continue

        mao = estado.get('mao')
        if not mao or mao.get('precisa') != EU:
            continue

        acao = capturar_acao(estado)
        if acao:
            aplicar_acao_p1(acao, sock)

    sock.close()


if __name__ == "__main__":
    main()