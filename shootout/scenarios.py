"""Famous shootouts, picked up at the moment the deciding kick is due.

More can be added as JSON files in ~/.penalty_shootout/mods (see load_mods).

You always play team 'p1'. Results are in kicking order for each side
(True = scored). Only team names and kit colours are used.
"""

import json
import os

MOD_DIR = os.path.join(os.path.expanduser('~'), '.penalty_shootout', 'mods')

SCENARIOS = [
    dict(
        key='panenka76',
        title='Belgrade 1976',
        teams=('Czechoslovakia', 'West Germany'),
        kits=(dict(shirt=(0.85, 0.12, 0.15), shorts=(1.0, 1.0, 1.0), keeper=(0.2, 0.2, 0.25)),
              dict(shirt=(0.95, 0.95, 0.95), shorts=(0.1, 0.1, 0.1), keeper=(0.15, 0.55, 0.25))),
        first='p1',
        results={'p1': [True, True, True, True], 'p2': [True, True, True, False]},
        role='kick',
        intro=('European Championship final. Uli Hoeness has just blazed the fourth German '
               'kick over the bar. Score this one and Czechoslovakia are champions of Europe.'),
        history=('Antonin Panenka waited for Sepp Maier to dive and chipped the ball softly '
                 'down the middle. The kick still carries his name.'),
    ),
    dict(
        key='berlin06',
        title='Berlin 2006',
        teams=('Italy', 'France'),
        kits=(dict(shirt=(0.1, 0.3, 0.8), shorts=(1.0, 1.0, 1.0), keeper=(0.95, 0.8, 0.1)),
              dict(shirt=(0.95, 0.95, 0.95), shorts=(0.1, 0.15, 0.45), keeper=(0.2, 0.2, 0.25))),
        first='p1',
        results={'p1': [True, True, True, True], 'p2': [True, False, True, True]},
        role='kick',
        intro=('World Cup final. David Trezeguet hit the bar with France\'s second kick. '
               'Italy have scored all four. One more and the World Cup is Italy\'s.'),
        history='Fabio Grosso rifled it high into the corner. Italy won 5-3.',
    ),
    dict(
        key='lusail22',
        title='Lusail 2022',
        teams=('Argentina', 'France'),
        kits=(dict(shirt=(0.55, 0.78, 0.95), shorts=(0.1, 0.1, 0.15), keeper=(0.25, 0.25, 0.3)),
              dict(shirt=(0.1, 0.15, 0.4), shorts=(1.0, 1.0, 1.0), keeper=(0.95, 0.8, 0.1))),
        first='p2',
        results={'p1': [True, True, True], 'p2': [True, False, False, True]},
        role='kick',
        intro=('World Cup final after a 3-3 classic. Kingsley Coman was saved and Aurelien '
               'Tchouameni missed. Argentina lead 3-2: score this to win the World Cup.'),
        history='Gonzalo Montiel sent Hugo Lloris the wrong way. Argentina won 4-2.',
    ),
    dict(
        key='wembley21',
        title='Wembley 2021',
        teams=('England', 'Italy'),
        kits=(dict(shirt=(0.95, 0.95, 0.95), shorts=(0.1, 0.15, 0.4), keeper=(0.95, 0.8, 0.1)),
              dict(shirt=(0.1, 0.3, 0.8), shorts=(1.0, 1.0, 1.0), keeper=(0.15, 0.6, 0.3))),
        first='p2',
        results={'p1': [True, True, False, False], 'p2': [True, False, True, True, False]},
        role='kick',
        intro=('Euro 2020 final. Rashford hit the post and Sancho was saved, but Pickford '
               'has just saved from Jorginho. Italy lead 3-2: you must score to stay alive.'),
        history='Gianluigi Donnarumma saved from Bukayo Saka. Italy won 3-2.',
    ),
    dict(
        key='istanbul05',
        title='Istanbul 2005',
        teams=('Liverpool', 'AC Milan'),
        kits=(dict(shirt=(0.8, 0.1, 0.12), shorts=(0.8, 0.1, 0.12), keeper=(0.2, 0.2, 0.22)),
              dict(shirt=(0.95, 0.95, 0.95), shorts=(0.95, 0.95, 0.95), keeper=(0.95, 0.8, 0.1))),
        first='p2',
        results={'p1': [True, True, False, True], 'p2': [False, False, True, True]},
        role='keep',
        intro=('Champions League final, after Liverpool came back from 3-0 down. You are in '
               'goal. Save this kick and Liverpool win the Champions League.'),
        history=('Jerzy Dudek danced on his line all shootout, then saved Andriy '
                 'Shevchenko\'s kick. Liverpool won 3-2.'),
    ),
    dict(
        key='munich12',
        title='Munich 2012',
        teams=('Chelsea', 'Bayern Munich'),
        kits=(dict(shirt=(0.1, 0.25, 0.75), shorts=(0.1, 0.25, 0.75), keeper=(0.95, 0.8, 0.1)),
              dict(shirt=(0.85, 0.1, 0.15), shorts=(0.85, 0.1, 0.15), keeper=(0.2, 0.6, 0.3))),
        first='p2',
        results={'p1': [False, True, True, True], 'p2': [True, True, True, False, False]},
        role='kick',
        intro=('Champions League final in Bayern\'s own stadium. Cech has saved from Olic '
               'and Schweinsteiger hit the post. Score this and Chelsea win it.'),
        history='Didier Drogba rolled it past Manuel Neuer. Chelsea won 4-3.',
    ),
    dict(
        key='pasadena94',
        title='Pasadena 1994',
        teams=('Italy', 'Brazil'),
        kits=(dict(shirt=(0.1, 0.3, 0.8), shorts=(1.0, 1.0, 1.0), keeper=(0.2, 0.2, 0.25)),
              dict(shirt=(0.98, 0.85, 0.1), shorts=(0.1, 0.3, 0.75), keeper=(0.2, 0.5, 0.3))),
        first='p1',
        results={'p1': [False, True, True, False], 'p2': [False, True, True, True]},
        role='kick',
        intro=('World Cup final, 0-0 after extra time in the heat. Baresi and Massaro have missed '
               'for Italy. Brazil lead 3-2: you must score to keep Italy alive.'),
        history='Roberto Baggio blazed it over the bar. Brazil won 3-2.',
    ),
    dict(
        key='pasadena99',
        title='Pasadena 1999',
        teams=('USA', 'China'),
        kits=(dict(shirt=(0.95, 0.95, 0.95), shorts=(0.1, 0.15, 0.45), keeper=(0.2, 0.2, 0.25)),
              dict(shirt=(0.85, 0.1, 0.12), shorts=(0.85, 0.1, 0.12), keeper=(0.15, 0.55, 0.3))),
        first='p2',
        results={'p1': [True, True, True, True], 'p2': [True, True, False, True, True]},
        role='kick',
        intro=('Women\'s World Cup final in front of 90,000 at the Rose Bowl. Briana Scurry has '
               'saved China\'s third kick. Score this and the USA are world champions.'),
        history='Brandi Chastain scored the winning penalty. The USA won 5-4.',
    ),
    dict(
        key='moscow08',
        title='Moscow 2008',
        teams=('Chelsea', 'Manchester United'),
        kits=(dict(shirt=(0.1, 0.25, 0.75), shorts=(0.1, 0.25, 0.75), keeper=(0.95, 0.8, 0.1)),
              dict(shirt=(0.95, 0.95, 0.95), shorts=(0.1, 0.1, 0.12), keeper=(0.2, 0.2, 0.25))),
        first='p2',
        results={'p1': [True, True, True, True], 'p2': [True, True, False, True, True]},
        role='kick',
        intro=('Champions League final in the Moscow rain. Petr Cech saved from Ronaldo. Score this '
               'and Chelsea win the Champions League for the first time.'),
        history=('John Terry slipped as he struck it and hit the post. Manchester United won 6-5 '
                 'in sudden death.'),
        weather='rain',
    ),
    dict(
        key='basel25',
        title='Basel 2025',
        teams=('England', 'Spain'),
        kits=(dict(shirt=(0.95, 0.95, 0.95), shorts=(0.1, 0.15, 0.4), keeper=(0.15, 0.6, 0.3)),
              dict(shirt=(0.85, 0.1, 0.12), shorts=(0.1, 0.15, 0.45), keeper=(0.95, 0.8, 0.1))),
        first='p1',
        results={'p1': [False, True, True, False], 'p2': [False, False, True, False]},
        role='kick',
        intro=('Women\'s Euro final, 1-1 after extra time. Hannah Hampton has kept England in it. '
               'Spain have just missed again: score this and England are champions of Europe.'),
        history='Chloe Kelly smashed it in. England won 3-1 on penalties.',
    ),
]


