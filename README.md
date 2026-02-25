# Penalty Shootout — OpenGL Game

A 3D penalty kick shootout game built with **Python** and **OpenGL (PyOpenGL + GLUT)**. Features PvP and PvC modes, an interactive aiming system, AI goalkeeper with adaptive difficulty, and a full match simulation with sudden death.

## Gameplay

- **Player vs Player (PvP)** — Two players alternate between shooting and goalkeeping
- **Player vs Computer (PvC)** — Play against an AI opponent with adjustable difficulty
- **5 shots per player**, followed by sudden death if tied
- Interactive aiming with accuracy mechanics and camera shake effects

## Controls

| Key | Action |
|-----|--------|
| Arrow Keys | Aim the shot / Move goalkeeper |
| Mouse Click | Confirm shot |
| `P` | Pause / Resume |
| `R` | Restart match |
| `ESC` | Quit |

## Features

- 3D rendered football pitch, goal, ball, and players
- Animated ball trajectory and goalkeeper dives
- AI goalkeeper with configurable reaction time and reach
- Adaptive difficulty (Easy / Medium / Hard)
- Shot history tracking with scoreboard overlay
- Camera system with polar coordinate controls

## Difficulty Levels

| Parameter | Easy | Medium | Hard |
|-----------|------|--------|------|
| GK Reaction Delay | Slow | Medium | Fast |
| GK Reach | Short | Medium | Wide |
| GK Guess Accuracy | Low | Medium | High |

## Tech Stack

- Python
- PyOpenGL (OpenGL, GLUT, GLU)

## Project Structure

```
├── README.md
└── penalty_shootout.py    # Complete game source
```

## How to Run

```bash
pip install PyOpenGL PyOpenGL_accelerate
python penalty_shootout.py
```
