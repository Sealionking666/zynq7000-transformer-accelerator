.section .rodata
.balign 64
.global official_inputs
official_inputs:
.incbin "input-q16.bin"
.section .rodata
.balign 64
.global official_expected
official_expected:
.incbin "expected-logits-q16.bin"
.section .rodata
.balign 64
.global official_labels
official_labels:
.incbin "labels-i32.bin"
