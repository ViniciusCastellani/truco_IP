#!/usr/bin/env python3
"""
Truco Paulista — Jogador 1 (HOST)
"""

import socket, json, time, os, threading
import truco_game as tg

PLAYER_ID   = 'p1'
OPPONENT_ID = 'p2'

HOST_PORT = 5000
HOST_BIND = '0.0.0.0'

# ══════════════════════════════════════════════════════════════════════════════
#  RSA
# ══════════════════════════════════════════════════════════════════════════════

CHAVE_PUBLICA  = [29, 247]
CHAVE_PRIVADA  = [149, 247]

def _egcd(a, b):
    if a == 0: return b, 0, 1
    g, x, y = _egcd(b % a, a)
    return g, y - (b // a) * x, x

def criptografar(mensagem: str, chave: list) -> list:
    e, n = chave
    resultado = []
    for ch in mensagem:
        code = ord(ch)
        if code >= n:
            resultado.append(n)
            resultado.append(code // n)
            resultado.append(code % n)
        else:
            resultado.append(pow(code, e, n))
    return resultado

def descriptografar(cifrado: list, chave: list) -> str:
    d, n = chave
    resultado = []
    i = 0
    while i < len(cifrado):
        val = cifrado[i]
        if val == n:
            code = cifrado[i+1] * n + cifrado[i+2]
            resultado.append(chr(code))
            i += 3
        else:
            resultado.append(chr(pow(val, d, n)))
            i += 1
    return ''.join(resultado)

def _empacotar(dados: dict) -> bytes:
    texto   = json.dumps(dados, ensure_ascii=True)
    cifrado = criptografar(texto, CHAVE_PUBLICA)
    return json.dumps(cifrado).encode('utf-8')

def _desempacotar(raw: bytes) -> dict:
    cifrado = json.loads(raw.decode('utf-8'))
    texto   = descriptografar(cifrado, CHAVE_PRIVADA)
    return json.loads(texto)


# ══════════════════════════════════════════════════════════════════════════════
#  ESTADO COMPARTILHADO
# ══════════════════════════════════════════════════════════════════════════════

_lock        = threading.Lock()
_estado      = tg.new_game()
_addr_p2     = None
_estado_novo = threading.Event()


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
#  PROTOCOLO
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
        packed = _empacotar(dados)
        sock.sendto(packed, addr)
    except Exception as ex:
        print(f"[ERRO REDE] Falha ao enviar para {addr}: {ex}")


def _broadcast(sock, addr_p2, st, tipo, dados_extras=None):
    if addr_p2:
        _enviar(sock, addr_p2, _estado_para_msg(st, tipo, dados_extras))


# ══════════════════════════════════════════════════════════════════════════════
#  THREAD DO SERVIDOR
# ══════════════════════════════════════════════════════════════════════════════

def _thread_servidor(sock):
    global _addr_p2

    print(f"[NET] Aguardando Jogador 2 na porta {HOST_PORT}...")

    # ── Fase de conexão ──────────────────────────────────────────────────────
    while _addr_p2 is None:
        sock.settimeout(1.0)
        try:
            raw, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except Exception as ex:
            print(f"[ERRO RECV] {ex}")
            continue

        try:
            dados = _desempacotar(raw)
        except Exception as ex:
            print(f"[ERRO CRIPTO] Pacote de {addr} não pôde ser lido: {ex}")
            continue

        print(f"[DEBUG] Pacote recebido de {addr}: tipo={dados.get('tipo_msg')} vez={dados.get('vez')}")

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
            for _ in range(3):
                _enviar(sock, addr, ack)
                time.sleep(0.05)

    # ── Iniciar partida ──────────────────────────────────────────────────────
    st = _get_estado()
    st['phase'] = 'ready'
    st = tg.start_hand(st)
    _set_estado(st)
    for _ in range(3):
        _broadcast(sock, _addr_p2, st, 'ESTADO')
        time.sleep(0.1)
    print(f"[JOGO] Partida iniciada! Vira: {tg.label(st['hand']['vira'])}")

    # ── Loop principal do servidor ───────────────────────────────────────────
    while True:
        sock.settimeout(0.2)
        try:
            raw, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except Exception as ex:
            print(f"[ERRO RECV] {ex}")
            continue

        if addr != _addr_p2:
            continue

        try:
            dados = _desempacotar(raw)
        except Exception as ex:
            print(f"[ERRO CRIPTO] {ex}")
            continue

        tipo  = dados.get('tipo_msg')
        pid   = dados.get('vez')
        st    = _get_estado()
        phase = st.get('phase')
        h     = st.get('hand') or {}

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

            if st['phase'] == 'hand_over':
                _broadcast(sock, _addr_p2, st, 'ESTADO', {"evento": "mao_encerrada"})
            elif st['phase'] == 'game_over':
                _broadcast(sock, _addr_p2, st, 'FIM', {"vencedor": st['winner']})
                break

        elif tipo == 'ESTADO' and dados.get('dados_extras', {}).get('acao') == 'PROXIMA_MAO':
            # FIX: não chama start_hand aqui — P1 é o único que controla o
            # início da próxima mão (loop principal). Apenas reenvia o estado
            # atual para P2 sincronizar caso ele ainda esteja esperando.
            st = _get_estado()
            _broadcast(sock, _addr_p2, st, 'ESTADO', {"evento": "sync_mao"})

        elif tipo == 'ESTADO':
            _broadcast(sock, _addr_p2, st, 'ESTADO')

    print("[NET] Thread servidor encerrada.")


# ══════════════════════════════════════════════════════════════════════════════
#  DISPLAY
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
#  APLICA JOGADA DO P1 LOCALMENTE
# ══════════════════════════════════════════════════════════════════════════════

def aplicar_acao_p1(action, sock):
    st    = _get_estado()
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
    print(f"  → IP: {ip_local}   Porta: {HOST_PORT}")
    print(f"\n  ⚠️  Verifique se o firewall permite UDP na porta {HOST_PORT}")
    print(f"     Linux:   sudo ufw allow {HOST_PORT}/udp")
    print(f"     Windows: netsh advfirewall firewall add rule name=Truco protocol=UDP dir=in localport={HOST_PORT} action=allow\n")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST_BIND, HOST_PORT))
    print(f"[NET] Socket UDP vinculado em {HOST_BIND}:{HOST_PORT} ✓\n")

    t = threading.Thread(target=_thread_servidor, args=(sock,), daemon=True)
    t.start()

    print("[JOGO] Aguardando Jogador 2 conectar...\n")
    while _addr_p2 is None:
        time.sleep(0.3)

    while True:
        st = _get_estado()
        if st.get('phase') not in ('waiting', 'ready', None):
            break
        time.sleep(0.2)

    # ── Loop principal do Jogador 1 ──────────────────────────────────────────
    while True:
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
            # FIX: somente P1 chama start_hand. A thread do servidor não o faz
            # mais, evitando o double-shuffle que causava dessincronia.
            st = tg.start_hand(_get_estado())
            _set_estado(st)
            # Envia múltiplas vezes para garantir que P2 receba o novo estado
            for _ in range(3):
                _broadcast(sock, _addr_p2, st, 'ESTADO', {"evento": "nova_mao"})
                time.sleep(0.05)
            continue

        h = st.get('hand')
        if not h:
            continue

        needs_me = (h.get('needs') == PLAYER_ID)
        if not needs_me:
            continue

        action = get_action(st)
        if action:
            aplicar_acao_p1(action, sock)

    sock.close()
    print("[NET] Encerrado.")


if __name__ == '__main__':
    main()