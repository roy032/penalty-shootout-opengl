"""The coach's report after a match: patterns in how the human played."""


def _pct(a, b):
    return f'{round(100 * a / b)}%' if b else '-'


def coach_report(log, human_slots):
    """Short lines of analysis from the kick log. Each log entry has side,
    scored, aim (x, y), composure, runup, kind, keeper_dir and keeper_side."""
    lines = []
    mine = [k for k in log if k['side'] in human_slots and k.get('aim')]
    if mine:
        left = sum(1 for k in mine if k['aim'][0] < -0.8)
        right = sum(1 for k in mine if k['aim'][0] > 0.8)
        n = len(mine)
        if max(left, right) >= 3 and max(left, right) >= 0.7 * n:
            side = "keeper's right" if left > right else "keeper's left"
            lines.append(f'You went to the {side} {max(left, right)} times out of {n}: a good keeper will spot that.')
        rushed = sum(1 for k in mine if k.get('composure') == 'rushed')
        if rushed:
            lines.append(f'You rushed {rushed} kick(s) straight after the whistle; '
                         f'they scored {_pct(sum(k["scored"] for k in mine if k.get("composure") == "rushed"), rushed)}.')
        settled = [k for k in mine if k.get('composure') == 'settled']
        if settled:
            lines.append(f'Settled kicks scored {_pct(sum(k["scored"] for k in settled), len(settled))}.')
        disguised = [k for k in mine if k.get('runup') == 'disguised']
        if disguised:
            lines.append(f'Disguised run-ups scored {_pct(sum(k["scored"] for k in disguised), len(disguised))}.')
        high = [k for k in mine if k['aim'][1] > 1.5]
        if high:
            lines.append(f'Kicks aimed high scored {_pct(sum(k["scored"] for k in high), len(high))}.')
    faced = [k for k in log if k.get('keeper_side') in human_slots]
    if faced:
        dives = [k.get('keeper_dir') for k in faced]
        stays = sum(1 for d in dives if d == 0)
        waits = sum(1 for d in dives if d is None)
        saves = sum(1 for k in faced if not k['scored'] and k['label'].startswith(('SAVED', 'CAUGHT')))
        lines.append(f'In goal you saved {saves} of {len(faced)}.')
        if waits >= 2:
            lines.append(f'You waited and reacted {waits} times: reacting is usually too late.')
        if stays == 0 and len(faced) >= 4:
            lines.append('You never stayed in the middle. Watch out for the Panenka.')
    if not lines:
        lines.append('Not enough kicks to spot a pattern yet.')
    return lines[:6]
