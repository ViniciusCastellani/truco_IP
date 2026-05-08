#!/usr/bin/env python3
"""
Truco Paulista — Jogador 1 (HOST)
Este arquivo substitui server.py + player_1.py.
Roda na máquina do Jogador 1, que hospeda a partida.

Uso:
  1. Execute este arquivo: python player_1_host.py
  2. Informe seu IP para o Jogador 2 (exibido na tela).
  3. Aguarde o Jogador 2 conectar.

O Jogador 2 deve rodar player_2_client.py apontando para o IP desta máquina.
"""

import socket, json, time, os, threading
import truco_game as tg

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

PLAYER_ID   = 'p1'
OPPONENT_ID = 'p2'

# Porta que este host vai escutar (Jogador 2 conecta aqui)
HOST_PORT = 5000
HOST_BIND = '0.0.0.0'   # escuta em todas as interfaces

# ══════════════════════════════════════════════════════════════════════════════
#  RSA
# ══════════════════════════════════════════════════════════════════════════════

CHAVE_PUBLICA  = [29, 247]
CHAVE_PRIVADA  = [149, 247]

def _egcd(a, b):
    if a == 0: return b, 0, 1
    g, x, y = _egcd(b % a, a)
    return g, y - (b // a) * x, x

def _inverso_modular(e, phi):
    g, x, _ = _egcd(e, phi)
    if g != 1: raise ValueError("e e phi não coprimos!")
    return x % phi

def criptografar(mensagem: str, chave: list) -> list:
    e, n = chave
    return [pow(ord(ch), e, n) for ch in mensagem if ord(ch) < n]

def descriptografar(cifrado: list, chave: list) -> str:
    d, n = chave
    return ''.join(chr(pow(c, d, n)) for c in cifrado)

def _empacotar(dados: dict) -> bytes:
    texto   = json.dumps(dados)
    cifrado = criptografar(texto, CHAVE_PUBLICA)
    return json.dumps(cifrado).encode('utf-8')

def _desempacotar(raw: bytes) -> dict:
    cifrado = json.loads(raw.decode('utf-8'))
    texto   = descriptografar(cifrado, CHAVE_PRIVADA)
    return json.loads(texto)


# ══════════════════════════════════════════════════════════════════════════════
#  ESTADO COMPARTILHADO (protegido por lock)
# ══════════════════════════════════════════════════════════════════════════════

_lock          = threading.Lock()
_estado        = tg.new_game()
_addr_p2       = None          # endereço UDP do Jogador 2
_estado_novo   = threading.Event()   # sinaliza ao loop principal que houve update


def _get_estado():
    with _lock:
        import copy
        return copy.deepcopy(_estado)

def _set_estado(novo):
    global _estado
    with _lock:
        _estado = novo
    _estado_novo.set()


# ══════════════════════════════════════════════════════════════════════════════
#  PROTOCOLO — mesma estrutura do server.py original
# ══════════════════════════════════════════════════════════════════════════════

def _estado_para_msg(st, tipo, dados_extras=None):
    h = st.get('hand') or {}
    return {
        "tipo_msg":     tipo,
        "vez":          h.get('needs') or h.get('turn') or 'p1',
        "vira":         h.get('vira'),
        "valor_rodada": h.get('stake', 1),
        "mesa": {
            "p1": h.get('table', {}).get('p1'),
            "p2": h.get('table', {}).get('p2'),
        },
        "pontos": {
            "p1": st['scores']['p1'],
            "p2": st['scores']['p2'],
        },
        "qtd_cartas": {
            "p1": len(h.get('cards', {}).get('p1', [])),
            "p2": len(h.get('cards', {}).get('p2', [])),
        },
        "dados_extras":  dados_extras or {},
        "_phase":        st.get('phase'),
        "_message":      st.get('message', ''),
        "_hand":         h,
        "_winner":       st.get('winner'),
        "_dealer":       st.get('dealer'),
    }


def _enviar(sock, addr, dados):
    try:
        sock.sendto(_empacotar(dados), addr)
    except Exception as ex:
        print(f"[ERRO REDE] Falha ao enviar para {addr}: {ex}")


def _broadcast(sock, addr_p2, st, tipo, dados_extras=None):
    """Envia o estado atual para o Jogador 2."""
    if addr_p2:
        _enviar(sock, addr_p2, _estado_para_msg(st, tipo, dados_extras))


# ══════════════════════════════════════════════════════════════════════════════
#  THREAD DO SERVIDOR — processa mensagens do Jogador 2
# ══════════════════════════════════════════════════════════════════════════════

def _thread_servidor(sock):
    global _addr_p2

    print(f"[NET] Aguardando Jogador 2 na porta {HOST_PORT}...")

    # ── Fase de conexão ──────────────────────────────────────────────────────
    while _addr_p2 is None:
        sock.settimeout(1.0)
        try:
            raw, addr = sock.recvfrom(65535)
            dados = _desempacotar(raw)
        except socket.timeout:
            continue
        except Exception as ex:
            print(f"[ERRO] {ex}")
            continue

        if dados.get('tipo_msg') == 'INICIO' and dados.get('vez') == 'p2':
            _addr_p2 = addr
            print(f"[JOGO] Jogador 2 conectado de {addr}")

            ack = {
                "tipo_msg": "INICIO", "vez": "p2",
                "vira": None, "valor_rodada": 1,
                "mesa": {"p1": None, "p2": None},
                "pontos": {"p1": 0, "p2": 0},
                "qtd_cartas": {"p1": 0, "p2": 0},
                "dados_extras": {"status": "conectado", "aguardando": False},
                "_phase": "waiting",
                "_message": "p2 conectado! Iniciando...",
                "_hand": None, "_winner": None, "_dealer": "p1",
            }
            _enviar(sock, addr, ack)

    # ── Iniciar partida ──────────────────────────────────────────────────────
    st = _get_estado()
    st['phase'] = 'ready'
    st = tg.start_hand(st)
    _set_estado(st)
    _broadcast(sock, _addr_p2, st, 'ESTADO')
    print(f"[JOGO] Partida iniciada! Vira: {tg.label(st['hand']['vira'])}")

    # ── Loop principal do servidor ───────────────────────────────────────────
    while True:
        sock.settimeout(0.2)
        try:
            raw, addr = sock.recvfrom(65535)
            dados = _desempacotar(raw)
        except socket.timeout:
            continue
        except Exception as ex:
            print(f"[ERRO RECV] {ex}")
            continue

        if addr != _addr_p2:
            continue

        tipo  = dados.get('tipo_msg')
        pid   = dados.get('vez')
        st    = _get_estado()
        phase = st.get('phase')
        h     = st.get('hand') or {}

        # ── Jogada do p2 ────────────────────────────────────────────────────
        if tipo == 'JOGADA' and pid == 'p2':
            extras = dados.get('dados_extras', {})
            acao   = extras.get('acao')

            if acao == 'JOGAR_CARTA':
                if h.get('needs') != 'p2':
                    continue
                st, msg = tg.play_card(st, 'p2', extras.get('idx'))
                _set_estado(st)
                _broadcast(sock, _addr_p2, st, 'JOGADA', {"resultado": msg})

            elif acao == 'TRUCO':
                st, msg = tg.call_truco(st, 'p2', extras.get('nivel'))
                _set_estado(st)
                _broadcast(sock, _addr_p2, st, 'TRUCO', {"acao": "TRUCO", "nivel": extras.get('nivel')})

            elif acao == 'RESPONDER_TRUCO':
                st, msg = tg.respond_truco(st, 'p2', extras.get('aceitar'))
                _set_estado(st)
                _broadcast(sock, _addr_p2, st, 'TRUCO', {"acao": "RESPOSTA", "aceitar": extras.get('aceitar'), "resultado": msg})

            elif acao == 'MAO11':
                st, msg = tg.mao11_decide(st, 'p2', extras.get('jogar'))
                _set_estado(st)
                _broadcast(sock, _addr_p2, st, 'ESTADO', {"acao": "MAO11", "resultado": msg})

            # Fim de mão / partida
            if st['phase'] == 'hand_over':
                _broadcast(sock, _addr_p2, st, 'ESTADO', {"evento": "mao_encerrada"})
            elif st['phase'] == 'game_over':
                _broadcast(sock, _addr_p2, st, 'FIM', {"vencedor": st['winner']})
                break

        # ── Pedido de próxima mão ────────────────────────────────────────────
        elif tipo == 'ESTADO' and dados.get('dados_extras', {}).get('acao') == 'PROXIMA_MAO':
            if phase == 'hand_over':
                st = tg.start_hand(st)
                _set_estado(st)
                _broadcast(sock, _addr_p2, st, 'ESTADO', {"evento": "nova_mao"})

        # ── Ping / sync ──────────────────────────────────────────────────────
        elif tipo == 'ESTADO':
            _broadcast(sock, _addr_p2, st, 'ESTADO')

    print("[NET] Thread servidor encerrada.")


# ══════════════════════════════════════════════════════════════════════════════
#  DISPLAY (idêntico ao player_1.py original)
# ══════════════════════════════════════════════════════════════════════════════

def clr():
    os.system('clear' if os.name != 'nt' else 'cls')

def card_str(c):
    return f'[{tg.label(c)}]' if c else '[ - ]'

def draw(st):
    clr()
    sc    = st['scores']
    phase = st['phase']
    you   = PLAYER_ID
    adv   = OPPONENT_ID

    SEP = '─' * 50
    print(SEP)
    print(f'  TRUCO PAULISTA  [HOST/p1]     Você: {you}')
    print(f'  Placar:  p1 = {sc["p1"]:2}    p2 = {sc["p2"]:2}')
    print(SEP)

    h = st.get('hand')
    if not h:
        print(f'\n  {st.get("message", "")}')
        return

    vira = h['vira']
    print(f'  Vira: {tg.label(vira)}   Manilha: {tg.manilha_str(vira)}')
    print(SEP)

    if h.get('rodadas'):
        print('\n  Rodadas jogadas:')
        for i, r in enumerate(h['rodadas'], 1):
            mark = 'você' if r['winner'] == you else ('adv' if r['winner'] == adv else 'empate')
            print(f'    {i}. {tg.label(r[you])} vs {tg.label(r[adv])}  →  {mark}')

    print('\n  Mesa:')
    print(f'    Adv ({adv}):   {card_str(h["table"].get(adv))}')
    print(f'    Você ({you}):  {card_str(h["table"].get(you))}')

    stake_label = h["truco_level"].upper() if h.get("truco_level") else "normal"
    print(f'\n  Aposta: {stake_label} ({h["stake"]} pt(s))')
    if phase == 'truco' and h.get('truco_caller') == adv:
        print(f'  !!! {adv} pediu {h["truco_pending"].upper()}! ({tg.STAKES[h["truco_pending"]]} pts) !!!')

    cards = h['cards'].get(you, [])
    print()
    if cards:
        parts = '   '.join(f'[{i+1}] {tg.label(c)}' for i, c in enumerate(cards))
        print(f'  Suas cartas: {parts}')
    else:
        print('  Suas cartas: (nenhuma)')

    opp_count = len(h['cards'].get(adv, []))
    print(f'  {adv} tem {opp_count} carta(s) na mão.')
    print(f'\n  >> {st.get("message", "")}')


# ══════════════════════════════════════════════════════════════════════════════
#  INPUT
# ══════════════════════════════════════════════════════════════════════════════

def get_action(st):
    h     = st['hand']
    phase = st['phase']

    if phase == 'mao11' and h.get('needs') == PLAYER_ID:
        print('\n  Mão de Onze — veja suas cartas e decida:')
        print('  [j] Jogar   [f] Fugir')
        while True:
            r = input('  > ').strip().lower()
            if r == 'j': return ('mao11', True)
            if r == 'f': return ('mao11', False)

    if phase == 'truco' and h.get('needs') == PLAYER_ID:
        nxt  = tg.next_truco_level(h)
        opts = '[a] Aceitar   [c] Correr'
        if nxt:
            opts += f'   [r] Aumentar → {nxt.upper()} ({tg.STAKES[nxt]} pts)'
        print(f'\n  {opts}')
        while True:
            r = input('  > ').strip().lower()
            if r == 'a': return ('respond', True)
            if r == 'c': return ('respond', False)
            if r == 'r' and nxt: return ('call_truco', nxt)

    if phase == 'playing' and h.get('needs') == PLAYER_ID:
        cards   = h['cards'][PLAYER_ID]
        n       = len(cards)
        nxt_tru = tg.next_truco_level(h)
        opts    = f'  Jogar: [1-{n}]'
        if nxt_tru:
            opts += f'   Truco: [t] → {nxt_tru.upper()} ({tg.STAKES[nxt_tru]} pts)'
        print(f'\n{opts}')
        while True:
            r = input('  > ').strip().lower()
            if r.isdigit():
                idx = int(r) - 1
                if 0 <= idx < n:
                    return ('play', idx)
                print(f'  Escolha entre 1 e {n}.')
            elif r == 't' and nxt_tru:
                return ('call_truco', nxt_tru)

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  APLICA JOGADA DO P1 LOCALMENTE (sem rede — está na mesma máquina)
# ══════════════════════════════════════════════════════════════════════════════

def aplicar_acao_p1(action, sock):
    st    = _get_estado()
    phase = st['phase']
    h     = st['hand'] or {}
    kind  = action[0]

    msg = ''
    if kind == 'play':
        if h.get('needs') != PLAYER_ID:
            return
        st, msg = tg.play_card(st, PLAYER_ID, action[1])
        _set_estado(st)
        _broadcast(sock, _addr_p2, st, 'JOGADA', {"resultado": msg})

    elif kind == 'call_truco':
        st, msg = tg.call_truco(st, PLAYER_ID, action[1])
        _set_estado(st)
        _broadcast(sock, _addr_p2, st, 'TRUCO', {"acao": "TRUCO", "nivel": action[1]})

    elif kind == 'respond':
        st, msg = tg.respond_truco(st, PLAYER_ID, action[1])
        _set_estado(st)
        _broadcast(sock, _addr_p2, st, 'TRUCO', {"acao": "RESPOSTA", "aceitar": action[1], "resultado": msg})

    elif kind == 'mao11':
        st, msg = tg.mao11_decide(st, PLAYER_ID, action[1])
        _set_estado(st)
        _broadcast(sock, _addr_p2, st, 'ESTADO', {"acao": "MAO11", "resultado": msg})

    if msg:
        print(f"[JOGO] {msg}")

    # Fim de mão / partida
    st = _get_estado()
    if st['phase'] == 'hand_over':
        _broadcast(sock, _addr_p2, st, 'ESTADO', {"evento": "mao_encerrada"})
    elif st['phase'] == 'game_over':
        _broadcast(sock, _addr_p2, st, 'FIM', {"vencedor": st['winner']})


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def _get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    clr()
    print("=" * 52)
    print("  TRUCO PAULISTA — Jogador 1 [HOST]")
    print("=" * 52)

    ip_local = _get_local_ip()
    print(f"\n  Seu IP na rede: {ip_local}")
    print(f"  Porta:          {HOST_PORT}")
    print(f"\n  Passe para o Jogador 2:")
    print(f"  → IP: {ip_local}   Porta: {HOST_PORT}\n")

    # Socket UDP compartilhado entre thread e loop principal
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST_BIND, HOST_PORT))

    # Inicia thread do servidor em background
    t = threading.Thread(target=_thread_servidor, args=(sock,), daemon=True)
    t.start()

    # Aguarda Jogador 2 conectar antes de iniciar a UI
    print("[JOGO] Aguardando Jogador 2 conectar...\n")
    while _addr_p2 is None:
        time.sleep(0.3)

    # Aguarda partida iniciar (thread muda o estado para 'playing')
    while True:
        st = _get_estado()
        if st.get('phase') not in ('waiting', 'ready', None):
            break
        time.sleep(0.2)

    # ── Loop principal do Jogador 1 ──────────────────────────────────────────
    while True:
        # Aguarda sinal de mudança de estado ou timeout
        _estado_novo.wait(timeout=0.5)
        _estado_novo.clear()

        st    = _get_estado()
        phase = st.get('phase', '')

        draw(st)

        if phase == 'game_over':
            w = st.get('winner')
            print(f'\n  JOGO ENCERRADO! {"VOCÊ VENCEU! 🎉" if w == PLAYER_ID else "Você perdeu."}')
            print(f'  Placar final: p1 {st["scores"]["p1"]} × {st["scores"]["p2"]} p2')
            break

        if phase == 'hand_over':
            input('\n  [Enter] para iniciar próxima mão...')
            st = tg.start_hand(_get_estado())
            _set_estado(st)
            _broadcast(sock, _addr_p2, st, 'ESTADO', {"evento": "nova_mao"})
            continue

        h = st.get('hand')
        if not h:
            continue

        needs_me = (h.get('needs') == PLAYER_ID)
        if not needs_me:
            # Não é minha vez — aguarda evento da thread
            continue

        # ── Minha vez ────────────────────────────────────────────────────────
        action = get_action(st)
        if action:
            aplicar_acao_p1(action, sock)

    sock.close()
    print("[NET] Encerrado.")


if __name__ == '__main__':
    main()