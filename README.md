# Penalty Shootout (OpenGL)

A 3D penalty shootout written in Python with PyOpenGL and GLUT. Play against the computer or a friend on one keyboard, on a pitch built to real-world dimensions under the floodlights.

![Aiming at the top corner](docs/screenshot-aim.png)

## What makes it play like a real shootout

- **Aim, power and timing.** Move a reticle anywhere on the goal mouth (or off it), pick a shot type, then stop the power bar during the run-up. Green is the sweet spot. Over-hit it and the ball climbs, so it can fly over the bar. Aim tight to a post and you might hit it, or miss altogether.
- **Four shot types.** Placed (accurate), Driven (fast but wild), Curler (bends back in), and Chip / Panenka (slow and lofted: unstoppable if the keeper dives, embarrassing if they stand still).
- **The keeper has to guess.** Real penalties are too fast to react to, so the keeper picks a dive (left, right or stay; high or low) before the kick, and it stays hidden. A correct guess still has to reach the ball: the corners, tight to the posts and under the bar, beat even a perfect dive. A keeper who waits gets a split second after contact to react, late.
- **Real ball physics.** Gravity, curl, bounces, the post and crossbar, and the net. Shots can go in off the post, in off the keeper, or bounce out off the bar.
- **Nerves.** "MUST SCORE" and "TO WIN IT" kicks, sudden death, and the keeper waving their arms all make the kicker's aim shakier.
- **Proper shootout rules.** Coin toss for who kicks first, 3, 5 or 10 kicks each, an early finish once a side cannot be caught, then sudden death.
- **Atmosphere.** A full stadium, whistle, kick, the clang of the post, crowd roars and gasps, and a heartbeat on must-score kicks (sound needs pygame).
- **Replays and stats.** The decisive kick is replayed in slow motion from behind the net. The end screen shows where every kick went, and your career record is saved between sessions.

## How to Run

Requires Python 3.8+ and an OpenGL-capable system with GLUT (freeglut).

```bash
pip install -r requirements.txt
python penalty_shootout.py
```

`pygame` is used only for sound. Without it, or without an audio device, the game runs silently. `PyOpenGL_accelerate` is optional and can be installed separately for better performance.

**GLUT library**

- Linux: install freeglut from your package manager, for example `sudo apt install freeglut3-dev` on Debian/Ubuntu.
- Windows: the PyOpenGL package from pip does not include the GLUT DLL, so `glutInit` fails with `NullFunctionError`. Download a Windows build of freeglut and copy `freeglut.dll` (64-bit for 64-bit Python) next to `python.exe` or into `C:\Windows\System32`.
- macOS: the system GLUT framework is used.

## Controls

**Menu**: `W`/`S` move, `A`/`D` change, `Enter`/`Space` kick off. The mouse works too. In the menu you choose PvC or PvP, the difficulty, the number of kicks, and (PvP only) hidden aim.

**Match**

| | Player 1 | Player 2 (PvP) |
|---|---|---|
| Aim (kicking) | `W` `A` `S` `D` | `I` `J` `K` `L` |
| Start run-up, then set power | `Space` | `Enter` |
| Change shot type (kicking) | `E` | `O` |
| Dive left / right (keeping) | `A` / `D` | `J` / `L` |
| Stay in the centre (keeping) | `S` | `K` |
| Toggle high / low dive (keeping) | `W` | `I` |
| Wave arms to put the kicker off (keeping, 3 per kick) | `E` | `O` |

| Key | Action |
|-----|--------|
| `C` | Change camera: broadcast, behind the goal, side, free orbit (arrows and Page Up/Down) |
| `H` | How to play |
| `N` | Sound on / off |
| `P` | Pause (then `R` restart, `M` menu) |
| `V` | Watch the decisive kick again (after the match) |
| `Esc` | Quit |

**Hidden aim (PvP):** with both players on one screen, the kicker's reticle is hidden by default so the keeper cannot see it. You still move it from the centre with your aim keys, so you aim by feel. The keeper's choice is never shown in PvP.

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
│   ├── audio.py            # Procedural sound effects
│   ├── stats.py            # Career stats file
│   ├── render.py           # 3D scene
│   ├── hud.py              # Scoreboard, menus, banners
│   └── app.py              # GLUT window and callbacks
├── tests/                  # pytest suite (runs without a display)
└── tools/balance.py        # Conversion-rate simulation
```

Run the tests with `pip install pytest && pytest`.
