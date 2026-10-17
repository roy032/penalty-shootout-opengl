"""Famous shootouts, picked up at the moment the deciding kick is due.

You always play team 'p1'. Results are in kicking order for each side
(True = scored). Only team names and kit colours are used.
"""

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
]


def by_key(key):
    for s in SCENARIOS:
        if s['key'] == key:
            return s
    return SCENARIOS[0]
