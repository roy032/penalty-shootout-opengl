# Penalty Shootout (OpenGL)

A 3D penalty shootout written in Python with PyOpenGL and GLUT. Play against the computer or a friend on one keyboard, on a pitch built to real-world dimensions under the floodlights.

![Aiming at the top corner](docs/screenshot-aim.png)

## What makes it play like a real shootout

**Taking the kick**
- **Aim, power and timing.** Move a reticle anywhere on the goal mouth (or off it), pick a shot type, then stop the power bar during the run-up. Green is the sweet spot; over-hit it and the ball climbs over the bar. Aim tight to a post and you might hit it, or miss altogether.
- **Seven shot types.** Placed, Driven, Curler, Chip / Panenka, Knuckleball (no spin, wobbles late, hard to hold), Skidder (low, fizzes off the turf) and the Stutter (hop, wait for the keeper to move, roll it the other way: slow if he holds his ground).
- **Body shape gives you away.** Your hips open towards where you are aiming during the run-up, and both human and computer keepers can read it. Disguise the run-up to stay closed, at a small cost in accuracy.
- **Composure.** Rushing the kick straight after the whistle makes it shakier; a calm breath helps; dithering lets the crowd get to you. A breathing indicator shows where you are.
- **Slips and double touches.** A worn spot, a wet pitch or an over-hit drive can make your plant foot go. A slip skews the ball, and a double touch is ruled out by VAR.
- **The long walk.** Each taker walks from the halfway line (skippable), towards his own fans' roar or the away end's whistles. Everyone kicks once before anyone kicks twice; after ten outfielders, the goalkeeper steps up.

**Keeping goal**
- **Guess, or react late.** Pick a dive before the kick (it stays hidden), or wait for a split second of reaction after contact. Feet can save a shot down the middle.
- **Mind games.** Shuffle along the line to make one side look bigger, fake a lean, or wave your arms. Overdo it and the referee books you; leave your line early and VAR orders a retake. Two yellows and an outfield player has to go in goal.
- **Specialist sub.** Before the shootout, bring on a penalty-specialist keeper with a longer reach (but he is a worse kicker).
- **Momentum.** Saves give a keeper confidence; misses make the next kicker more nervous. Keepers celebrate saves with a dance.

**Atmosphere**
- **Home and away ends.** The toss winner chooses which end. The fans behind the goal wear their team's colours, do a Mexican wave, unfurl a tifo, wave flags and jump around to put off the away kicker.
- **Weather and time of day.** Rain (skidding ball, slippery spot, spilled catches), wind (drift, worst on chips), snow (orange ball), fog, and day or night with floodlights, phone torches and flares.
- **The full cast.** A referee who shows cards, an assistant on the goal line, both squads arm in arm on the halfway line reacting to every kick, and the kicker's celebration of your choice.

**Modes**
- **Player v CPU** and **Player v Player** on one keyboard: 3, 5 or 10 kicks each, or sudden death only.
- **Famous shootouts**: Belgrade 1976, Berlin 2006, Lusail 2022, Wembley 2021, Istanbul 2005 (you are in goal) and Munich 2012, each picked up at the deciding kick with a history card before and after. Only team names and kit colours are used.
- **90th-minute penalty**: 1-1 in normal time, and rebounds are live.
- **Party** for 3 to 8 friends: King of the Goal, or a knockout bracket of quick shootouts.
- **Training ground**: a trajectory preview, an all-time success heatmap by zone, and a drill machine that fires at the zone you pick when you keep.

**Presentation**
- **Cameras**: broadcast, behind the goal, side, a keeper's-eye view with your gloves in shot, and a free orbit. Replays slow right down at saves and post hits, with net, ball and side cameras.
- **Saved replays and clips**: save a shootout as a small replay file that re-simulates every kick (`--replay FILE` to watch), or export the replay as a GIF.
- **Accessibility**: scoreboard ticks and crosses as well as colours, a relaxed timing assist (slower power bar, wider sweet spot), captions for sound cues, and rebindable keys.
- **Private aiming for PvP**: a gamepad rumbles to tell the kicker where the hidden aim is, or the kicker can aim on a phone.
- **Sound and stats**: whistle, kick, the clang of the post, crowd roars, gasps and jeers, a heartbeat on must-score kicks, and your career record saved between sessions.

## How to Run

Requires Python 3.8+ and an OpenGL-capable system with GLUT (freeglut).

```bash
pip install -r requirements.txt
python penalty_shootout.py
```

`pygame` is used for sound and gamepads. Without it the game runs silently and keyboard-only. `Pillow` is optional and turns exported clips into GIFs (without it, clips are saved as a folder of frames). `PyOpenGL_accelerate` is optional and can be installed separately for better performance.

