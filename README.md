# Penalty Shootout (OpenGL)

A 3D penalty shootout game written in Python with PyOpenGL and GLUT. Supports two-player (PvP) and player-versus-computer (PvC) modes.

## Gameplay

- **PvP**: two players on one keyboard take turns shooting and keeping goal.
- **PvC**: Player 1 plays against a computer opponent that shoots and keeps goal, with Easy, Medium and Hard difficulty.
- Each player takes 5 penalties. The match ends early once one side cannot be caught. If the score is level after 5 each, it goes to sudden death: the first player ahead after an equal number of kicks wins.
- A shot is saved if the goalkeeper is in its path; otherwise it is a goal.

## How to Run

Requires Python 3.8+ and an OpenGL-capable system with GLUT (freeglut).

```bash
pip install -r requirements.txt
python penalty_shootout.py
```

`PyOpenGL_accelerate` is optional and can be installed separately for better performance.

**GLUT library**

- Linux: install freeglut from your package manager, for example `sudo apt install freeglut3-dev` on Debian/Ubuntu.
- Windows: the PyOpenGL package from pip does not include the GLUT DLL, so `glutInit` fails with `NullFunctionError`. Download a Windows build of freeglut and copy `freeglut.dll` (64-bit for 64-bit Python) next to `python.exe` or into `C:\Windows\System32`.
- macOS: the system GLUT framework is used.

## Controls

**Menu**

| Key | Action |
|-----|--------|
| `W` / `S` | Move between Mode, Difficulty and Start |
| `A` / `D` | Change the selected option (difficulty only in PvC) |
| `Enter` / `Space` | Start the match |
| Left mouse click | Select a button |

**Match**

| Key | Action |
|-----|--------|
| `A` / `D` / `W` / `S` | Player 1 shoots: bottom-left / bottom-right / top-right / top-left |
| `J` / `L` / `I` / `K` | Player 2 shoots (PvP only): bottom-left / bottom-right / top-right / top-left |
| `A` / `D` / `W` / `S` | Player 1 in goal (when Player 2 shoots): left / right / high centre / low centre |
| `J` / `L` / `I` / `K` | Player 2 in goal (PvP only, when Player 1 shoots): left / right / high centre / low centre |
| Left / Right arrow | Rotate camera |
| Up / Down arrow | Raise / lower camera |
| `Page Up` / `Page Down` | Zoom in / out |
| `P` | Pause / resume |
| `R` | Restart the match |
| `M` | Return to menu (after the match ends) |
| `Esc` / `Q` | Quit |

The goalkeeper can move before or during the kick. In PvC the computer keeps goal against Player 1 and shoots as Player 2.

## Difficulty (PvC)

| Parameter | Easy | Medium | Hard |
|-----------|------|--------|------|
| Ball speed | Slow | Medium | Fast |
| Goalkeeper reaction delay | 350 ms | 250 ms | 150 ms |
| Goalkeeper dive reach | Short | Medium | Wide |
| Computer shot accuracy | Low | Medium | High |

The computer goalkeeper also biases its dive towards the side Player 1 has shot to most often.

## Project Structure

```
├── README.md
├── requirements.txt
└── penalty_shootout.py    # Game source
```
