.wrap_target
rx_wait:
IN 8, LSB
JMP YZ, rx_wait
DLY 24
IN 8, LSB
SETX 8
rx_loop:
DLY 48
IN 8, LSB
JMP YNZ, rx_loop
PUSH
HALT
.wrap
