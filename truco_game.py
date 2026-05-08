import random, copy

SUITS = ['P', 'C', 'E', 'O']
SYM   = {'P': '♣', 'C': '♥', 'E': '♠', 'O': '♦'}
RANKS = ['4', '5', '6', '7', 'Q', 'J', 'K', 'A', '2', '3']

# Ordem das cartas do menor para o maior (excluindo manilhas)
RANK_ORDER = ['4', '5', '6', '7', 'Q', 'J', 'K', 'A', '2', '3']

# Naipes das manilhas do mais fraco ao mais forte: ♦ < ♠ < ♥ < ♣
SUIT_MANILHA = ['O', 'E', 'C', 'P']

LEVELS  = [None, 'truco', 'seis', 'nove', 'doze']
STAKES  = {None:1, 'truco':3, 'seis':6, 'nove':9, 'doze':12}
RUN_PTS = {'truco':1, 'seis':3, 'nove':6, 'doze':9}


def manilha_rank(vira_r):
    """Retorna o rank que é manilha dado o rank do vira."""
    return RANK_ORDER[(RANK_ORDER.index(vira_r) + 1) % 10]


def rank(c, vira):
    """Força da carta. Manilhas valem 11-14, regulares 1-10."""
    m = manilha_rank(vira['r'])
    if c['r'] == m:
        return 11 + SUIT_MANILHA.index(c['s'])   # ♦=11, ♠=12, ♥=13, ♣=14
    return RANK_ORDER.index(c['r']) + 1           # 1-10


def manilha_str(vira):
    """Retorna string legível das manilhas em ordem, ex: 'A♣ > A♥ > A♠ > A♦'"""
    m = manilha_rank(vira['r'])
    return ' > '.join(m + SYM[s] for s in reversed(SUIT_MANILHA))


def label(c):  return c['r'] + SYM[c['s']]
def opp(p):    return 'p2' if p == 'p1' else 'p1'


def deck():
    d = [{'r': r, 's': s} for s in SUITS for r in RANKS]
    random.shuffle(d)
    return d


# ── State constructors ────────────────────────────────────────────────────────

def new_game():
    return {
        'scores':  {'p1': 0, 'p2': 0},
        'phase':   'waiting',       # waiting → ready → playing / truco / mao11 / hand_over / game_over
        'hand':    None,
        'dealer':  'p1',
        'winner':  None,
        'message': 'Aguardando Jogador 2...',
    }


def start_hand(st):
    st = copy.deepcopy(st)
    d     = deck()
    first = opp(st['dealer'])
    st['dealer'] = opp(st['dealer'])   # alternate dealer each hand

    hand = {
        'cards':         {'p1': d[:3], 'p2': d[3:6]},
        'vira':          d[6],          # carta virada — define a manilha
        'table':         {'p1': None,  'p2': None},
        'rodadas':       [],
        'turn':          first,
        'needs':         first,
        'stake':         1,
        'truco_level':   None,
        'truco_pending': None,
        'truco_caller':  None,
        'winner':        None,
        'mao11':         None,
    }
    st['hand']    = hand
    st['phase']   = 'playing'
    st['message'] = f'Nova mão! {first} começa.'

    sc = st['scores']
    if sc['p1'] == 11 or sc['p2'] == 11:
        st['phase']  = 'mao11'
        hand['mao11'] = {
            'p1': None if sc['p1'] == 11 else 'play',
            'p2': None if sc['p2'] == 11 else 'play',
        }
        hand['stake'] = 3
        hand['needs'] = 'p1' if sc['p1'] == 11 else 'p2'
        st['message'] = 'Mão de onze! Decida se joga ou foge.'
    return st


# ── Actions ───────────────────────────────────────────────────────────────────

def play_card(st, player, idx):
    st = copy.deepcopy(st)
    h  = st['hand']
    if st['phase'] != 'playing' or h['needs'] != player:
        return st, 'Não é sua vez.'
    cards = h['cards'][player]
    if not (0 <= idx < len(cards)):
        return st, 'Carta inválida.'

    card = cards.pop(idx)
    h['table'][player] = card
    o = opp(player)

    if h['table'][o] is None:
        h['needs'] = o
        msg = f'{player} jogou {label(card)}. Vez de {o}.'
        st['message'] = msg
        return st, msg

    return _resolve(st)


def call_truco(st, player, level):
    st = copy.deepcopy(st)
    h  = st['hand']

    if st['phase'] == 'playing':
        if h['needs'] != player:
            return st, 'Não é sua vez.'
    elif st['phase'] == 'truco':
        if h['truco_caller'] == player or h['needs'] != player:
            return st, 'Não pode pedir truco agora.'
    else:
        return st, 'Não pode pedir truco agora.'

    base     = h['truco_pending'] or h['truco_level']
    base_idx = LEVELS.index(base)
    lvl_idx  = LEVELS.index(level)
    if lvl_idx != base_idx + 1:
        nxt = LEVELS[base_idx + 1] if base_idx + 1 < len(LEVELS) else None
        return st, f"Próximo nível: {nxt}." if nxt else 'Já está no máximo (doze).'

    h['truco_pending'] = level
    h['truco_caller']  = player
    h['needs']         = opp(player)
    st['phase']        = 'truco'
    msg = f'{player} pediu {level.upper()}! Vale {STAKES[level]} pts se aceito.'
    st['message'] = msg
    return st, msg


