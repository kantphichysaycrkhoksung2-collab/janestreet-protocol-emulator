.wrap_target
JMP TXE, done
PULL
SETX 8
tx_bit:
OUT 0
DLY 48
JMP XNZ, tx_bit
.wrap
done:
HALT
