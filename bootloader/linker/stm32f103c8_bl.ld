/* Bootloader linker script — first 16KB of Flash */
MEMORY
{
  FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 16K
  RAM (xrw)  : ORIGIN = 0x20000000, LENGTH = 20K
}

/* Application must use a matching script with:
 *   FLASH ORIGIN = 0x08004000, LENGTH = 48K
 */
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
