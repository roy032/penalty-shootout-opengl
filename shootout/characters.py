"""The character roster: legends, icons, current stars (men and women) and a
few fantasy originals, with their looks, personalities, signature moves,
celebrations and aura.

Everything about a real player here is a game caricature built from public
moments (a famous celebration, a famous penalty). Names live only in this
file, so a published build can rename them in one place.

Ratings run 0..1 like squad ratings. Keepers carry small reach and speed
bonuses on top of the difficulty table; their kicking ratings matter only if
the shootout goes all the way round to them.
"""

import json
import os
import random
import zlib

from .squad import Player

# ------------------------------------------------------------------ looks
SKINS = [(0.96, 0.8, 0.66), (0.9, 0.72, 0.56), (0.78, 0.58, 0.42), (0.6, 0.42, 0.28),
         (0.44, 0.3, 0.2), (0.32, 0.21, 0.14)]
HAIR_COLOURS = {
    'black': (0.08, 0.06, 0.05), 'brown': (0.3, 0.18, 0.1), 'blond': (0.86, 0.72, 0.42),
    'red': (0.62, 0.26, 0.1), 'grey': (0.62, 0.62, 0.62), 'bleach': (0.93, 0.88, 0.62),
    'purple': (0.55, 0.2, 0.75), 'white': (0.95, 0.95, 0.97), 'pink': (0.95, 0.45, 0.7),
}
HAIRS = ['short', 'buzz', 'bald', 'quiff', 'long', 'ponytail', 'bun', 'afro', 'curly', 'mohawk', 'braids',
         'manbun', 'r9']
BEARDS = [None, 'stubble', 'full', 'goatee']
BOOTS = {'black': (0.08, 0.08, 0.08), 'white': (0.92, 0.92, 0.92), 'gold': (0.95, 0.75, 0.2),
         'pink': (0.95, 0.4, 0.65), 'orange': (0.95, 0.5, 0.1), 'cyan': (0.2, 0.8, 0.9)}


def look(skin=1, hair='short', hc='brown', beard=None, h=1.0, w=1.0, **extra):
    d = dict(skin=skin, hair=hair, hc=hc, beard=beard, h=h, w=w)
    d.update(extra)
    return d


def look_colours(lk):
    """Resolve a look's names into colours for the renderer."""
    return dict(skin=SKINS[max(0, min(len(SKINS) - 1, int(lk.get('skin', 1))))],
                hair=HAIR_COLOURS.get(lk.get('hc', 'brown'), HAIR_COLOURS['brown']),
                boots=BOOTS.get(lk.get('boots', 'black'), BOOTS['black']))


def club_look(seed, keeper=False):
    """A stable random look for a club player, from his name and number."""
    r = random.Random(seed)
    hair = r.choice(['short', 'short', 'buzz', 'buzz', 'bald', 'quiff', 'curly', 'afro', 'long', 'manbun',
                     'mohawk', 'braids'])
    hc = r.choice(['black', 'black', 'brown', 'brown', 'blond', 'red', 'bleach'])
    lk = look(r.randrange(len(SKINS)), hair, hc, r.choice(BEARDS + [None, None]), round(r.uniform(0.94, 1.07), 2),
              round(r.uniform(0.93, 1.08), 2))
    if r.random() < 0.15:
        lk['socks'] = 'down'
    if r.random() < 0.1:
        lk['headband'] = True
    lk['boots'] = r.choice(['black', 'black', 'white', 'pink', 'orange', 'cyan', 'gold'])
    if keeper:
        lk['gloves'] = r.choice(['white', 'lime', 'orange', 'black'])
        lk['sleeves'] = 'long'
    return lk


GLOVE_COLOURS = {'white': (0.95, 0.95, 0.95), 'lime': (0.7, 0.95, 0.2), 'orange': (0.98, 0.55, 0.1),
                 'black': (0.12, 0.12, 0.14), 'pink': (0.95, 0.45, 0.7), 'gold': (0.95, 0.75, 0.2)}

# ------------------------------------------------------------ personalities
TAKER_PERSONAS = {
    'ice': ('Ice Cold', 'Away-end whistles do nothing; the antics barely land. Always placed.'),
    'showboat': ('Showboat', 'Panenkas and stutters, and the biggest celebrations in the game.'),
    'hothead': ('Hothead', "Drives it hard. The keeper's antics hit twice as hard."),
    'thinker': ('Thinker', 'Long ritual, disguised run-up: very hard to read.'),
    'kid': ('Nervous Kid', 'Great ratings, but the fifth kick and must-score kicks weigh heavy.'),
    'clutch': ('Big Game', 'Better when it matters: steadier on must-score and winning kicks.'),
    'steady': ('Steady', 'No drama: does what the ratings say.'),
}
KEEPER_PERSONAS = {
    'dancer': ('Dancer', 'Wobbles and waves on the line to rattle the taker.'),
    'wall': ('Wall', 'Stays big and goes late: more reach, fewer guesses.'),
    'gambler': ('Gambler', 'Goes early and guesses. More saves, more VAR retakes.'),
    'reader': ('Reader', 'Studies the taker: reads the run-up and remembers your habits.'),
    'showman': ('Showman', 'Points, takes the ball off you, celebrates every save.'),
    'sweeper': ('Sweeper', 'Quick off the line and strong on rebounds.'),
    'cat': ('Cat', 'Explosive dives and fingertip stretches.'),
}
SIGNATURES = {
    'hop': ('The hop', 'A skip just before contact that freezes the keeper. Quicker than a stutter.'),
    'stopstart': ('Paradinha', 'Stops dead in the run-up and waits for the keeper to move.'),
    'stance': ('Power stance', 'Legs wide, deep breath, then the run-up. Settles the nerves.'),
    'panenka': ('Panenka', 'Chips it down the middle.'),
    'rocket': ('Rocket', 'Smashes it high: the keeper has no time.'),
    'curl': ('Curler', 'Bends it into the side netting.'),
    'low': ('Low corner', 'Side-foot, low, inside the post. Never misses low.'),
    'knuckle': ('Knuckleball', 'No spin: it wobbles in the air.'),
    'disguise': ('Poker face', 'A run-up that gives nothing away.'),
    'notes': ('The notes', 'Notes on every taker in a sock or on the bottle. Never wrong.'),
    'star': ('Star jump', 'Spreads wide and big when he stays in the middle.'),
    'legs': ('Spaghetti legs', 'Wobbles on the line before the kick.'),
    'point': ('The point', 'Points at a corner: "I know where you are going".'),
    'early': ('Off the line', 'Charges off the line at the taker.'),
}
SIG_SHOT = {'hop': 'stutter', 'stopstart': 'stutter', 'panenka': 'chip', 'rocket': 'driven', 'curl': 'curl',
            'low': 'placed', 'knuckle': 'knuckle'}
