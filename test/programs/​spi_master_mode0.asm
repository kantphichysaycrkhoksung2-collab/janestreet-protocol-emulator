.wrap_bot 0
.wrap_top 11
SETX 8
spi0_loop:
IN 0, MSB
SETP 1, 1
SETP 1, 0
JMP YNZ, spi0_loop
PUSH
HALT
