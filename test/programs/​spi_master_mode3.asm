.wrap_bot 0
.wrap_top 11
SETX 8
spi3_loop:
SETP 1, 0
IN 0, MSB
SETP 1, 1
JMP YNZ, spi3_loop
PUSH
HALT
