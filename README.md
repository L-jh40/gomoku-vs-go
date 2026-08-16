# Gomoku vs Go (windowed AI-vs-AI)

This folder contains a complete new implementation of the hybrid game.

## Run

```powershell
cd gomoku-vs-go2
python main.py
```

Command-line self-play:

```powershell
python main.py --cli
python main.py --size 19
```

Dependencies: Python 3.9+ with `numpy` and `tkinter`.

## Files

| File | Purpose |
|------|---------|
| `board.py` | board state, Go capture, white-territory/dead cells, red threat classification, exact candidate ranges, scoring |
| `rules.py` | Renju fouls (overline / four-four / three-three) and line-pattern threat classification |
| `ai_search.py` | White forced-defence recursion, Black Algorithm A, minimax/alpha-beta, farthest-open fallback |
| `ai_black.py` / `ai_white.py` | thin public wrappers |
| `gui.py` | windowed AI-vs-AI application, pass, resign + black-win replay dialog |
| `main.py` | GUI / CLI entry point |

## Board injection helper

Tests can inject a pattern and use AI functions without a GUI:

```python
from board import HybridBoard, WHITE, BLACK
import ai_black, ai_white, ai_search

b = HybridBoard(15)
b.load_centered([
    "0002B00",
    "0021200",
    "0211120",
    "2111120",
    "C222A00",
])
# White to move: b.load_centered leaves history empty and no turn state,
# so call the AI for the desired side directly:
move = ai_white.best_white_move(b, time_limit=10, max_depth=2)
```

`white_should_pass(b)` distinguishes pass from resignation when
`best_white_move` returns `None`.

## Exact marker scoring

| Marker | Threat | Score |
|--------|--------|-------|
| solid circle | five point | handled before scoring |
| triangle | four-three / open four | 625 |
| hollow triangle | fragile four-three / open four | 250 |
| large circle | rush four / open three | 125 |
| small circle | sleep three / open two | 25 |
| red dot | sleep two | 1 |
| territory | empty dead cell or dead black cell | -1 |

Black group score is `A * (1 - 0.5 ** n)` where `n` is the group's liberty
count and `A` is the red-position score lost if the group vanished.
