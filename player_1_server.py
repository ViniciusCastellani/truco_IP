#!/usr/bin/env python3
"""Truco Paulista — Jogador 1 (HOST)"""

import socket, json, time, os, threading, copy
import truco_game as tg

PID, OID = 'p1', 'p2'
PORT = 5000

# ── Tabela de substituição ────────────────────────────────────────────────────

CHAVE_CRIPTO = {
    "A": 29, "B": 49, "C": 58, "D": 72, "E": 13,
    "F": 28, "G": 48, "H": 57, "I": 71, "J": 12,
    "K": 27, "L": 47, "M": 56, "N": 70, "O": 11,
    "P": 26, "Q": 46, "R": 55, "S": 69, "T": 10,
    "U": 25, "V": 45, "W": 24, "X": 54, "Y": 68, "Z":  9,

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

    # JSON
    "{": 75, "}": 76, "[": 77, "]": 78,
    ":": 79, '"': 80, "_": 81,

    # Naipes
    "♣": 82, "♥": 83, "♠": 84, "♦": 85,
}

CHAVE_DECRIPTO = {v: k for k, v in CHAVE_CRIPTO.items()}
TAMANHO_BLOCO  = 5

# ── RSA ───────────────────────────────────────────────────────────────────────

def eh_primo(num):
    if num < 2: return False
    for i in range(2, int(num**0.5) + 1):
        if num % i == 0: return False
    return True

def gerar_primos(limite):
    return [i for i in range(2, limite) if eh_primo(i)]

def gerar_chaves_rsa():
    """Gera par de chaves RSA interativamente. Retorna (chave_publica, chave_privada)."""
    LIMITE       = 1000
    VAL_MAX_TAB  = max(CHAVE_CRIPTO.values())   # 85
    lista_primos = gerar_primos(LIMITE)
    print(f'\n  Primos disponíveis (até {LIMITE}):\n  {lista_primos}\n')

    while True:
        try:
            p = int(input('  Primeiro primo (P): '))
            q = int(input('  Segundo primo  (Q): '))
        except ValueError: print('  Digite inteiros.'); continue
        if p not in lista_primos or q not in lista_primos:
            print('  P e Q devem ser primos da lista.'); continue
        if p == q:
            print('  P e Q precisam ser diferentes.'); continue
        if p * q <= VAL_MAX_TAB:
            print(f'  P×Q = {p*q} deve ser > {VAL_MAX_TAB} (maior valor da tabela).'); continue
        break

    n        = p * q
    totiente = (p - 1) * (q - 1)
    print(f'\n  N (módulo) = {n}   totiente = {totiente}')

    candidatos_e = [x for x in gerar_primos(totiente) if x > q]
    print(f'\n  Candidatos para E (primo > Q={q}):\n  {candidatos_e[:30]}{"..." if len(candidatos_e)>30 else ""}\n')
    while True:
        try:
            e = int(input('  E: '))
            if e in candidatos_e: break
            print('  E deve estar na lista.')
        except ValueError: print('  Digite um inteiro.')

    # Calcular D: menor inteiro tal que (e * d) % totiente == 1
    d = 1
    while (e * d) % totiente != 1: d += 1

    pub  = [e, n]
    priv = [d, n]
    print(f'\n  Chave pública  [E, N] = {pub}')
    print(f'  Chave privada  [D, N] = {priv}')
    return pub, priv

# ── Chaves pré-configuradas (opcional) ──────────────────────────────────────
# Preencha os valores abaixo para pular a geração interativa de chaves.
# Deixe None para gerar as chaves ao iniciar o programa.
#
# Exemplo:
#   CHAVE_PUBLICA_P1  = [17, 143]   # [E, N]
#   CHAVE_PRIVADA_P1  = [113, 143]  # [D, N]

CHAVE_PUBLICA_P1  = None   # [E, N] — preencha ou deixe None para gerar
CHAVE_PRIVADA_P1  = None   # [D, N] — preencha ou deixe None para gerar

# Preenchidos em runtime (não edite)
_chave_pub_local   = None
_chave_priv_local  = None
_chave_pub_remota  = None   # chave pública de p2 (recebida no handshake)

def set_chave_pub_remota(pub):
    global _chave_pub_remota
    _chave_pub_remota = pub

def criptografar_rsa(msg, chave_publica):
    e, n = chave_publica
    return ''.join(f'{pow(CHAVE_CRIPTO[ch], e, n):05d}' for ch in msg)

def descriptografar_rsa(txt, chave_privada):
    d, n = chave_privada; out = []
    for i in range(0, len(txt), TAMANHO_BLOCO):
        val = pow(int(txt[i:i+TAMANHO_BLOCO]), d, n)
        out.append(CHAVE_DECRIPTO[val])
    return ''.join(out)