CELEBRATIONS = {
    'knee slide': 'Knee slide', 'aeroplane': 'Aeroplane', 'shush': 'Shush the crowd', 'badge kiss': 'Badge kiss',
    'siuu': 'The jump-spin and land', 'meditate': 'Cross-legged and zen', 'cold': 'Shivering: so cold',
    'crossed arms': 'Arms folded, unbothered', 'samba': 'Samba by the corner flag', 'arms wide': 'Arms wide',
    'pose': 'The pose: arms out, chin up', 'tea': 'Sipping the tea', 'shirt swing': 'Shirt off, swung round',
    'backflip': 'Backflip', 'think': 'Finger on the temple', 'shaka': 'Shaka and a grin',
    'shirt show': 'Holds the shirt up to the fans', 'lean': 'Leaning on the post', 'collar': 'Collar up, stands still',
    'scream': 'The scream run', 'punch': 'Punches the air', 'heart': 'Hands make a heart',
    'number': 'Shows a number with his fingers', 'point sky': 'Points to the sky', 'wag': 'Finger wag',
    'selfie': 'Takes a selfie with the fans', 'roar': 'Roars', 'flex': 'Stands still and flexes',
    'boot kiss': 'Kisses the boot', 'levitate': 'Floats off the ground', 'wings': 'Wings of fire',
    'spell': 'Casts a spell', 'bolt': 'Lightning bolt pose', 'stroll': 'Strolls away, unmoved',
}
SAVE_CELEBRATIONS = {
    'dance': 'Dances on the line', 'scorpion': 'Scorpion kick', 'roar': 'Roars at the crowd',
    'star': 'Star jump', 'shimmy': 'Shimmies at the taker', 'shush': 'Shushes the crowd', 'wag': 'Finger wag',
    'float': 'Floats on the line',
}
MANNERISMS = {'kiss': 'kisses the ball', 'wipe': 'wipes his face on his shirt', 'sky': 'stares at the sky',
              'breath': 'takes a huge breath', 'bar': 'slaps the crossbar', 'scuff': 'scuffs the line',
              'clap': 'claps the gloves'}
ERAS = {'legend': 'Legend', 'icon': 'Cult icon', 'current': 'Current star', 'fantasy': 'Fantasy',
        'custom': 'Your player', 'mod': 'Mod'}
GLOWS = {'legend': (1.0, 0.82, 0.3), 'icon': (1.0, 0.55, 0.25), 'current': (0.55, 0.85, 1.0),
         'fantasy': (0.75, 0.4, 1.0), 'custom': (0.4, 1.0, 0.6), 'mod': (0.9, 0.9, 0.9)}

ROSTER = []


def _c(key, name, full, number, era, women, role, foot, ratings, persona, sig, cel, aura, lk, tag, **kw):
    ch = dict(key=key, name=name, full=full, number=number, era=era, women=women, role=role, foot=foot,
              composure=ratings[0], power=ratings[1], placement=ratings[2], persona=persona, signature=sig,
              celebration=cel, aura=aura, look=lk, tag=tag, natural=kw.pop('natural', 0.6),
              low=kw.pop('low', 0.5), reach=kw.pop('reach', 0.0), speed=kw.pop('speed', 0.0),
              unlock=kw.pop('unlock', None), glow=kw.pop('glow', None), mannerism=kw.pop('mannerism', None),
              lines=kw.pop('lines', []), kit=kw.pop('kit', None))
    assert not kw, kw
    ROSTER.append(ch)
    return ch


K, KP = 'kick', 'keep'
# --- Current stars: men
_c('messi', 'MESSI', 'Lionel Messi', 10, 'current', False, K, 'L', (0.86, 0.72, 0.95), 'steady', 'low',
   'shirt show', 1.0, look(2, 'short', 'brown', 'full', 0.94, 0.95, boots='gold'), 'The GOAT', low=0.75,
   natural=0.55, mannerism='breath', lines=['The GOAT is walking up.', 'Eight Ballon d\'Ors of aura on that spot.'])
_c('ronaldo', 'RONALDO', 'Cristiano Ronaldo', 7, 'current', False, K, 'R', (0.9, 0.95, 0.85), 'clutch', 'stance',
   'siuu', 0.98, look(1, 'quiff', 'black', None, 1.04, 1.02, boots='white'), 'SIUUU', low=0.35, mannerism='breath',
   lines=['The power stance. Here comes the stutter-step and the strike.', 'The whole stadium is ready to shout SIU.'])
_c('haaland', 'HAALAND', 'Erling Haaland', 9, 'current', False, K, 'L', (0.84, 0.97, 0.78), 'ice', 'rocket',
   'meditate', 0.9, look(0, 'manbun', 'blond', None, 1.1, 1.06, boots='white'), 'The Terminator', low=0.4,
   lines=['A robot in boots.', 'He does not do nerves.'])
_c('mbappe', 'MBAPPE', 'Kylian Mbappe', 10, 'current', False, K, 'R', (0.86, 0.94, 0.86), 'clutch', 'rocket',
   'crossed arms', 0.92, look(3, 'bald', 'black', None, 1.0, 1.0, boots='orange'), 'Arms folded', low=0.45,
   lines=['Hat-trick in a World Cup final. A penalty holds no fear.'])
_c('neymar', 'NEYMAR', 'Neymar Jr', 10, 'current', False, K, 'R', (0.78, 0.8, 0.9), 'showboat', 'stopstart', 'heart',
   0.82, look(2, 'quiff', 'bleach', 'stubble', 0.96, 0.95, boots='pink'), 'The stop-start', mannerism='kiss',
   lines=['Watch the run-up. He will stop. He always stops.'])
_c('bellingham', 'BELLINGHAM', 'Jude Bellingham', 5, 'current', False, K, 'R', (0.85, 0.82, 0.84), 'showboat',
   'curl', 'arms wide', 0.88, look(4, 'buzz', 'black', None, 1.04, 1.0, headband=False, boots='white'), 'Hey Jude',
   lines=['Arms out wide is coming if this goes in.'])
