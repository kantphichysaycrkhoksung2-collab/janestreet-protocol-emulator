.wrap_bot 0
.wrap_top 13
SETX 8
wr_loop:
IN 0, MSB
SETP 1, 1
SETP 1, 0
JMP YNZ, wr_loop
PUSH
SETP 0, 0
SETP 1, 1
SETP 1, 6
SETP 0, 1
HALT
