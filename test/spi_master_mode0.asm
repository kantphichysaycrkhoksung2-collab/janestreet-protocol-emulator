.wrap_bot 0
.wrap_top 12
    PULL
    SETX 8
loop:
    OUT 2, MSB
    SETP 1, 1
    IN 3
    SETP 1, 0
    JMP XNZ, loop
    PUSH
    HALT
