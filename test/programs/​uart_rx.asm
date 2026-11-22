.wrap_target
WAITP 8, 0
DLY 24
SETX 8
rx_loop:
DLY 48
IN 8, LSB
JMP XNZ, rx_loop
PUSH
.wrap