_c('palmer', 'PALMER', 'Cole Palmer', 10, 'current', False, K, 'L', (0.97, 0.78, 0.9), 'ice', 'low', 'cold', 0.85,
   look(1, 'short', 'red', 'stubble', 1.03, 0.94, boots='black'), 'Cold', low=0.6, mannerism='breath',
   lines=['Cold Palmer. Has he ever missed one?', 'Ice in the veins. Literally shivering.'])
_c('vinicius', 'VINICIUS', 'Vinicius Jr', 7, 'current', False, K, 'R', (0.72, 0.86, 0.8), 'hothead', 'curl', 'samba',
   0.82, look(4, 'curly', 'black', None, 1.0, 0.95, boots='white'), 'Samba', lines=['If it goes in, he is dancing.'])
_c('yamal', 'YAMAL', 'Lamine Yamal', 10, 'current', False, K, 'L', (0.74, 0.8, 0.9), 'showboat', 'curl', 'number',
   0.8, look(3, 'curly', 'black', None, 1.0, 0.92, boots='pink'), '304', lines=['The kid from 304.'])
_c('saka', 'SAKA', 'Bukayo Saka', 7, 'current', False, K, 'L', (0.8, 0.78, 0.86), 'steady', 'low', 'point sky',
   0.75, look(4, 'buzz', 'black', None, 0.96, 0.95), 'Starboy', mannerism='breath',
   lines=['He has been here before, and he has come back stronger.'])
_c('kane', 'KANE', 'Harry Kane', 9, 'current', False, K, 'R', (0.9, 0.95, 0.88), 'ice', 'rocket', 'knee slide',
   0.82, look(0, 'short', 'brown', None, 1.04, 1.0), 'Hurricane', low=0.3,
   lines=['Hits them hard and high. Almost always.'])
_c('salah', 'SALAH', 'Mohamed Salah', 11, 'current', False, K, 'L', (0.88, 0.84, 0.88), 'ice', 'low', 'arms wide',
   0.86, look(2, 'afro', 'black', 'full', 0.97, 0.95), 'The Egyptian King', low=0.6)
_c('lewandowski', 'LEWANDOWSKI', 'Robert Lewandowski', 9, 'current', False, K, 'R', (0.9, 0.82, 0.92), 'thinker',
   'stopstart', 'heart', 0.84, look(0, 'short', 'brown', None, 1.04, 0.98), 'Waits for the keeper')
_c('jorginho', 'JORGINHO', 'Jorginho', 21, 'current', False, K, 'R', (0.88, 0.5, 0.92), 'thinker', 'hop',
   'badge kiss', 0.65, look(1, 'short', 'brown', 'stubble', 0.94, 0.94), 'The hop', low=0.7,
   lines=['The hop is coming. The keeper knows it, and still goes.'])
_c('rashford', 'RASHFORD', 'Marcus Rashford', 10, 'current', False, K, 'R', (0.66, 0.88, 0.8), 'kid', 'rocket',
   'think', 0.7, look(4, 'short', 'black', None, 1.0, 0.98), 'Think about it')
_c('grealish', 'GREALISH', 'Jack Grealish', 10, 'current', False, K, 'R', (0.7, 0.7, 0.82), 'showboat', 'curl',
   'knee slide', 0.68, look(1, 'long', 'brown', 'stubble', 0.98, 0.98, socks='down', headband=True),
   'Socks down', lines=['Socks rolled down. Calves on show.'])
# --- Current stars: keepers
_c('emi', 'E MARTINEZ', 'Emiliano "Dibu" Martinez', 23, 'current', False, KP, 'R', (0.6, 0.6, 0.4), 'showman',
   'point', 'shimmy', 0.95, look(1, 'short', 'black', 'stubble', 1.06, 1.06, gloves='lime', sleeves='long'),
   'Mind games', reach=0.06, speed=0.01, mannerism='scuff',
   lines=['He is talking to the taker. Of course he is.', 'The master of mind games is in goal.'])
_c('pickford', 'PICKFORD', 'Jordan Pickford', 1, 'current', False, KP, 'L', (0.65, 0.7, 0.55), 'reader', 'notes',
   'roar', 0.7, look(0, 'short', 'brown', 'stubble', 0.96, 1.0, gloves='orange', sleeves='long'), 'Bottle notes',
   reach=0.0, speed=0.02, mannerism='clap', lines=['Pickford checks the notes on his water bottle.'])
_c('courtois', 'COURTOIS', 'Thibaut Courtois', 1, 'current', False, KP, 'L', (0.5, 0.5, 0.4), 'wall', 'star', 'roar',
   0.85, look(0, 'short', 'brown', None, 1.14, 1.0, gloves='white', sleeves='long'), 'The tallest wall',
   reach=0.09, speed=-0.01)
_c('bounou', 'BOUNOU', 'Yassine Bounou', 1, 'current', False, KP, 'R', (0.5, 0.5, 0.4), 'reader', None, 'star',
   0.8, look(2, 'short', 'black', 'full', 1.04, 1.0, gloves='white', sleeves='long'), 'Reads every run-up',
   reach=0.03, speed=0.01)
_c('donnarumma', 'DONNARUMMA', 'Gianluigi Donnarumma', 99, 'current', False, KP, 'R', (0.5, 0.5, 0.4), 'wall', None,
   'wag', 0.8, look(1, 'short', 'black', 'stubble', 1.13, 1.08, gloves='black', sleeves='long'), 'Gigio',
   reach=0.08, speed=-0.01)
# --- Current stars: women
_c('bonmati', 'BONMATI', 'Aitana Bonmati', 14, 'current', True, K, 'R', (0.94, 0.78, 0.94), 'ice', 'low', 'heart',
   0.95, look(1, 'ponytail', 'brown', None, 0.93, 0.92), 'Three Ballons d\'Or', low=0.65)
_c('putellas', 'PUTELLAS', 'Alexia Putellas', 11, 'current', True, K, 'L', (0.88, 0.82, 0.92), 'steady', 'curl',
   'point sky', 0.92, look(1, 'ponytail', 'blond', None, 0.98, 0.94), 'La Reina')
_c('kerr', 'KERR', 'Sam Kerr', 20, 'current', True, K, 'R', (0.84, 0.9, 0.82), 'clutch', 'rocket', 'backflip', 0.88,
   look(1, 'ponytail', 'brown', None, 0.96, 0.95), 'The backflip', lines=['If she scores, stand well back.'])
_c('kelly', 'KELLY', 'Chloe Kelly', 18, 'current', True, K, 'R', (0.92, 0.94, 0.84), 'clutch', 'rocket',
   'shirt swing', 0.88, look(0, 'ponytail', 'blond', None, 0.98, 0.95), 'Winner, two Euro finals',
   lines=['She has won a European final from the spot already.'])
