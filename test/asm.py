#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assembler for the mini microcode engine (32 x 16-bit words).

Word = op[15:12] | a[11:8] | imm[7:0]
Directives: .wrap_target (next instruction = wrap bottom), .wrap (last instruction = wrap top)
Default wrap: bottom = 0, top = last instruction.
"""
import re
import sys

MAX_WORDS = 32
OPS = {"DLY": 0, "SETP": 1, "SETOE": 2, "WAITP": 3, "JMP": 4, "PULL": 5, "PUSH": 6,
       "OUT": 7, "IN": 8, "SETX": 9, "SETY": 10, "SETO": 11, "SETF": 12, "HALT": 13,
       "SETD": 14, "SETI": 15}
CONDS = {"ALWAYS": 0, "XNZ": 1, "YNZ": 2, "TXE": 3, "OSR0": 6, "OSR7": 7}
IMM_ONLY = {"DLY", "SETOE", "SETX", "SETY", "SETO", "SETI", "SETF"}
NOARG = {"PULL", "PUSH", "HALT"}


class AsmError(Exception):
    pass


def _num(tok, name, line, lo, hi, what):
    try:
        v = int(tok, 0)
    except ValueError:
        raise AsmError("%s:%d: %s: expected a number, got '%s'" % (name, line, what, tok))
    if not lo <= v <= hi:
        raise AsmError("%s:%d: %s out of range %d..%d: %d" % (name, line, what, lo, hi, v))
    return v


def assemble(text, name="<asm>"):
    """Return (words, wrap_bot, wrap_top)."""
    items, labels = [], {}
    wrap_bot, wrap_top = None, None
    for ln, raw in enumerate(text.splitlines(), 1):
        s = re.split(r";|#|//", raw)[0].strip()
        while True:
            m = re.match(r"^([A-Za-z_]\w*)\s*:\s*(.*)$", s)
            if not m:
                break
            if m.group(1) in labels:
                raise AsmError("%s:%d: duplicate label '%s'" % (name, ln, m.group(1)))
            labels[m.group(1)] = len(items)
            s = m.group(2)
        if not s:
            continue
        low = s.lower()
        if low == ".wrap_target":
            wrap_bot = len(items)
            continue
        if low == ".wrap":
            if not items:
                raise AsmError("%s:%d: .wrap before any instruction" % (name, ln))
            wrap_top = len(items) - 1
            continue
        parts = s.split(None, 1)
        mn = parts[0].upper()
        args = [a.strip() for a in parts[1].split(",")] if len(parts) > 1 else []
        if mn not in OPS and mn not in ("JMPH", "JMPL"):
            raise AsmError("%s:%d: unknown mnemonic '%s'" % (name, ln, parts[0]))
        items.append((ln, mn, args))
    if len(items) > MAX_WORDS:
        raise AsmError("%s: program has %d instructions, max %d" % (name, len(items), MAX_WORDS))

    def target(tok, ln):
        if tok in labels:
            return labels[tok]
        if re.match(r"^(0x[0-9a-fA-F]+|\d+|0b[01]+)$", tok):
            return _num(tok, name, ln, 0, MAX_WORDS - 1, "jump target")
        raise AsmError("%s:%d: unknown label '%s'" % (name, ln, tok))

    words = []
    for ln, mn, args in items:
        def need(n):
            if len(args) != n:
                raise AsmError("%s:%d: %s takes %d operand(s), got %d" % (name, ln, mn, n, len(args)))
        a = imm = 0
        if mn in NOARG:
            need(0)
        elif mn in IMM_ONLY:
            need(1)
            imm = _num(args[0], name, ln, 0, 255, mn + " operand")
        elif mn in ("SETP", "SETD"):
            need(2)
            a = _num(args[0], name, ln, 0, 7 if mn == "SETD" else 14, "output pin")
            imm = _num(args[1], name, ln, 0, 1, "value")
        elif mn == "WAITP":
            need(2)
            a = _num(args[0], name, ln, 0, 12, "input pin")
            imm = _num(args[1], name, ln, 0, 1, "value")
        elif mn == "JMP":
            need(2)
            c = args[0].upper()
            if c not in CONDS:
                raise AsmError("%s:%d: unknown condition '%s' (use %s, or JMPH/JMPL)"
                               % (name, ln, args[0], " ".join(CONDS)))
            a, imm = CONDS[c], target(args[1], ln)
        elif mn in ("JMPH", "JMPL"):
            need(2)
            p = _num(args[0], name, ln, 0, 7, "pin (0-7 for JMPH/JMPL)")
            a, imm = (4 if mn == "JMPH" else 5), (p << 5) | target(args[1], ln)
        elif mn in ("OUT", "IN"):
            if not args:
                raise AsmError("%s:%d: %s needs a pin" % (name, ln, mn))
            a = _num(args[0], name, ln, 0, 14 if mn == "OUT" else 12, "pin")
            for mod in (m.upper() for m in args[1:]):
                if mod == "MSB":
                    imm |= 1
                elif mod == "LSB":
                    pass
                elif mod == "OD" and mn == "OUT":
                    if a > 7:
                        raise AsmError("%s:%d: OD only works on pins 0-7" % (name, ln))
                    imm |= 2
                else:
                    raise AsmError("%s:%d: bad modifier '%s' for %s" % (name, ln, mod, mn))
        words.append((OPS.get(mn, 4) << 12) | (a << 8) | imm)
    if not words:
        raise AsmError("%s: empty program" % name)
    wb = 0 if wrap_bot is None else wrap_bot
    wt = len(words) - 1 if wrap_top is None else wrap_top
    if wb >= len(words) or wb > wt:
        raise AsmError("%s: bad wrap range %d..%d" % (name, wb, wt))
    return words, wb, wt


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = [a for a in argv[1:] if a.startswith("--")]
    if len(args) != 1:
        print("usage: asm.py prog.asm [--c | --py]")
        return 2
    try:
        words, wb, wt = assemble(open(args[0]).read(), args[0])
    except AsmError as e:
        print("error:", e, file=sys.stderr)
        return 1
    if "--c" in flags:
        print("static const uint16_t prog[%d] = {%s};" % (len(words), ", ".join("0x%04X" % w for w in words)))
        print("#define WRAP_BOT %d\n#define WRAP_TOP %d" % (wb, wt))
    elif "--py" in flags:
        print("PROG = [%s]\nWRAP_BOT, WRAP_TOP = %d, %d" % (", ".join("0x%04X" % w for w in words), wb, wt))
    else:
        for i, w in enumerate(words):
            print("%2d: %04X" % (i, w))
        print("wrap_bot=%d wrap_top=%d" % (wb, wt))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