To watch a saved replay: `python penalty_shootout.py --replay ~/.penalty_shootout/replays/shootout-....json`

**GLUT library**

- Linux: install freeglut from your package manager, for example `sudo apt install freeglut3-dev` on Debian/Ubuntu.
- Windows: the PyOpenGL package from pip does not include the GLUT DLL, so `glutInit` fails with `NullFunctionError`. Download a Windows build of freeglut and copy `freeglut.dll` (64-bit for 64-bit Python) next to `python.exe` or into `C:\Windows\System32`.
- macOS: the system GLUT framework is used.

## Controls

**Menu**: `W`/`S` move, `A`/`D` change, `Enter`/`Space` kick off, `K` rebind keys. The mouse works too.

**Match** (default keys; rebind them from the menu)

| | Player 1 | Player 2 |
|---|---|---|
| Aim (kicking) / dive (keeping) | `W` `A` `S` `D` | `I` `J` `K` `L` |
| Start run-up, then set power | `Space` | `Enter` |
| Shot type (kicking) / wave arms (keeping) | `E` | `O` |
| Disguise run-up (kicking) / shuffle along the line (keeping) | `Q` | `U` |
| Change celebration (after scoring) / fake lean (keeping) | `X` | `M` |

When keeping, left and right pick the dive, down stays in the centre and up toggles a high or low dive. In party modes the kicker always uses Player 1's keys and the keeper Player 2's.

| Key | Action |
|-----|--------|
| `C` | Change camera (in a replay: net, ball or side camera) |
| `T` | Trajectory preview on/off (training) |
| `H` | How to play |
| `N` | Sound on / off |
| `P` | Pause (then `R` restart, `M` menu) |
| `V` / `F` / `G` | After the match: watch the replay, save a replay file, save a GIF clip |
| `Esc` | Quit |

**Gamepads**: pad 1 plays as Player 1 and pad 2 as Player 2. Stick or d-pad aims and dives, A shoots, B is shot type / wave, X disguise / shuffle, Y celebrate / fake, Start pauses and Back changes camera. With hidden aim, the kicker's pad rumbles more towards the posts and the bar.

**Phone controller**: switch it on in the menu and the game shows an address and a PIN. Open the address on a phone on the same network, enter the PIN, and aim by touch so your opponent cannot see where you are going. The server only runs while the setting is on.

**Hidden aim (PvP):** with both players on one screen, the kicker's reticle is hidden by default so the keeper cannot see it. You still move it from the centre with your aim keys, so you aim by feel (or with rumble, or on a phone). The keeper's choice is never shown in PvP.

## Difficulty (PvC)

| | Easy | Medium | Hard |
|---|---|---|---|
| Computer keeper reads your body shape | 15% | 30% | 35% |
| Keeper reach and speed | Short, slow | Medium | Long, quick |
| Computer kicker accuracy | Wild | Good | Sharp |
| Kicker exploits your favourite dive | No | A little | Yes |

When it doesn't read you, the computer keeper leans towards the side you have favoured. Computer kickers have personalities (the Placer, the Blaster, the Artist) with different shot choices and a natural side. `python tools/balance.py` prints simulated conversion rates; real shootouts convert roughly three kicks in four.

## Project Structure

```
├── penalty_shootout.py     # Entry point
├── shootout/
│   ├── config.py           # Pitch dimensions (metres), shot types, difficulty
│   ├── rules.py            # Shootout scoring and sudden death
│   ├── physics.py          # Ball flight, posts, net, shot error
│   ├── keeper.py           # Dives and the keeper's body for saves
│   ├── kick.py             # One kick in flight and the referee's call
│   ├── ai.py               # Computer kicker and keeper
│   ├── game.py             # Match flow and input (no OpenGL)
│   ├── modes.py            # Shootout, training, 90th-minute pen, party formats
│   ├── scenarios.py        # Famous shootouts
│   ├── controls.py         # Key bindings (rebindable, saved to a file)
│   ├── audio.py            # Procedural sound effects
│   ├── stats.py            # Career stats and the training heatmap
│   ├── render.py           # 3D scene, crowd and weather
│   ├── hud.py              # Scoreboard, menus, banners, captions
│   ├── gamepad.py          # Gamepads and rumble (optional, via pygame)
│   ├── phone.py            # Phone controller web page (optional)
│   └── app.py              # GLUT window, cameras, clip export
├── tests/                  # pytest suite (runs without a display)
└── tools/balance.py        # Conversion-rate simulation
```

Run the tests with `pip install pytest && pytest`.