_c('russo', 'RUSSO', 'Alessia Russo', 23, 'current', True, K, 'R', (0.84, 0.82, 0.86), 'ice', 'low', 'arms wide',
   0.78, look(0, 'ponytail', 'brown', None, 1.0, 0.94), 'Cool finisher')
_c('ljames', 'L JAMES', 'Lauren James', 7, 'current', True, K, 'R', (0.74, 0.86, 0.9), 'showboat', 'curl',
   'knee slide', 0.82, look(4, 'bun', 'black', None, 0.98, 0.94), 'Magic feet')
_c('hegerberg', 'HEGERBERG', 'Ada Hegerberg', 14, 'current', True, K, 'R', (0.88, 0.84, 0.88), 'steady', 'low',
   'point sky', 0.85, look(0, 'ponytail', 'blond', None, 1.03, 0.94), 'First Ballon d\'Or')
_c('bronze', 'BRONZE', 'Lucy Bronze', 2, 'current', True, K, 'R', (0.86, 0.95, 0.74), 'hothead', 'rocket', 'scream',
   0.82, look(2, 'curly', 'black', None, 1.0, 0.96, headband=True), 'Plays through anything',
   lines=['Strapped up and still smashing it.'])
_c('earps', 'EARPS', 'Mary Earps', 1, 'current', True, KP, 'R', (0.6, 0.55, 0.45), 'showman', None, 'roar', 0.85,
   look(0, 'ponytail', 'blond', None, 1.0, 1.0, gloves='white', sleeves='long'), 'The roar', reach=0.04,
   speed=0.02, mannerism='clap')
_c('hampton', 'HAMPTON', 'Hannah Hampton', 13, 'current', True, KP, 'L', (0.55, 0.55, 0.4), 'reader', 'notes',
   'roar', 0.82, look(0, 'ponytail', 'brown', None, 1.02, 0.98, gloves='pink', sleeves='long'),
   'Euro 2025 shootout hero', reach=0.04, speed=0.02, lines=['Hampton has the notes. She always has the notes.'])
_c('endler', 'ENDLER', 'Christiane Endler', 1, 'current', True, KP, 'R', (0.55, 0.6, 0.4), 'wall', 'star',
   'roar', 0.85, look(1, 'ponytail', 'black', None, 1.06, 1.0, gloves='black', sleeves='long'), 'The wall of Chile',
   reach=0.07, speed=0.0)
_c('coll', 'COLL', 'Cata Coll', 13, 'current', True, KP, 'R', (0.55, 0.55, 0.4), 'cat', None, 'shush', 0.72,
   look(1, 'ponytail', 'brown', None, 1.02, 0.96, gloves='white', sleeves='long'), 'Quick hands', reach=0.03,
   speed=0.03)
# --- Legends: men
_c('pele', 'PELE', 'Pele', 10, 'legend', False, K, 'R', (0.92, 0.86, 0.94), 'clutch', 'stopstart', 'punch', 1.0,
   look(4, 'buzz', 'black', None, 0.97, 0.98), 'The King', lines=['The King himself. Three World Cups.'],
   mannerism='sky')
_c('maradona', 'MARADONA', 'Diego Maradona', 10, 'legend', False, K, 'L', (0.86, 0.82, 0.95), 'showboat', 'curl',
   'scream', 1.0, look(2, 'curly', 'black', None, 0.9, 1.0), 'El Diego', lines=['El Diego. Genius in a left boot.'])
_c('zidane', 'ZIDANE', 'Zinedine Zidane', 10, 'legend', False, K, 'R', (0.97, 0.78, 0.93), 'ice', 'panenka',
   'arms wide', 1.0, look(1, 'bald', 'brown', None, 1.04, 0.98), 'Zizou',
   lines=['He chipped one in a World Cup final. Off the bar and in.'])
_c('ronaldinho', 'RONALDINHO', 'Ronaldinho', 10, 'legend', False, K, 'R', (0.82, 0.8, 0.92), 'showboat', 'curl',
   'shaka', 0.98, look(4, 'long', 'black', None, 1.0, 0.96, headband=True), 'Joga bonito',
   lines=['Smiling on the walk. Of course he is.'])
_c('r9', 'RONALDO', 'Ronaldo Nazario (R9)', 9, 'legend', False, K, 'R', (0.88, 0.9, 0.9), 'ice', 'low', 'wag', 1.0,
   look(3, 'r9', 'black', None, 1.02, 1.02), 'O Fenomeno', lines=['R9. The original Ronaldo.'])
_c('henry', 'HENRY', 'Thierry Henry', 14, 'legend', False, K, 'R', (0.9, 0.82, 0.92), 'ice', 'curl', 'lean', 0.95,
   look(4, 'bald', 'black', None, 1.05, 0.96), 'Va va voom')
_c('beckham', 'BECKHAM', 'David Beckham', 7, 'legend', False, K, 'R', (0.76, 0.82, 0.95), 'kid', 'curl',
   'arms wide', 0.9, look(0, 'quiff', 'blond', 'stubble', 1.0, 0.96), 'Bend it',
   lines=['Watch his footing on that spot.'])
_c('cantona', 'CANTONA', 'Eric Cantona', 7, 'legend', False, K, 'R', (0.96, 0.8, 0.88), 'ice', 'low', 'collar', 0.97,
   look(1, 'short', 'black', None, 1.06, 1.04, collar=True), 'Collar up',
   lines=['Collar up. He looks bored. That is bad news for the keeper.'])
_c('zlatan', 'ZLATAN', 'Zlatan Ibrahimovic', 10, 'legend', False, K, 'R', (0.92, 0.95, 0.84), 'showboat', 'rocket',
   'roar', 0.98, look(1, 'manbun', 'black', 'full', 1.1, 1.04), 'I am Zlatan',
   lines=['Zlatan does not take penalties. Penalties take Zlatan.'])
_c('pirlo', 'PIRLO', 'Andrea Pirlo', 21, 'legend', False, K, 'R', (0.98, 0.6, 0.94), 'ice', 'panenka', 'stroll',
   0.95, look(1, 'long', 'brown', 'full', 1.0, 0.94), 'The Maestro',
   lines=['Pirlo. He is going to chip it. Everyone knows. Nobody can stop it.'])
