#!/usr/bin/env python3
"""
Truco Paulista — Jogador 2 (CLIENT)
"""

import socket, json, time, os, threading
import truco_game as tg

PLAYER_ID   = 'p2'
OPPONENT_ID = 'p1'

HOST_P1   = None
HOST_PORT = 5000

# ══════════════════════════════════════════════════════════════════════════════
#  RSA  (idêntico ao host)
# ══════════════════════════════════════════════════════════════════════════════

CHAVE_PUBLICA  = [29, 247]
CHAVE_PRIVADA  = [149, 247]

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
#  REDE
# ══════════════════════════════════════════════════════════════════════════════

def send_message(sock, addr, dados: dict):
    try:
        sock.sendto(_empacotar(dados), addr)
    except Exception as ex:
        print(f"[ERRO REDE] {ex}")


# ══════════════════════════════════════════════════════════════════════════════
#  THREAD DE RECEPÇÃO EM BACKGROUND
#
#  FIX: O cliente original só recebia mensagens em momentos específicos do
#  loop, descartando tudo que chegasse enquanto o jogador estava no input().
#  Esta thread recebe continuamente e atualiza _estado_bg, que o loop
#  principal lê a qualquer momento.
# ══════════════════════════════════════════════════════════════════════════════

_bg_lock   = threading.Lock()
_estado_bg = None          # último estado recebido da rede
_estado_ev = threading.Event()


def _set_estado_bg(st):
    global _estado_bg
    with _bg_lock:
        _estado_bg = st
    _estado_ev.set()


def _get_estado_bg():
    with _bg_lock:
        return _estado_bg


def _thread_recv(sock):
    """Recebe continuamente mensagens do host e atualiza o estado global."""
    while True:
        sock.settimeout(0.3)
        try:
            raw, _ = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError:
            # Socket fechado — encerra thread
            break
        except Exception as ex:
            print(f"[RECV BG] {ex}")
            continue

        try:
            dados = _desempacotar(raw)
        except Exception as ex:
            print(f"[CRIPTO BG] {ex}")
            continue

        if dados.get('_phase') is not None:
            _set_estado_bg(msg_para_estado(dados))


# ══════════════════════════════════════════════════════════════════════════════
#  CONVERSÃO MSG ↔ ESTADO
# ══════════════════════════════════════════════════════════════════════════════

def msg_para_estado(dados: dict) -> dict:
    return {
        'scores':  dados.get('pontos', {'p1': 0, 'p2': 0}),
        'phase':   dados.get('_phase', 'playing'),
        'hand':    dados.get('_hand'),
        'dealer':  dados.get('_dealer', 'p1'),
        'winner':  dados.get('_winner'),
        'message': dados.get('_message', ''),
    }