def pack(d):
    return criptografar_rsa(json.dumps(d, ensure_ascii=False), _chave_pub_remota).encode()

def unpack(b):
    return json.loads(descriptografar_rsa(b.decode(), _chave_priv_local))

# ── Estado compartilhado ──────────────────────────────────────────────────────

_lock = threading.Lock()
_st   = tg.new_game()
_addr = None
_ev   = threading.Event()

def get_st():
    with _lock: return copy.deepcopy(_st)

def set_st(s):
    global _st
    with _lock: _st = s
    _ev.set()

# ── Rede ──────────────────────────────────────────────────────────────────────

def send(sock, addr, data):
    try: sock.sendto(pack(data), addr)
    except Exception as e: print(f'[SEND ERR] {e}')

def bcast(sock, st, tipo='ESTADO'):
    if _addr: send(sock, _addr, {'t': tipo, 'st': st})

# ── Thread do servidor ────────────────────────────────────────────────────────

def server(sock):
    global _addr
    print(f'[NET] Aguardando p2 na porta {PORT}...')

    # ── Handshake com troca de chaves RSA ────────────────────────────────────
    # Fase 1: receber INICIO de p2 (texto puro — chaves ainda não trocadas)
    while _addr is None:
        sock.settimeout(1.0)
        try: raw, addr = sock.recvfrom(65535)
        except socket.timeout: continue
        try: d = json.loads(raw.decode())           # sem cifra ainda
        except: continue
        if d.get('t') == 'INICIO':
            _addr = addr
            print(f'[NET] p2 conectado: {addr}')
            # Fase 2: enviar chave pública de p1 (texto puro)
            sock.sendto(json.dumps({'t':'CHAVE','pub':_chave_pub_local}).encode(), addr)
            print(f'[NET] Chave pública de p1 enviada: {_chave_pub_local}')

    # Fase 3: receber chave pública de p2 (texto puro)
    print('[NET] Aguardando chave pública de p2...')
    while _chave_pub_remota is None:
        sock.settimeout(1.0)
        try: raw, addr = sock.recvfrom(65535)
        except socket.timeout: continue
        if addr != _addr: continue
        try: d = json.loads(raw.decode())
        except: continue
        if d.get('t') == 'CHAVE' and 'pub' in d:
            set_chave_pub_remota(d['pub'])
            print(f'[NET] Chave pública de p2 recebida: {_chave_pub_remota}')
            # Fase 4: confirmar handshake — agora com cifra RSA
            send(sock, _addr, {'t':'INICIO','ok':True})
            print('[NET] Handshake concluído — comunicação cifrada iniciada.')

    st = tg.start_hand(get_st())
    set_st(st); bcast(sock, st)
    print(f'[JOGO] Partida iniciada. Vira: {tg.label(st["hand"]["vira"])}')

    while True:
        sock.settimeout(0.2)
        try: raw, addr = sock.recvfrom(65535)
        except socket.timeout: continue
        if addr != _addr: continue
        try: d = unpack(raw)
        except: continue
        if d.get('t') != 'ACAO': continue

        st = get_st(); h = st.get('hand') or {}; a = d.get('a')

        if   a=='play'       and h.get('needs')==OID: st,_ = tg.play_card(st, OID, d['idx'])
        elif a=='truco':                               st,_ = tg.call_truco(st, OID, d['nivel'])
        elif a=='resp_truco':                          st,_ = tg.respond_truco(st, OID, d['aceitar'])
        elif a=='mao11':                               st,_ = tg.mao11_decide(st, OID, d['jogar'])
        else: continue

        set_st(st)
        bcast(sock, st, 'FIM' if st['phase']=='game_over' else 'ESTADO')
        if st['phase'] == 'game_over': break

    print('[NET] Thread servidor encerrada.')

# ── Display ───────────────────────────────────────────────────────────────────

def clr(): os.system('clear' if os.name != 'nt' else 'cls')
def card_s(c): return f'[{tg.label(c)}]' if c else '[ - ]'