_c('panenka', 'PANENKA', 'Antonin Panenka', 7, 'legend', False, K, 'R', (0.96, 0.6, 0.9), 'ice', 'panenka',
   'arms wide', 0.88, look(0, 'long', 'brown', 'full', 1.0, 1.0), 'Invented it in 1976', mannerism='breath')
_c('baggio', 'BAGGIO', 'Roberto Baggio', 10, 'legend', False, K, 'R', (0.76, 0.8, 0.94), 'thinker', 'low',
   'point sky', 0.95, look(1, 'ponytail', 'brown', 'goatee', 0.96, 0.94), 'Il Divin Codino',
   lines=['The Divine Ponytail. Pasadena still haunts him.'])
_c('totti', 'TOTTI', 'Francesco Totti', 10, 'legend', False, K, 'R', (0.9, 0.82, 0.9), 'showboat', 'panenka',
   'selfie', 0.92, look(0, 'short', 'brown', 'stubble', 1.02, 1.0), 'Er cucchiaio',
   lines=['Totti. Expect the spoon. Expect a selfie.'])
_c('drogba', 'DROGBA', 'Didier Drogba', 11, 'legend', False, K, 'R', (0.94, 0.92, 0.84), 'clutch', 'low',
   'knee slide', 0.95, look(5, 'braids', 'black', None, 1.08, 1.06), 'Munich 2012',
   lines=['He won a European Cup with the last kick in Munich.'])
_c('gerrard', 'GERRARD', 'Steven Gerrard', 8, 'legend', False, K, 'R', (0.84, 0.94, 0.84), 'clutch', 'rocket',
   'badge kiss', 0.9, look(0, 'buzz', 'brown', None, 1.02, 0.98), 'Istanbul 2005')
_c('klose', 'KLOSE', 'Miroslav Klose', 11, 'legend', False, K, 'R', (0.84, 0.8, 0.84), 'steady', 'low', 'backflip',
   0.85, look(0, 'buzz', 'brown', None, 1.04, 0.96), 'Somersault king')
_c('grosso', 'GROSSO', 'Fabio Grosso', 3, 'icon', False, K, 'L', (0.86, 0.92, 0.8), 'clutch', 'rocket', 'scream',
   0.8, look(1, 'long', 'black', 'stubble', 1.0, 0.96), 'Berlin 2006',
   lines=['A full-back to win the World Cup. He scored the last one in Berlin.'])
_c('pearce', 'PSYCHO', 'Stuart Pearce', 3, 'icon', False, K, 'L', (0.8, 0.98, 0.7), 'hothead', 'rocket', 'scream',
   0.85, look(0, 'buzz', 'brown', None, 1.0, 1.06), 'Euro 96 redemption',
   lines=['Psycho. He missed in 1990. Six years later he roared.'])
_c('balotelli', 'BALOTELLI', 'Mario Balotelli', 45, 'icon', False, K, 'R', (0.98, 0.84, 0.88), 'ice', 'stopstart',
   'flex', 0.88, look(4, 'mohawk', 'black', None, 1.06, 1.04), 'Why always me?',
   lines=['Hardly ever misses. Does not even look at the keeper.'])
# --- Legends: keepers
_c('buffon', 'BUFFON', 'Gianluigi Buffon', 1, 'legend', False, KP, 'R', (0.55, 0.55, 0.4), 'wall', None, 'roar',
   0.98, look(1, 'short', 'brown', 'stubble', 1.06, 1.04, gloves='white', sleeves='long'), 'Gigi', reach=0.07,
   speed=0.01, mannerism='bar')
_c('yashin', 'YASHIN', 'Lev Yashin', 1, 'legend', False, KP, 'R', (0.5, 0.5, 0.4), 'cat', None, 'float', 1.0,
   look(0, 'short', 'brown', None, 1.05, 1.0, gloves='black', sleeves='long', cap=True), 'The Black Spider',
   reach=0.07, speed=0.03, kit=(0.06, 0.06, 0.07), lines=['The Black Spider. Over a hundred penalties saved.'])
_c('higuita', 'HIGUITA', 'Rene Higuita', 1, 'icon', False, KP, 'R', (0.7, 0.8, 0.6), 'gambler', 'early', 'scorpion',
   0.9, look(3, 'afro', 'black', None, 0.98, 1.0, gloves='white'), 'The scorpion',
   lines=['El Loco himself. Do not be surprised by anything.'])
_c('chilavert', 'CHILAVERT', 'Jose Luis Chilavert', 1, 'icon', False, KP, 'L', (0.88, 0.92, 0.82), 'showman', 'point',
   'roar', 0.92, look(1, 'short', 'black', 'goatee', 1.04, 1.12, gloves='white', sleeves='long'),
   'The keeper who takes them', reach=0.03, speed=0.0, lines=['A goalkeeper who scores free kicks and penalties.'])
_c('ceni', 'CENI', 'Rogerio Ceni', 1, 'icon', False, KP, 'R', (0.9, 0.86, 0.86), 'reader', None, 'roar', 0.85,
   look(0, 'short', 'brown', None, 1.02, 1.0, gloves='orange', sleeves='long'), 'Over a hundred goals', reach=0.02,
   speed=0.01)
_c('neuer', 'NEUER', 'Manuel Neuer', 1, 'legend', False, KP, 'L', (0.65, 0.75, 0.6), 'sweeper', 'early', 'roar',
   0.95, look(0, 'short', 'blond', None, 1.08, 1.04, gloves='white', sleeves='long'), 'Sweeper-keeper',
   reach=0.06, speed=0.02)
_c('dudek', 'DUDEK', 'Jerzy Dudek', 1, 'icon', False, KP, 'R', (0.5, 0.55, 0.4), 'dancer', 'legs', 'dance', 0.85,
   look(0, 'short', 'brown', None, 1.03, 1.0, gloves='white', sleeves='long'), 'Spaghetti legs',
   lines=['Watch the legs. Istanbul, 2005.'])
_c('kahn', 'KAHN', 'Oliver Kahn', 1, 'legend', False, KP, 'R', (0.6, 0.6, 0.45), 'wall', None, 'roar', 0.97,
   look(0, 'short', 'blond', None, 1.06, 1.08, gloves='white', sleeves='long'), 'The Titan', reach=0.07,
   speed=0.02, mannerism='bar', lines=['The Titan is screaming at his defenders. There are none.'])
_c('lehmann', 'LEHMANN', 'Jens Lehmann', 1, 'icon', False, KP, 'R', (0.55, 0.6, 0.45), 'reader', 'notes', 'roar',
   0.82, look(0, 'short', 'blond', None, 1.06, 1.0, gloves='white', sleeves='long'), 'The note in the sock',
   reach=0.03, speed=0.01, lines=['He is checking a note in his sock.'])