def acao_para_msg(action) -> dict:
    kind   = action[0]
    extras = {}
    if kind == 'play':
        extras = {'acao': 'JOGAR_CARTA', 'idx': action[1]}
    elif kind == 'call_truco':
        extras = {'acao': 'TRUCO', 'nivel': action[1]}
    elif kind == 'respond':
        extras = {'acao': 'RESPONDER_TRUCO', 'aceitar': action[1]}
    elif kind == 'mao11':
        extras = {'acao': 'MAO11', 'jogar': action[1]}
    return {
        "tipo_msg":     "JOGADA",
        "vez":          PLAYER_ID,
        "vira":         None,
        "valor_rodada": 1,
        "mesa":         {"p1": None, "p2": None},
        "pontos":       {"p1": 0, "p2": 0},
        "qtd_cartas":   {"p1": 0, "p2": 0},
        "dados_extras": extras,
    }


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
    print(f'  TRUCO PAULISTA  [CLIENT/p2]   Você: {you}')
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
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    global HOST_P1
    clr()
    print("=" * 52)
    print("  TRUCO PAULISTA — Jogador 2 [CLIENT]")
    print("=" * 52)

    if HOST_P1 is None:
        HOST_P1 = input("\n  IP do Jogador 1 (host): ").strip()
        if not HOST_P1:
            HOST_P1 = '127.0.0.1'

    srv = (HOST_P1, HOST_PORT)
    print(f"\n[NET] Conectando ao host {HOST_P1}:{HOST_PORT}...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # ── Conectar ao host ─────────────────────────────────────────────────────
    conn_msg = {
        "tipo_msg": "INICIO", "vez": PLAYER_ID,
        "vira": None, "valor_rodada": 1,
        "mesa": {"p1": None, "p2": None},
        "pontos": {"p1": 0, "p2": 0},
        "qtd_cartas": {"p1": 0, "p2": 0},
        "dados_extras": {},
    }

    conectado = False
    tentativa = 0
    while not conectado:
        tentativa += 1
        print(f"[NET] Tentativa {tentativa} — enviando INICIO...")
        send_message(sock, srv, conn_msg)
        sock.settimeout(2.0)
        try:
            raw, _ = sock.recvfrom(65535)
            resp   = _desempacotar(raw)
        except socket.timeout:
            resp = None
        except Exception as ex:
            print(f"[ERRO] {ex}")
            resp = None

        if resp is None:
            print(f"[NET] Sem resposta do host. Verifique:")
            print(f"      • IP correto? ({HOST_P1}:{HOST_PORT})")
            print(f"      • Host está rodando player_1_host.py?")
            print(f"      • Firewall permite UDP porta {HOST_PORT}?")
            time.sleep(1)
            continue

        if resp.get('tipo_msg') == 'INICIO':
            print(f"[JOGO] Conectado! {resp.get('_message', '')}")
            conectado = True
        else:
            print(f"[NET] Resposta inesperada: tipo={resp.get('tipo_msg')} — tentando novamente.")
            time.sleep(1)

    # ── Inicia thread de recepção em background ──────────────────────────────
    # FIX: garante que mensagens nunca sejam descartadas enquanto o jogador
    # está digitando. A thread atualiza _estado_bg continuamente.
    recv_thread = threading.Thread(target=_thread_recv, args=(sock,), daemon=True)
    recv_thread.start()

    # ── Aguardar início da partida ───────────────────────────────────────────
    print("[JOGO] Aguardando partida iniciar...\n")
    while True:
        _estado_ev.wait(timeout=1.0)
        _estado_ev.clear()
        st = _get_estado_bg()
        if st and st.get('phase') not in ('waiting', 'ready', None):
            estado = st
            print("[JOGO] Partida iniciada!")
            break

    # ── Loop principal ───────────────────────────────────────────────────────
    while True:
        # Sempre lê o estado mais recente recebido
        novo = _get_estado_bg()
        if novo:
            estado = novo

        if estado is None:
            time.sleep(0.2)
            continue

        draw(estado)
        phase = estado.get('phase', '')

        if phase == 'game_over':
            w = estado.get('winner')
            print(f'\n  JOGO ENCERRADO! {"VOCÊ VENCEU! 🎉" if w == PLAYER_ID else "Você perdeu."}')
            print(f'  Placar final: p1 {estado["scores"]["p1"]} × {estado["scores"]["p2"]} p2')
            break

        if phase == 'hand_over':
            # FIX: P2 não chama start_hand nem envia PROXIMA_MAO.
            # Apenas aguarda P1 enviar o novo estado (nova mão) passivamente.
            # Isso elimina o double-shuffle que causava dessincronia.
            print('\n  Aguardando próxima mão...')
            while True:
                _estado_ev.wait(timeout=1.0)
                _estado_ev.clear()
                novo = _get_estado_bg()
                if novo and novo.get('phase') in ('playing', 'mao11'):
                    estado = novo
                    break
            continue

        h = estado.get('hand')
        if not h:
            time.sleep(0.2)
            continue

        needs_me = (h.get('needs') == PLAYER_ID)
        if not needs_me:
            # Não é minha vez — aguarda atualização da thread de background
            _estado_ev.wait(timeout=1.0)
            _estado_ev.clear()
            continue

        # ── Minha vez ────────────────────────────────────────────────────────
        action = get_action(estado)
        if action:
            msg = acao_para_msg(action)
            send_message(sock, srv, msg)
            # Aguarda confirmação do host (estado atualizado pela thread bg)
            deadline = time.time() + 5.0
            phase_antes = estado.get('phase')
            needs_antes = h.get('needs')
            while time.time() < deadline:
                _estado_ev.wait(timeout=0.3)
                _estado_ev.clear()
                novo = _get_estado_bg()
                if novo:
                    # Sai do loop se o estado mudou (jogada processada)
                    h_novo = novo.get('hand') or {}
                    if (novo.get('phase') != phase_antes or
                            h_novo.get('needs') != needs_antes):
                        estado = novo
                        break

    sock.close()
    print("[NET] Encerrado.")


if __name__ == '__main__':
    main()