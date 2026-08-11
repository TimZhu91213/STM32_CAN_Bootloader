/* Application linker script — remaining 48KB after bootloader */
MEMORY
{
  FLASH (rx) : ORIGIN = 0x08004000, LENGTH = 48K
  RAM (xrw)  : ORIGIN = 0x20000000, LENGTH = 20K
}

ENTRY(Reset_Handler)

SECTIONS
{
  .isr_vector :
  {
    KEEP(*(.isr_vector))
  } > FLASH

  .text :
  {
    *(.text*)
    *(.rodata*)
    _etext = .;
  } > FLASH

  _sidata = LOADADDR(.data);
  .data :
  {
    _sdata = .;
    *(.data*)
    _edata = .;
  } > RAM AT> FLASH

  .bss :
  {
    _sbss = .;
    *(.bss*)
    *(COMMON)
    _ebss = .;
  } > RAM
}
