.wrap_bot 0
.wrap_top 13
SETX 8
rd_loop:
IN 0, MSB
SETP 1, 1
SETP 1, 0
JMP YNZ, rd_loop
PUSH
SETP 0, 0
SETP 1, 1
SETP 1, 6
SETP 0, 1
HALT