def _valid(sc):
    try:
        ok = (isinstance(sc['key'], str) and isinstance(sc['title'], str) and len(sc['teams']) == 2
              and len(sc['kits']) == 2 and sc['first'] in ('p1', 'p2') and sc['role'] in ('kick', 'keep')
              and all(isinstance(r, bool) for s in ('p1', 'p2') for r in sc['results'][s]))
        for kit in sc['kits']:
            for part in ('shirt', 'shorts', 'keeper'):
                if len(kit[part]) != 3:
                    return False
        return ok and isinstance(sc.get('intro', ''), str) and isinstance(sc.get('history', ''), str)
    except (KeyError, TypeError):
        return False


def load_mods(directory=MOD_DIR, teams=None):
    """Add famous shootouts (and team kits) from JSON files in the mods folder.
    A file holds {"scenarios": [...]} and/or {"teams": [...]}, using the same
    fields as the built-in ones. Bad entries are skipped. Returns how many
    were added."""
    added = 0
    try:
        names = sorted(f for f in os.listdir(directory) if f.endswith('.json'))
    except OSError:
        return 0
    for name in names:
        try:
            with open(os.path.join(directory, name)) as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        for sc in data.get('scenarios', []) if isinstance(data, dict) else []:
            if _valid(sc) and all(s['key'] != sc['key'] for s in SCENARIOS):
                sc = dict(sc, teams=tuple(sc['teams']), kits=tuple(
                    {k: tuple(v) for k, v in kit.items()} for kit in sc['kits']))
                sc.setdefault('intro', '')
                sc.setdefault('history', '')
                SCENARIOS.append(sc)
                added += 1
        if teams is not None and isinstance(data, dict):
            for t in data.get('teams', []):
                try:
                    team = dict(name=str(t['name'])[:12].upper(), shirt=tuple(t['shirt']),
                                shorts=tuple(t['shorts']), keeper=tuple(t['keeper']))
                except (KeyError, TypeError):
                    continue
                if all(len(team[k]) == 3 for k in ('shirt', 'shorts', 'keeper')):
                    teams.append(team)
                    added += 1
    return added


def really_lost(sc):
    """Did the side you play lose this shootout in real life?"""
    if 'really_lost' in sc:
        return bool(sc['really_lost'])
    return f"{sc['teams'][1]} won" in sc.get('history', '')


def by_key(key):
    for s in SCENARIOS:
        if s['key'] == key:
            return s
    return SCENARIOS[0]