_c('schmeichel', 'SCHMEICHEL', 'Peter Schmeichel', 1, 'legend', False, KP, 'R', (0.6, 0.65, 0.45), 'wall', 'star',
   'star', 0.95, look(0, 'short', 'blond', None, 1.1, 1.1, gloves='white', sleeves='long'), 'The Great Dane',
   reach=0.08, speed=0.0)
_c('casillas', 'CASILLAS', 'Iker Casillas', 1, 'legend', False, KP, 'R', (0.55, 0.55, 0.45), 'cat', None,
   'float', 0.95, look(1, 'short', 'black', 'stubble', 1.0, 0.98, gloves='white', sleeves='long'), 'San Iker',
   reach=0.04, speed=0.03)
# --- Legends: women
_c('marta', 'MARTA', 'Marta', 10, 'legend', True, K, 'L', (0.9, 0.84, 0.94), 'showboat', 'curl', 'point sky', 1.0,
   look(3, 'ponytail', 'black', None, 0.94, 0.94), 'The Queen', lines=['Marta. Six-time world player of the year.'])
_c('hamm', 'HAMM', 'Mia Hamm', 9, 'legend', True, K, 'R', (0.9, 0.84, 0.88), 'steady', 'low', 'arms wide', 0.95,
   look(0, 'ponytail', 'brown', None, 0.95, 0.92), 'The original icon')
_c('wambach', 'WAMBACH', 'Abby Wambach', 20, 'legend', True, K, 'R', (0.86, 0.94, 0.8), 'hothead', 'rocket', 'scream',
   0.92, look(0, 'short', 'blond', None, 1.06, 1.02), 'Header queen')
_c('rapinoe', 'RAPINOE', 'Megan Rapinoe', 15, 'legend', True, K, 'R', (0.96, 0.8, 0.9), 'ice', 'low', 'pose', 0.98,
   look(0, 'short', 'purple', None, 0.98, 0.94), 'The pose', low=0.6,
   lines=['Arms out, chin up. If she scores, you know what is coming.'])
_c('morgan', 'MORGAN', 'Alex Morgan', 13, 'legend', True, K, 'R', (0.86, 0.84, 0.86), 'showboat', 'low', 'tea', 0.9,
   look(1, 'ponytail', 'brown', None, 0.98, 0.92), 'Tea time', lines=['If this goes in, someone is having tea.'])
_c('chastain', 'CHASTAIN', 'Brandi Chastain', 6, 'icon', True, K, 'L', (0.9, 0.9, 0.84), 'clutch', 'rocket',
   'shirt swing', 0.92, look(0, 'short', 'blond', None, 1.0, 0.95), '1999 winner',
   lines=['She won a World Cup final with a penalty. With her weaker foot.'])
_c('sawa', 'SAWA', 'Homare Sawa', 10, 'legend', True, K, 'R', (0.92, 0.76, 0.9), 'ice', 'low', 'arms wide', 0.92,
   look(0, 'short', 'black', None, 0.92, 0.92), '2011 world champion')
_c('prinz', 'PRINZ', 'Birgit Prinz', 9, 'legend', True, K, 'R', (0.86, 0.92, 0.84), 'clutch', 'rocket', 'punch',
   0.92, look(0, 'short', 'brown', None, 1.04, 1.0), 'Two World Cups')
_c('sinclair', 'SINCLAIR', 'Christine Sinclair', 12, 'legend', True, K, 'R', (0.9, 0.84, 0.88), 'steady', 'low',
   'point sky', 0.95, look(0, 'ponytail', 'brown', None, 1.0, 0.95), 'All-time top scorer')
_c('ksmith', 'K SMITH', 'Kelly Smith', 10, 'legend', True, K, 'R', (0.86, 0.84, 0.9), 'showboat', 'curl', 'boot kiss',
   0.88, look(0, 'ponytail', 'blond', None, 0.96, 0.94), 'Kisses the boot')
_c('scurry', 'SCURRY', 'Briana Scurry', 1, 'icon', True, KP, 'R', (0.55, 0.5, 0.4), 'gambler', 'early', 'roar', 0.9,
   look(4, 'short', 'black', None, 1.0, 1.0, gloves='white', sleeves='long'), 'The 1999 save', reach=0.04,
   speed=0.03)
_c('angerer', 'ANGERER', 'Nadine Angerer', 1, 'legend', True, KP, 'R', (0.55, 0.55, 0.45), 'wall', None, 'roar',
   0.9, look(0, 'short', 'blond', None, 1.02, 1.0, gloves='white', sleeves='long'), 'World player of the year',
   reach=0.06, speed=0.01)
_c('solo', 'SOLO', 'Hope Solo', 1, 'icon', True, KP, 'R', (0.6, 0.6, 0.45), 'showman', 'point', 'shush', 0.88,
   look(1, 'ponytail', 'brown', None, 1.03, 0.98, gloves='white', sleeves='long'), 'Glove swap antics',
   reach=0.05, speed=0.02)
# --- Unlockable archetypes (fictional)
_c('professor', 'PROFESSOR', 'The Professor', 8, 'fantasy', False, K, 'R', (0.92, 0.6, 0.99), 'thinker', 'low',
   'stroll', 0.85, look(0, 'bald', 'grey', 'full', 0.96, 0.96, glasses=True), 'Never misses low', low=0.95,
   unlock='bins_5', glow=(0.6, 0.9, 1.0))
_c('elloco', 'EL LOCO', 'El Loco', 1, 'fantasy', False, KP, 'R', (0.92, 0.95, 0.88), 'gambler', 'early', 'scorpion',
   0.9, look(3, 'afro', 'bleach', 'goatee', 1.0, 1.04, gloves='pink'), 'Takes them and saves them', reach=0.05,
   speed=0.03, unlock='keeper_goal', glow=(1.0, 0.4, 0.6))
_c('thecat', 'THE CAT', 'The Cat', 1, 'fantasy', True, KP, 'R', (0.55, 0.55, 0.45), 'cat', None, 'float', 0.9,
   look(5, 'bun', 'black', None, 1.0, 0.94, gloves='black'), 'Nine lives, ten fingertips', reach=0.06,
   speed=0.05, unlock='fingertip', glow=(0.4, 1.0, 0.5))
