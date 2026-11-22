.wrap_target
JMP TXE, done
PULL
SETX 8
spi3_loop:
SETP 1, 0
IN 0, MSB
SETP 1, 1
JMP XNZ, spi3_loop
PUSH
.wrap
done:
HALT