def respond_truco(st, player, accept):
    st = copy.deepcopy(st)
    h  = st['hand']
    if st['phase'] != 'truco' or h['needs'] != player:
        return st, 'Não é hora de responder.'

    caller  = h['truco_caller']
    pending = h['truco_pending']

    if accept:
        h['truco_level']   = pending
        h['stake']         = STAKES[pending]
        h['truco_pending'] = None
        h['truco_caller']  = None
        h['needs']         = player
        h['turn']          = player
        st['phase']        = 'playing'
        msg = f'{player} aceitou! Jogo vale {h["stake"]} pts.'
    else:
        pts = RUN_PTS[pending]
        st['scores'][caller] += pts
        h['winner']  = caller
        st['phase']  = 'hand_over'
        st = _check_win(st)
        msg = f'{player} correu! {caller} ganha {pts} pt(s).'

    st['message'] = msg
    return st, msg


def mao11_decide(st, player, play):
    st = copy.deepcopy(st)
    h  = st['hand']
    if st['phase'] != 'mao11' or h['needs'] != player:
        return st, 'Não é sua vez de decidir.'

    d = h['mao11']
    d[player] = 'play' if play else 'fold'
    o = opp(player)

    if d[o] is None:
        h['needs'] = o
        msg = f'{player} decidiu. Aguardando {o}...'
        st['message'] = msg
        return st, msg

    p1d, p2d = d['p1'], d['p2']
    if p1d == 'fold' and p2d == 'fold':
        st['phase']  = 'hand_over'
        msg = 'Ambos fugiram. Sem pontuação.'
    elif p1d == 'fold':
        st['scores']['p2'] += 1
        h['winner']  = 'p2'
        st['phase']  = 'hand_over'
        st = _check_win(st)
        msg = 'p1 fugiu da mão de onze. p2 ganha 1 pt.'
    elif p2d == 'fold':
        st['scores']['p1'] += 1
        h['winner']  = 'p1'
        st['phase']  = 'hand_over'
        st = _check_win(st)
        msg = 'p2 fugiu da mão de onze. p1 ganha 1 pt.'
    else:
        st['phase'] = 'playing'
        h['needs']  = h['turn']
        msg = 'Ambos jogam! Vale 3 pts.'

    st['message'] = msg
    return st, msg


# ── Internals ─────────────────────────────────────────────────────────────────

def _resolve(st):
    h       = st['hand']
    c1, c2  = h['table']['p1'], h['table']['p2']
    r1, r2  = rank(c1, h['vira']), rank(c2, h['vira'])
    winner  = 'p1' if r1 > r2 else ('p2' if r2 > r1 else 'tie')

    h['rodadas'].append({'p1': c1, 'p2': c2, 'winner': winner})
    h['table'] = {'p1': None, 'p2': None}

    hw     = _hand_winner(h)
    result = f'Rodada {len(h["rodadas"])}: {label(c1)} vs {label(c2)} → {winner}'

    if hw:
        h['winner'] = hw
        if hw != 'tie':
            st['scores'][hw] += h['stake']
        st['phase'] = 'hand_over'
        st = _check_win(st)
        suffix = f' | {hw} venceu a mão! +{h["stake"]} pt(s).' if hw != 'tie' else ' | Empate geral! Sem pontos.'
    else:
        next_t      = winner if winner != 'tie' else h['turn']
        h['turn']   = next_t
        h['needs']  = next_t
        suffix      = f' | Vez de {next_t}.'

    st['message'] = result + suffix
    return st, st['message']


def _hand_winner(h):
    rs   = h['rodadas']
    n    = len(rs)
    wins = {'p1': 0, 'p2': 0, 'tie': 0}
    for r in rs:
        wins[r['winner']] += 1

    if wins['p1'] >= 2: return 'p1'
    if wins['p2'] >= 2: return 'p2'

    if n >= 2:
        if wins['p1'] == 1 and wins['tie'] >= 1: return 'p1'
        if wins['p2'] == 1 and wins['tie'] >= 1: return 'p2'

    if n == 3:
        if wins['p1'] > wins['p2']: return 'p1'
        if wins['p2'] > wins['p1']: return 'p2'
        for r in rs:
            if r['winner'] != 'tie': return r['winner']
        return 'tie'

    return None


def _check_win(st):
    for p in ('p1', 'p2'):
        if st['scores'][p] >= 12:
            st['phase']  = 'game_over'
            st['winner'] = p
    return st


def next_truco_level(h):
    base = h['truco_pending'] or h['truco_level']
    idx  = LEVELS.index(base)
    nxt  = idx + 1
    return LEVELS[nxt] if nxt < len(LEVELS) else None
