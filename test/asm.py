#!/usr/bin/env python3
"""Assembler for the protocol-emulator mini engine (see src/Mini_engine.v).

Source syntax (one statement per line, ';' starts a comment):

    .equ SDA 0              ; named constant
    .wrap_bot               ; PC wraps to the next instruction ...
    .wrap_top               ; ... after the previous instruction executes
    label:
        MNEMONIC operands

Mnemonics
    DLY n                   idle n extra steps (instruction takes n+1 steps)
    SETP pin, v             push-pull drive pin to v
    SETD pin, v             open-drain: v=0 drive low, v=1 release   (pin 0-7)
    SETOE mask              uio output-enable mask
    WAITP pin, v            stall until pin == v
    JMP cond, label         cond: ALWAYS XNZ(X!=0, X--) YNZ(Y!=0, Y--) TXE OSR0 OSR7
    JMPH pin, label         jump if pin high (pin 0-7)
    JMPL pin, label         jump if pin low  (pin 0-7)
    PULL / PUSH / HALT
    OUT pin [, MSB] [, OD]  shift OSR to pin; MSB = MSB-first, OD = open-drain
    IN pin [, MSB]          shift pin into ISR; MSB = MSB-first
    SETX n / SETY n / SETO n (OSR) / SETI n (ISR) / SETF n (flags)

Command line:
    python3 asm.py prog.asm            listing + wrap info
    python3 asm.py prog.asm --c NAME   C array (for the RP2350 host)
    python3 asm.py prog.asm --py NAME  Python list
"""
import argparse
import re
import sys

OPS = dict(DLY=0, SETP=1, SETOE=2, WAITP=3, JMP=4, PULL=5, PUSH=6, OUT=7, IN=8,
           SETX=9, SETY=10, SETO=11, SETF=12, HALT=13, SETD=14, SETI=15)
CONDS = dict(ALWAYS=0, XNZ=1, YNZ=2, TXE=3, PINH=4, PINL=5, OSR0=6, OSR7=7)
MODS = dict(MSB=1, OD=2)
IMEM_WORDS = 32


class AsmError(Exception):
    pass


class Program:
    def __init__(self, words, wrap_bot, wrap_top, labels, listing):
        self.words, self.wrap_bot, self.wrap_top = words, wrap_bot, wrap_top
        self.labels, self.listing = labels, listing

    def __iter__(self):
        return iter((self.words, self.wrap_bot, self.wrap_top))