_c('ice', 'ICE', 'Ice', 5, 'fantasy', True, K, 'R', (0.99, 0.75, 0.92), 'ice', 'low', 'cold', 0.95,
   look(0, 'long', 'white', None, 1.0, 0.94), 'The fifth-taker legend', unlock='sudden_win', glow=(0.7, 0.95, 1.0))
# --- Fantasy originals
_c('colossus', 'COLOSSUS', 'Colossus', 1, 'fantasy', False, KP, 'R', (0.5, 0.9, 0.3), 'wall', 'star', 'roar', 0.95,
   look(5, 'bald', 'black', 'full', 1.22, 1.22, gloves='gold'), 'A mountain in gloves', reach=0.12, speed=-0.02,
   unlock='three_saves', glow=(1.0, 0.6, 0.2))
_c('mystic', 'MYSTIC', 'The Mystic', 13, 'fantasy', True, K, 'R', (0.95, 0.75, 0.95), 'thinker', 'disguise',
   'levitate', 1.0, look(2, 'long', 'purple', None, 0.98, 0.92), 'Sees the future', unlock='tournament',
   glow=(0.7, 0.3, 1.0), lines=['The Mystic has already seen how this ends.'])
_c('thunder', 'THUNDER', 'Thunder', 9, 'fantasy', False, K, 'R', (0.8, 1.0, 0.82), 'hothead', 'rocket', 'bolt', 0.92,
   look(4, 'mohawk', 'bleach', None, 1.08, 1.1, boots='cyan'), 'The fastest shot alive', glow=(0.4, 0.8, 1.0))
_c('shadow', 'SHADOW', 'Shadow', 0, 'fantasy', False, K, 'L', (0.9, 0.78, 0.9), 'thinker', 'disguise', 'shush', 0.9,
   look(5, 'braids', 'black', None, 1.0, 0.94), 'Nobody reads Shadow', unlock='ghost_win', glow=(0.35, 0.35, 0.45))
_c('phoenix', 'PHOENIX', 'Phoenix', 17, 'fantasy', True, K, 'R', (0.92, 0.86, 0.86), 'clutch', 'curl', 'wings', 0.95,
   look(2, 'long', 'red', None, 0.98, 0.94), 'Rises after every miss', unlock='rewrite', glow=(1.0, 0.45, 0.1))
_c('wizard', 'WIZARD', 'The Wizard', 11, 'fantasy', False, K, 'L', (0.86, 0.72, 0.96), 'showboat', 'curl', 'spell',
   0.92, look(0, 'long', 'grey', 'full', 0.98, 0.96), 'Bends it round corners', glow=(0.4, 1.0, 0.6))
_c('valkyrie', 'VALKYRIE', 'Valkyrie', 4, 'fantasy', True, K, 'R', (0.88, 0.96, 0.8), 'clutch', 'rocket', 'roar',
   0.92, look(0, 'braids', 'blond', None, 1.08, 1.0), 'Shoots like a spear', glow=(0.95, 0.95, 0.6))
_c('phantom', 'PHANTOM', 'Phantom', 1, 'fantasy', False, KP, 'R', (0.55, 0.55, 0.45), 'reader', 'legs', 'float', 0.95,
   look(0, 'buzz', 'white', None, 1.04, 0.98, gloves='white'), 'Is he even there?', reach=0.05, speed=0.03,
   glow=(0.85, 0.9, 1.0))
_c('siren', 'SIREN', 'Siren', 1, 'fantasy', True, KP, 'R', (0.55, 0.55, 0.45), 'dancer', 'legs', 'shimmy', 0.92,
   look(2, 'long', 'pink', None, 1.0, 0.95, gloves='pink'), 'Hypnotic on the line', reach=0.04, speed=0.02,
   glow=(1.0, 0.5, 0.85))

EXTRA = []          # created players and mod characters


def all_characters():
    return ROSTER + EXTRA


def get(key):
    for ch in ROSTER + EXTRA:
        if ch['key'] == key:
            return ch
    return None


def locked(ch, stats):
    """Unlockable legends need their matching achievement."""
    need = ch.get('unlock')
    return bool(need) and need not in (stats or {}).get('achievements', [])


FILTERS = ['all', 'legend', 'icon', 'current', 'women', 'keepers', 'fantasy', 'custom']
FILTER_LABELS = {'all': 'All', 'legend': 'Legends', 'icon': 'Cult icons', 'current': 'Current stars',
                 'women': 'Women', 'keepers': 'Keepers', 'fantasy': 'Fantasy', 'custom': 'Yours and mods'}


def filtered(kind, role=None):
    out = []
    for ch in all_characters():
        if role and ch['role'] != role:
            continue
        if kind == 'all' or (kind == 'women' and ch['women']) or (kind == 'keepers' and ch['role'] == 'keep') or \
                (kind == 'custom' and ch['era'] in ('custom', 'mod')) or ch['era'] == kind:
            out.append(ch)
    return out


def make_player(ch, number=None):
    """A squad.Player for a character."""
    keeper = ch['role'] == 'keep'
    p = Player(ch['number'] if number is None else number, ch['name'], ch['composure'], ch['power'],
               ch['placement'], ch['foot'], ch['natural'], ch['low'], keeper=keeper)
    p.char = ch['key']
    p.full = ch['full']
    p.women = ch['women']
    p.look = dict(ch['look'])
    p.persona = ch['persona']
    p.signature = ch['signature']
    p.celebration = ch['celebration']
    p.aura = ch['aura']
    p.glow = tuple(ch['glow']) if ch.get('glow') else GLOWS.get(ch['era'], GLOWS['mod'])
    p.reach = ch['reach']
    p.speed = ch['speed']
    p.tag = ch['tag']
    p.lines = list(ch['lines'])
    p.mannerism = ch['mannerism'] or ('clap' if keeper else 'breath')
    p.era = ch['era']
    p.kit_override = tuple(ch['kit']) if ch.get('kit') else None
    return p


def draft(rng, takers, keepers, exclude=(), stats=None):
    """Random characters for a squad: unlocked, not already taken, no custom ones."""
    pool = [c for c in ROSTER if c['key'] not in exclude and not locked(c, stats)]
    out = [c for c in pool if c['role'] == 'kick']
    gk = [c for c in pool if c['role'] == 'keep']
    return rng.sample(out, min(takers, len(out))), rng.sample(gk, min(keepers, len(gk)))


