.wrap_target
JMP TXE, done
PULL
SETX 8
spi0_loop:
IN 0, MSB
SETP 1, 1
SETP 1, 0
JMP XNZ, spi0_loop
PUSH
.wrap
done:
HALT