def draw(st):
    clr(); sc = st['scores']; h = st.get('hand')
    sep = '─'*50
    print(sep)
    print(f'  TRUCO PAULISTA [HOST/p1]   Placar: p1={sc["p1"]}  p2={sc["p2"]}')
    print(sep)
    if not h: print(f'\n  {st.get("message","")}'); return
    print(f'  Vira: {tg.label(h["vira"])}   Manilha: {tg.manilha_str(h["vira"])}')
    if h['rodadas']:
        print('\n  Rodadas:')
        for i,r in enumerate(h['rodadas'],1):
            w = 'você' if r['winner']==PID else ('adv' if r['winner']==OID else 'empate')
            print(f'    {i}. {tg.label(r[PID])} vs {tg.label(r[OID])} → {w}')
    print(f'\n  Mesa:  Adv: {card_s(h["table"].get(OID))}   Você: {card_s(h["table"].get(PID))}')
    slabel = h['truco_level'].upper() if h.get('truco_level') else 'normal'
    print(f'  Aposta: {slabel} ({h["stake"]}pt)')
    if st['phase']=='truco' and h.get('truco_caller')==OID:
        print(f'  !!! {OID} pediu {h["truco_pending"].upper()}! ({tg.STAKES[h["truco_pending"]]}pts) !!!')
    cards = h['cards'].get(PID, [])
    print('\n  ' + ('  '.join(f'[{i+1}]{tg.label(c)}' for i,c in enumerate(cards)) or '(nenhuma)'))
    print(f'  {OID} tem {len(h["cards"].get(OID,[]))} carta(s).')
    print(f'\n  >> {st.get("message","")}')

# ── Input ─────────────────────────────────────────────────────────────────────

def get_action(st):
    h = st['hand']; phase = st['phase']
    if phase=='mao11' and h.get('needs')==PID:
        print('\n  Mão de Onze: [j] Jogar  [f] Fugir')
        while True:
            r = input('  > ').strip().lower()
            if r=='j': return ('mao11', True)
            if r=='f': return ('mao11', False)
    if phase=='truco' and h.get('needs')==PID:
        nxt = tg.next_truco_level(h)
        print('\n  [a] Aceitar  [c] Correr' + (f'  [r] → {nxt.upper()}({tg.STAKES[nxt]}pt)' if nxt else ''))
        while True:
            r = input('  > ').strip().lower()
            if r=='a': return ('respond', True)
            if r=='c': return ('respond', False)
            if r=='r' and nxt: return ('call_truco', nxt)
    if phase=='playing' and h.get('needs')==PID:
        cards = h['cards'][PID]; n = len(cards); nxt = tg.next_truco_level(h)
        print(f'\n  Jogar:[1-{n}]' + (f'  Truco:[t]→{nxt.upper()}' if nxt else ''))
        while True:
            r = input('  > ').strip().lower()
            if r.isdigit():
                idx = int(r)-1
                if 0 <= idx < n: return ('play', idx)
            elif r=='t' and nxt: return ('call_truco', nxt)
    return None

# ── Aplica ação do P1 ─────────────────────────────────────────────────────────

def apply_p1(action, sock):
    st = get_st(); k = action[0]
    if   k=='play':        st,_ = tg.play_card(st, PID, action[1])
    elif k=='call_truco':  st,_ = tg.call_truco(st, PID, action[1])
    elif k=='respond':     st,_ = tg.respond_truco(st, PID, action[1])
    elif k=='mao11':       st,_ = tg.mao11_decide(st, PID, action[1])
    set_st(st)
    bcast(sock, st, 'FIM' if st['phase']=='game_over' else 'ESTADO')

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global _chave_pub_local, _chave_priv_local
    clr()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
    except: ip = "127.0.0.1"
    print(f'  IP: {ip}   Porta: {PORT}\n  Passe esse IP para o Jogador 2.\n')

    if CHAVE_PUBLICA_P1 and CHAVE_PRIVADA_P1:
        _chave_pub_local  = CHAVE_PUBLICA_P1
        _chave_priv_local = CHAVE_PRIVADA_P1
        print(f'  Chave pública  [E, N] = {_chave_pub_local}')
        print(f'  Chave privada  [D, N] = {_chave_priv_local}')
    else:
        print('  === GERAÇÃO DAS CHAVES RSA (Jogador 1) ===')
        _chave_pub_local, _chave_priv_local = gerar_chaves_rsa()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', PORT))
    threading.Thread(target=server, args=(sock,), daemon=True).start()

    while _addr is None: time.sleep(0.2)
    while _chave_pub_remota is None: time.sleep(0.2)   # aguarda handshake completo
    while get_st().get('phase') in ('waiting','ready',None): time.sleep(0.2)

    while True:
        _ev.wait(0.5); _ev.clear()
        st = get_st(); phase = st.get('phase','')
        draw(st)

        if phase == 'game_over':
            w = st.get('winner')
            print(f'\n  FIM! {"VOCÊ VENCEU! 🎉" if w==PID else "Você perdeu."}')
            print(f'  Placar final: p1 {st["scores"]["p1"]} × {st["scores"]["p2"]} p2')
            break

        if phase == 'hand_over':
            input('\n  [Enter] próxima mão...')
            st = tg.start_hand(get_st()); set_st(st)
            bcast(sock, st); continue

        h = st.get('hand')
        if not h or h.get('needs') != PID: continue

        a = get_action(st)
        if a: apply_p1(a, sock)

    sock.close()

if __name__ == '__main__': main()