# SPDX-License-Identifier: Apache-2.0
"""Assembler for the protocol emulator core.

Usage:  python asm.py program.asm
Prints one line per instruction: address, 16-bit hex word.
"""
import re
import sys


OPS = {
    "NOP": (0, "none"), "SET": (1, "imm"), "WAIT": (2, "imm"),
    "JMP": (3, "label"), "PUTBIT": (4, "pinmode"), "LOADX": (5, "imm"),
    "DJNZ": (6, "label"), "LOADO": (7, "imm"), "WPIN": (8, "pinlvl"),
    "GETBIT": (9, "pin"), "JPIN": (10, "jpin"), "OUTISR": (11, "none"),
    "SETPIN": (12, "pinlvl"), "DIRPIN": (13, "pinlvl"), "SETUIO": (14, "pinlvl"),
    "GETUIO": (15, "pin"),
}
DEPTH = 32


class AsmError(Exception):
    pass


def _num(tok, line_no, lo, hi, what):
    try:
        v = int(tok, 0)
    except ValueError:
        raise AsmError(f"line {line_no}: bad {what} '{tok}'")
    if not lo <= v <= hi:
        raise AsmError(f"line {line_no}: {what} {v} out of range {lo}..{hi}")
    return v


def assemble(text):
    """Return a list of 16-bit instruction words."""
    lines = []   # (line_no, mnemonic, [operands], source)
    labels = {}
    for line_no, raw in enumerate(text.splitlines(), 1):
        src = raw.split(";")[0].strip()
        while True:
            m = re.match(r"^([A-Za-z_]\w*):\s*(.*)$", src)
            if not m:
                break
            name = m.group(1)
            if name in labels:
                raise AsmError(f"line {line_no}: duplicate label '{name}'")
            labels[name] = len(lines)
            src = m.group(2)
        if not src:
            continue
        parts = src.split(None, 1)
        mnem = parts[0].upper()
        args = [a.strip() for a in parts[1].split(",")] if len(parts) > 1 else []
        if mnem not in OPS:
            raise AsmError(f"line {line_no}: unknown instruction '{parts[0]}'")
        lines.append((line_no, mnem, args, raw.strip()))

    if len(lines) > DEPTH:
        raise AsmError(f"program has {len(lines)} instructions, memory holds {DEPTH}")

    def target(tok, line_no):
        if tok in labels:
            return labels[tok]
        return _num(tok, line_no, 0, DEPTH - 1, "address")

    words = []
    for line_no, mnem, args, _ in lines:
        op, kind = OPS[mnem]
        want = {"none": 0, "imm": 1, "label": 1, "pin": 1, "pinlvl": 2, "jpin": 3,
                "pinmode": 2}[kind]
        if len(args) != want:
            raise AsmError(f"line {line_no}: {mnem} takes {want} operand(s), got {len(args)}")
        flags = imm = 0
        if kind == "imm":
            imm = _num(args[0], line_no, 0, 255, "value")
        elif kind == "label":
            imm = target(args[0], line_no)
        elif kind == "pin":
            imm = _num(args[0], line_no, 0, 7, "pin")
        elif kind == "pinlvl":
            imm = _num(args[0], line_no, 0, 7, "pin") | (_num(args[1], line_no, 0, 1, "level") << 3)
        elif kind == "pinmode":
            imm = _num(args[0], line_no, 0, 7, "pin")
            flags = _num(args[1], line_no, 0, 1, "mode")
        elif kind == "jpin":
            a = target(args[0], line_no)
            pin = _num(args[1], line_no, 0, 7, "pin")
            lvl = _num(args[2], line_no, 0, 1, "level")
            imm = a | (pin << 5)
            flags = lvl
        words.append((op << 12) | (flags << 8) | imm)
    return words


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python asm.py program.asm")
    src = open(sys.argv[1]).read()
    try:
        ws = assemble(src)
    except AsmError as e:
        sys.exit(f"error: {e}")
    for i, w in enumerate(ws):
        print(f"{i:2d}: {w:04x}")
