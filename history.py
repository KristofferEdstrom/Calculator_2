"""
history.py
"""

import json
import os

HISTORY_FILE = "history.json"

history = []

def load():
    global history

    if os.path.exists(HISTORY_FILE):

        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)

    return history



def save():
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)



def add(entry):
    history.append(entry)
    save()


def clear():
    history.clear()
    save()