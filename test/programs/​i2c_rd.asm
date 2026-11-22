.wrap_target
JMP TXE, done
PULL
SETX 8
rd_loop:
SETP 1, 1
IN 0, MSB
SETP 1, 0
JMP XNZ, rd_loop
PUSH
.wrap
done:
HALT