def squad_from(taker_keys, keeper_key, rng, exclude=(), stats=None, size=10):
    """Takers in the order given, topped up to a squad of ten with drafted
    characters, then the keeper."""
    chars = [get(k) for k in taker_keys if get(k)]
    used = set(exclude) | {c['key'] for c in chars}
    if keeper_key:
        used.add(keeper_key)
    more, gks = draft(rng, max(0, size - len(chars)), 0 if keeper_key and get(keeper_key) else 1, used, stats)
    keeper = get(keeper_key) if keeper_key and get(keeper_key) else gks[0]
    return [make_player(c) for c in chars + more] + [make_player(keeper)]


# ------------------------------------------------------------------ club players
def _crc(*parts):
    return zlib.crc32('|'.join(str(p) for p in parts).encode())


def dress_club_player(p):
    """Give a generated club player a stable look, personality and habits."""
    seed = _crc(p.name, p.number)
    p.look = club_look(seed, p.keeper)
    r = random.Random(seed + 1)
    if p.keeper:
        p.persona = r.choice(list(KEEPER_PERSONAS) + ['wall', 'reader'])
        p.mannerism = r.choice(['bar', 'scuff', 'clap'])
        p.celebration = r.choice(['dance', 'roar', 'star', 'wag'])
    else:
        c, pw, pl = p.composure, p.power, p.placement
        if c > 0.72:
            p.persona = 'ice'
        elif c < 0.38 and (pw + pl) / 2 > 0.55:
            p.persona = 'kid'
        elif pw > 0.7 and c < 0.55:
            p.persona = 'hothead'
        elif pl > 0.7 and pw < 0.5:
            p.persona = 'thinker'
        elif seed % 7 == 0:
            p.persona = 'showboat'
        elif seed % 11 == 0:
            p.persona = 'clutch'
        else:
            p.persona = 'steady'
        p.mannerism = r.choice(['kiss', 'wipe', 'sky', 'breath'])
        if seed % 5 == 0:
            p.signature = r.choice(['hop', 'stance', 'low', 'curl', 'rocket'])
    return p


# ---------------------------------------------------------- created players
def players_path(home):
    return os.path.join(home, 'players.json')


def valid_character(d, era='mod'):
    """Clean a character dict from a file (create-a-player or a mod). Returns
    the character or None."""
    try:
        role = d.get('role', 'kick')
        if role not in ('kick', 'keep'):
            return None
        ratings = [float(d[k]) for k in ('composure', 'power', 'placement')]
        if not all(0.0 <= r <= 1.0 for r in ratings):
            return None
        persona = d.get('persona', 'steady')
        if persona not in (KEEPER_PERSONAS if role == 'keep' else TAKER_PERSONAS):
            persona = 'wall' if role == 'keep' else 'steady'
        sig = d.get('signature')
        sig = sig if sig in SIGNATURES else None
        cel = d.get('celebration')
        cel = cel if cel in (SAVE_CELEBRATIONS if role == 'keep' else CELEBRATIONS) else None
        lk = d.get('look') or {}
        lk = look(int(lk.get('skin', 1)) % len(SKINS), lk.get('hair', 'short') if lk.get('hair') in HAIRS else 'short',
                  lk.get('hc', 'brown') if lk.get('hc') in HAIR_COLOURS else 'brown',
                  lk.get('beard') if lk.get('beard') in BEARDS else None,
                  max(0.85, min(1.2, float(lk.get('h', 1.0)))), max(0.85, min(1.2, float(lk.get('w', 1.0)))),
                  boots=lk.get('boots', 'black') if lk.get('boots') in BOOTS else 'black')
        if role == 'keep':
            lk['gloves'] = 'white'
            lk['sleeves'] = 'long'
        name = ''.join(ch for ch in str(d['name']).upper() if ch.isalnum() or ch in ' .-')[:12].strip()
        if not name:
            return None
        key = (d.get('key') or f'{era}:{name.lower()}')[:40]
        return dict(key=key, name=name, full=str(d.get('full', name.title()))[:30], number=int(d.get('number', 9)) % 100,
                    era=era, women=bool(d.get('women', False)), role=role, foot='L' if d.get('foot') == 'L' else 'R',
                    composure=ratings[0], power=ratings[1], placement=ratings[2], persona=persona, signature=sig,
                    celebration=cel, aura=max(0.0, min(1.0, float(d.get('aura', 0.3)))), look=lk,
                    tag=str(d.get('tag', ''))[:40], natural=max(0.3, min(0.9, float(d.get('natural', 0.6)))),
                    low=max(0.0, min(1.0, float(d.get('low', 0.5)))),
                    reach=max(-0.05, min(0.1, float(d.get('reach', 0.0)))),
                    speed=max(-0.03, min(0.04, float(d.get('speed', 0.0)))), unlock=None, glow=None, mannerism=None,
                    lines=[str(s)[:80] for s in d.get('lines', [])[:3] if isinstance(s, str)], kit=None)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def add_extra(ch):
    """Add (or replace) a created or modded character."""
    EXTRA[:] = [c for c in EXTRA if c['key'] != ch['key']]
    if any(c['key'] == ch['key'] for c in ROSTER):
        ch = dict(ch, key=ch['key'] + '+')
    EXTRA.append(ch)
    return ch


def load_custom(path):
    """Created players saved by the create-a-player screen."""
    EXTRA[:] = [c for c in EXTRA if c['era'] != 'custom']
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return 0
    n = 0
    for d in data.get('players', []) if isinstance(data, dict) else []:
        ch = valid_character(d, 'custom')
        if ch:
            add_extra(ch)
            n += 1
    return n


def save_custom(path):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(dict(players=[c for c in EXTRA if c['era'] == 'custom']), f, indent=1)
        return True
    except OSError:
        return False


RATING_BUDGET = 2.25          # composure + power + placement for a created player
CREATE_FIELDS = ['name', 'role', 'number', 'foot', 'women', 'skin', 'hair', 'hc', 'beard', 'h', 'w', 'boots',
                 'persona', 'signature', 'celebration', 'composure', 'power', 'placement', 'save']


def blank_character():
    return dict(key='custom:new', name='NEW STAR', full='New star', number=9, era='custom', women=False,
                role='kick', foot='R', composure=0.75, power=0.75, placement=0.75, persona='steady', signature=None,
                celebration='knee slide', aura=0.3, look=look(1, 'short', 'brown', None, 1.0, 1.0, boots='black'),
                tag='Created by you', natural=0.6, low=0.5, reach=0.0, speed=0.0, unlock=None, glow=None,
                mannerism=None, lines=[], kit=None)


def budget_left(ch):
    return round(RATING_BUDGET - ch['composure'] - ch['power'] - ch['placement'], 2)
