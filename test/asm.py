# SPDX-License-Identifier: Apache-2.0
# Assembler for the protocol emulator microcode engine.

import sys

OPS = {
    'DLY': 0, 'SETP': 1, 'SETOE': 2, 'WAITP': 3,
    'JMP': 4, 'PULL': 5, 'PUSH': 6, 'OUT': 7,
    'IN': 8, 'SETX': 9, 'SETY': 10, 'SETO': 11,
    'SETF': 12, 'HALT': 13, 'SETD': 14, 'SETI': 15
}

CONDS = {
    'ALWAYS': 0, 'XNZ': 1, 'YNZ': 2, 'TXE': 3,
    'PINH': 4, 'PINL': 5, 'OSR0': 6, 'OSR7': 7
}

def assemble_line(line, labels):
    parts = line.replace(',', ' ').split()
    if not parts:
        return None
    
    op_str = parts[0].upper()
    if op_str not in OPS:
        raise ValueError(f"Unknown mnemonic: {op_str}")
    
    op = OPS[op_str]
    a = 0
    imm = 0
    
    if op == OPS['DLY']:
        imm = int(parts[1], 0)
    elif op == OPS['SETP']:
        a = int(parts[1], 0)
        imm = int(parts[2], 0) & 1
    elif op == OPS['SETOE']:
        imm = int(parts[1], 0) & 0xFF
    elif op == OPS['WAITP']:
        a = int(parts[1], 0)
        imm = int(parts[2], 0) & 1
    elif op == OPS['JMP']:
        c_str = parts[1].upper()
        if c_str in CONDS:
            a = CONDS[c_str]
        else:
            a = int(c_str, 0)
        target = parts[2]
        imm = labels[target] if target in labels else int(target, 0)
        imm &= 0x1F
    elif op in (OPS['PULL'], OPS['PUSH'], OPS['HALT']):
        pass
    elif op == OPS['OUT'] or op == OPS['IN']:
        a = int(parts[1], 0)
        for mod in parts[2:]:
            mod = mod.upper()
            if mod == 'MSB':
                imm |= 1
            elif mod == 'OD':
                imm |= 2
    elif op in (OPS['SETX'], OPS['SETY'], OPS['SETO'], OPS['SETF'], OPS['SETI']):
        imm = int(parts[1], 0) & 0xFF
    elif op == OPS['SETD']:
        a = int(parts[1], 0)
        imm = int(parts[2], 0) & 1
        
    return (op << 12) | ((a & 0xF) << 8) | (imm & 0xFF)

def assemble(text, name="<inline>"):
    lines = []
    labels = {}
    pc = 0
    wrap_bot = 0
    wrap_top = 0
    
    for raw_line in text.splitlines():
        line = raw_line.split('#')[0].strip()
        if not line:
            continue
        if line.endswith(':'):
            lbl = line[:-1].strip()
            labels[lbl] = pc
            continue
        if line.startswith('.'):
            parts = line.split()
            if parts[0] == '.wrap_bot':
                wrap_bot = int(parts[1], 0)
            elif parts[0] == '.wrap_top':
                wrap_top = int(parts[1], 0)
            continue
        lines.append(line)
        pc += 1
        
    words = []
    for line in lines:
        w = assemble_line(line, labels)
        if w is not None:
            words.append(w)
            
    return words, wrap_bot, wrap_top

if __name__ == '__main__':
    if len(sys.argv) > 1:
        text = open(sys.argv[1]).read()
        words, wb, wt = assemble(text, sys.argv[1])
        print(f"Assembled {len(words)} words, wrap_bot={wb}, wrap_top={wt}")