def assemble(src, name='<asm>'):
    equ, labels, prog = {}, {}, []
    wrap_bot, wrap_top = 0, IMEM_WORDS - 1

    def num(tok, lineno):
        tok = tok.strip()
        if tok in equ:
            return equ[tok]
        try:
            return int(tok, 0)
        except ValueError:
            raise AsmError('%s:%d: bad number or unknown symbol %r' % (name, lineno, tok))

    for lineno, raw in enumerate(src.splitlines(), 1):
        line = raw.split(';')[0].strip()
        if not line:
            continue
        if line.endswith(':'):
            labels[line[:-1].strip()] = len(prog)
            continue
        if line.startswith('.'):
            parts = line.split()
            if parts[0] == '.equ':
                equ[parts[1]] = int(parts[2], 0) if parts[2] not in equ else equ[parts[2]]
            elif parts[0] == '.wrap_bot':
                wrap_bot = len(prog)
            elif parts[0] == '.wrap_top':
                wrap_top = len(prog) - 1
            else:
                raise AsmError('%s:%d: unknown directive %s' % (name, lineno, parts[0]))
            continue
        mn, _, rest = line.partition(' ')
        mn = mn.upper()
        args = [a.strip() for a in re.split(r'[,|]', rest) if a.strip()]
        prog.append((mn, args, lineno, raw.strip()))

    if len(prog) > IMEM_WORDS:
        raise AsmError('%s: program has %d words, instruction memory holds %d' % (name, len(prog), IMEM_WORDS))
    words, listing = [], []
    for addr, (mn, args, lineno, raw) in enumerate(prog):
        def err(msg):
            return AsmError('%s:%d: %s' % (name, lineno, msg))

        def need(n):
            if len(args) < n:
                raise err('%s needs %d operand(s)' % (mn, n))

        a = imm = 0
        if mn in ('SETP', 'WAITP', 'SETD'):
            need(2)
            a, imm = num(args[0], lineno), num(args[1], lineno)
            if imm not in (0, 1):
                raise err('value must be 0 or 1')
            op = OPS[mn]
        elif mn == 'JMP':
            need(2)
            cname = args[0].upper()
            if cname not in CONDS or cname in ('PINH', 'PINL'):
                raise err('bad JMP condition %r (use JMPH/JMPL for pins)' % args[0])
            a = CONDS[cname]
            if args[1] not in labels and not re.match(r'^\w+$', args[1]):
                raise err('bad label')
            imm = ('label', args[1])
            op = OPS['JMP']
        elif mn in ('JMPH', 'JMPL'):
            need(2)
            pin = num(args[0], lineno)
            if not 0 <= pin <= 7:
                raise err('JMPH/JMPL pin must be 0-7')
            a = CONDS['PINH' if mn == 'JMPH' else 'PINL']
            imm = ('label', args[1], pin)
            op = OPS['JMP']
        elif mn in ('OUT', 'IN'):
            need(1)
            a = num(args[0], lineno)
            for m in args[1:]:
                if m.upper() not in MODS:
                    raise err('unknown modifier %r' % m)
                if mn == 'IN' and m.upper() == 'OD':
                    raise err('IN has no OD modifier')
                imm |= MODS[m.upper()]
            op = OPS[mn]
        elif mn in ('PULL', 'PUSH', 'HALT'):
            op = OPS[mn]
        elif mn in ('DLY', 'SETOE', 'SETX', 'SETY', 'SETO', 'SETI', 'SETF'):
            need(1)
            imm = num(args[0], lineno)
            if not 0 <= imm <= 255:
                raise err('immediate out of range 0..255')
            op = OPS[mn]
        else:
            raise err('unknown mnemonic %r' % mn)
        if not 0 <= a <= 15:
            raise err('pin/condition out of range')
        if isinstance(imm, tuple):
            if imm[1] not in labels:
                raise err('undefined label %r' % imm[1])
            tgt = labels[imm[1]]
            if tgt >= IMEM_WORDS:
                raise err('label %r is past the end of instruction memory' % imm[1])
            imm = tgt | ((imm[2] << 5) if len(imm) > 2 else 0)
        word = (op << 12) | (a << 8) | imm
        words.append(word)
        listing.append('%02d: %04X  %s' % (addr, word, raw))
    return Program(words, wrap_bot, wrap_top, labels, listing)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('file')
    ap.add_argument('--c', metavar='NAME')
    ap.add_argument('--py', metavar='NAME')
    a = ap.parse_args()
    p = assemble(open(a.file).read(), a.file)
    if a.c:
        print('static const uint16_t %s[%d] = {%s};' % (a.c, len(p.words), ', '.join('0x%04X' % w for w in p.words)))
        print('#define %s_WRAP_BOT %d\n#define %s_WRAP_TOP %d' % (a.c.upper(), p.wrap_bot, a.c.upper(), p.wrap_top))
    elif a.py:
        print('%s = dict(words=[%s], wrap_bot=%d, wrap_top=%d)' % (
            a.py, ', '.join('0x%04X' % w for w in p.words), p.wrap_bot, p.wrap_top))
    else:
        print('\n'.join(p.listing))
        print('; %d words, wrap_bot=%d wrap_top=%d' % (len(p.words), p.wrap_bot, p.wrap_top))


if __name__ == '__main__':
    try:
        main()
    except AsmError as e:
        sys.exit(str(e))
