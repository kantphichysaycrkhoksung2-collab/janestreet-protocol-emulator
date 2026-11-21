<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->
## How it works

This project implements a reprogrammable Protocol Emulator ASIC designed for the Tiny Tapeout competition. The system architecture comprises four primary hardware modules integrated into a unified top-level design (`project.v`):

1. **Host SPI Interface (`host_spi.v`):** Acts as an SPI slave receiver, allowing an external microcontroller or host system to configure microcode, stream protocol data, and retrieve status flags synchronously.
2. **Microcode Engine (`mini_engine.v`):** A lightweight, programmable execution core that interprets custom instruction sets to dynamically manipulate incoming and outgoing protocol bitstreams.
3. **Asynchronous FIFOs & UART (`uart_fifo.v`):** Handles safe clock-domain crossing and provides serial communication streams for protocol verification and debugging.

The entire circuit is synthesized for a 25 MHz clock domain, utilizing optimized standard cells for minimal area and high reliability.

## How to test

To verify the functionality and timing behavior of the Protocol Emulator:
1. Navigate to the `test/` directory in your repository.
2. Execute the testbench using the automated Makefile command (`make`) or via `pytest` to invoke the Icarus Verilog simulation and cocotb test scripts.
3. The testbench will automatically simulate SPI master transactions, stream control commands into the SPI slave interface, execute microcode routines, and verify the resulting UART/protocol emulation output against expected reference vectors (`results.xml`).



## External hardware

List external hardware used in your project (e.g. PMOD, LED display, etc), if any
