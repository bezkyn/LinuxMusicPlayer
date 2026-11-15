#!/usr/bin/env python3
"""Imprime a versão do programa (o __version__ do linux-music-player.py)."""
import os
import re

raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(raiz, "linux-music-player.py"), encoding="utf-8") as fh:
    print(re.search(r'^__version__ = "([^"]+)"', fh.read(), re.M).group(1))
