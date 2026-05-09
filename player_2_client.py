#!/usr/bin/env python3
"""Truco Paulista — Jogador 2 (CLIENT)"""

import socket
import json
import time
import os
import threading
import truco_game as tg


# -------------------------------
# IDENTIFICAÇÃO DOS JOGADORES
# -------------------------------

EU  = 'p2'
ADV = 'p1'


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
#   CHAVE_PUBLICA_P2  = [31, 323]   # [E, N]
#   CHAVE_PRIVADA_P2  = [223, 323]  # [D, N]

CHAVE_PUBLICA_P2  = [37, 899]   # [E, N]
CHAVE_PRIVADA_P2  = [613, 899]  # [D, N]


# -------------------------------
# VARIÁVEIS DE ESTADO (RUNTIME)
# -------------------------------

minha_chave_publica  = None
minha_chave_privada  = None
chave_publica_do_adv = None   # recebida no handshake

_lock_estado = threading.Lock()
_estado_recebido = None
_evento          = threading.Event()


# -------------------------------
# FUNÇÕES AUXILIARES - PRIMOS
# -------------------------------

def eh_primo(numero):
    if numero < 2:
        return False

    for i in range(2, int(numero ** 0.5) + 1):
        if numero % i == 0:
            return False

    return True


def gerar_lista_primos(limite):
    lista = []

    for numero in range(2, limite):
        if eh_primo(numero):
            lista.append(numero)

    return lista


# -------------------------------
# GERAÇÃO DAS CHAVES RSA
# -------------------------------

def escolher_p_e_q(lista_primos):
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
    n        = p * q
    totiente = (p - 1) * (q - 1)

    print(f"\nN (módulo)  = {n}")
    print(f"Totiente    = {totiente}")

    return n, totiente


def escolher_e(q, totiente):
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
    d = 1

    while True:
        d += 1
        if (e * d) % totiente == 1:
            return d


def gerar_chaves_rsa():
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
    e, n    = chave_publica
    cifrado = ""

    for char in texto:
        valor_tabela  = CHAVE_CRIPTO[char]
        valor_cifrado = pow(valor_tabela, e, n)
        cifrado += f"{valor_cifrado:05d}"

    return cifrado


def descriptografar(texto_cifrado, chave_privada):
    d, n      = chave_privada
    decifrado = ""

    for i in range(0, len(texto_cifrado), TAMANHO_BLOCO):
        bloco     = texto_cifrado[i:i + TAMANHO_BLOCO]
        valor_cod = int(bloco)
        valor_dec = pow(valor_cod, d, n)
        decifrado += CHAVE_DECRIPTO[valor_dec]

    return decifrado


def empacotar(dados):
    texto_json    = json.dumps(dados, ensure_ascii=True)
    texto_cifrado = criptografar(texto_json, chave_publica_do_adv)
    return texto_cifrado.encode()


def desempacotar(dados_brutos):
    texto_cifrado = dados_brutos.decode()
    texto_json    = descriptografar(texto_cifrado, minha_chave_privada)
    return json.loads(texto_json)


# -------------------------------
# FUNÇÕES DE ESTADO RECEBIDO
# -------------------------------

def salvar_estado(novo_estado):
    global _estado_recebido
    with _lock_estado:
        _estado_recebido = novo_estado
    _evento.set()


def obter_estado():
    with _lock_estado:
        return _estado_recebido


# -------------------------------
# FUNÇÕES DE REDE
# -------------------------------

def enviar(sock, endereco, dados):
    try:
        sock.sendto(empacotar(dados), endereco)
    except Exception as erro:
        print(f"[ERRO AO ENVIAR] {erro}")


def definir_chave_publica_do_adv(chave):
    global chave_publica_do_adv
    chave_publica_do_adv = chave


# -------------------------------
# THREAD DE RECEPÇÃO
# -------------------------------

def thread_recepcao(sock):
    while True:
        sock.settimeout(0.3)
        try:
            dados_brutos, _ = sock.recvfrom(BUFFER_SIZE)
        except socket.timeout:
            continue
        except OSError:
            break

        try:
            mensagem = desempacotar(dados_brutos)
        except:
            continue

        if 'st' in mensagem:
            salvar_estado(mensagem['st'])


# -------------------------------
# HANDSHAKE RSA
# -------------------------------

def realizar_handshake(sock, endereco_servidor):
    # Fase 1: enviar INICIO para p1 (sem cifra ainda)
    while True:
        sock.sendto(json.dumps({'t': 'INICIO'}).encode(), endereco_servidor)
        sock.settimeout(2.0)

        try:
            dados_brutos, _ = sock.recvfrom(BUFFER_SIZE)
            mensagem = json.loads(dados_brutos.decode())   # sem cifra ainda

            if mensagem.get('t') == 'CHAVE' and 'pub' in mensagem:
                definir_chave_publica_do_adv(mensagem['pub'])
                print(f"[REDE] Chave pública de p1 recebida: {chave_publica_do_adv}")
                break

        except socket.timeout:
            print("[REDE] Sem resposta, tentando novamente...")

    # Fase 2: enviar chave pública de p2 para p1 (sem cifra)
    sock.sendto(json.dumps({'t': 'CHAVE', 'pub': minha_chave_publica}).encode(), endereco_servidor)
    print(f"[REDE] Chave pública de p2 enviada: {minha_chave_publica}")

    # Fase 3: aguardar confirmação cifrada de p1
    while True:
        sock.settimeout(2.0)
        try:
            dados_brutos, _ = sock.recvfrom(BUFFER_SIZE)
            mensagem = desempacotar(dados_brutos)   # agora com cifra RSA

            if mensagem.get('t') == 'INICIO' and mensagem.get('ok'):
                print("[REDE] Handshake concluído — comunicação cifrada iniciada!")
                break

        except socket.timeout:
            print("[REDE] Aguardando confirmação de p1...")
            sock.sendto(json.dumps({'t': 'CHAVE', 'pub': minha_chave_publica}).encode(), endereco_servidor)


# -------------------------------
# DISPLAY DO JOGO
# -------------------------------

def limpar_tela():
    os.system('clear' if os.name != 'nt' else 'cls')


def mostrar_carta(carta):
    if carta:
        return f"[{tg.nome_da_carta(carta)}]"
    return "[ - ]"


def exibir_estado(estado):
    limpar_tela()

    pontos = estado['pontos']
    mao    = estado.get('mao')

    separador = '─' * 50
    print(separador)
    print(f"  TRUCO PAULISTA [CLIENT / p2]   Placar: p1={pontos['p1']}  p2={pontos['p2']}")
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
    mao  = estado['mao']
    fase = estado['fase']

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
# MAIN
# -------------------------------

def main():
    global minha_chave_publica, minha_chave_privada

    limpar_tela()

    # Carregar ou gerar chaves RSA
    if CHAVE_PUBLICA_P2 and CHAVE_PRIVADA_P2:
        minha_chave_publica = CHAVE_PUBLICA_P2
        minha_chave_privada = CHAVE_PRIVADA_P2
        print(f"  Chave pública  [E, N] = {minha_chave_publica}")
        print(f"  Chave privada  [D, N] = {minha_chave_privada}")
    else:
        print("  === GERAÇÃO DAS CHAVES RSA (Jogador 2) ===")
        minha_chave_publica, minha_chave_privada = gerar_chaves_rsa()

    ip_servidor = input("\n  IP do Jogador 1: ").strip() or "127.0.0.1"
    endereco_servidor = (ip_servidor, PORTA)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print(f"[REDE] Conectando a {ip_servidor}:{PORTA}...")

    realizar_handshake(sock, endereco_servidor)

    # Iniciar thread de recepção de estados
    thread = threading.Thread(target=thread_recepcao, args=(sock,), daemon=True)
    thread.start()

    # Fase 4: enviar SYNC para confirmar que a thread está ativa
    print("[JOGO] Aguardando início da partida...")

    while True:
        enviar(sock, endereco_servidor, {'t': 'SYNC'})
        _evento.wait(1.0)
        _evento.clear()

        estado = obter_estado()
        if estado and estado.get('fase') not in ('aguardando', 'pronto', None):
            break

    # Loop principal do jogo
    while True:
        estado = obter_estado()

        if estado is None:
            time.sleep(0.2)
            continue

        exibir_estado(estado)
        fase = estado.get('fase', '')

        if fase == 'fim_de_jogo':
            vencedor = estado.get('vencedor')
            if vencedor == EU:
                print("\n  FIM! VOCÊ VENCEU! 🎉")
            else:
                print("\n  FIM! Você perdeu.")
            print(f"  Placar final: p1 {estado['pontos']['p1']} × {estado['pontos']['p2']} p2")
            break

        if fase == 'fim_de_mao':
            print("\n  Aguardando próxima mão...")

            while True:
                _evento.wait(1.0)
                _evento.clear()
                novo_estado = obter_estado()

                if novo_estado and novo_estado.get('fase') in ('jogando', 'mao_de_onze'):
                    break

            continue

        mao = estado.get('mao')
        if not mao:
            time.sleep(0.2)
            continue

        if mao.get('precisa') != EU:
            _evento.wait(1.0)
            _evento.clear()
            continue

        acao = capturar_acao(estado)
        if not acao:
            continue

        tipo_acao = acao[0]

        if tipo_acao == 'jogar':
            mensagem = {'t': 'ACAO', 'a': 'jogar_carta', 'idx': acao[1]}

        elif tipo_acao == 'pedir_truco':
            mensagem = {'t': 'ACAO', 'a': 'truco', 'nivel': acao[1]}

        elif tipo_acao == 'responder':
            mensagem = {'t': 'ACAO', 'a': 'resp_truco', 'aceitar': acao[1]}

        elif tipo_acao == 'mao_de_onze':
            mensagem = {'t': 'ACAO', 'a': 'mao_de_onze', 'jogar': acao[1]}

        else:
            continue

        enviar(sock, endereco_servidor, mensagem)

        # Aguardar confirmação de que o estado mudou
        fase_anterior    = fase
        precisa_anterior = mao.get('precisa')
        rodadas_anterior = len(mao.get('rodadas', []))
        prazo = time.time() + 5

        while time.time() < prazo:
            _evento.wait(0.5)
            _evento.clear()

            novo_estado = obter_estado()
            if novo_estado:
                nova_mao = novo_estado.get('mao') or {}
                fase_mudou    = novo_estado.get('fase') != fase_anterior
                precisa_mudou = nova_mao.get('precisa') != precisa_anterior
                # Detecta quando uma rodada foi resolvida mesmo que 'precisa'
                # continue sendo p2 (caso p2 vença a rodada e jogue primeiro na próxima)
                rodadas_mudou = len(nova_mao.get('rodadas', [])) != rodadas_anterior

                if fase_mudou or precisa_mudou or rodadas_mudou:
                    break

            # Re-solicita o estado ao servidor para tolerância a perda de pacote UDP
            enviar(sock, endereco_servidor, {'t': 'SYNC'})

    sock.close()


if __name__ == "__main__":
    main()