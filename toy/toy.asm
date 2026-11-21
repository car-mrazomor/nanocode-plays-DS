; toy.gb - tiny test cartridge for the emulator harness (RGBDS)
; A black 8x8 square on a white screen, starting at tile (9, 8).
; D-pad moves it one tile per press (clamped to the 20x18 screen).
; A toggles an inverted palette (whole screen flips colors).
;
; build: rgbasm -o toy.o toy.asm && rgblink -o toy.gb toy.o && rgbfix -v -p 0xFF -t TOY toy.gb

DEF rP1   EQU $FF00
DEF rNR52 EQU $FF26
DEF rLCDC EQU $FF40
DEF rSCY  EQU $FF42
DEF rSCX  EQU $FF43
DEF rLY   EQU $FF44
DEF rBGP  EQU $FF47
DEF rIE   EQU $FFFF

DEF START_X EQU 9
DEF START_Y EQU 8
DEF PAL_NORMAL EQU %11100100
DEF PAL_INVERT EQU %00011011

SECTION "Vars", WRAM0
wX:    db
wY:    db
wPrev: db
wInv:  db

SECTION "Header", ROM0[$100]
    nop
    jp Start
    ds $150 - @, 0

SECTION "Main", ROM0
Start:
    di
    ld sp, $FFFE
    xor a
    ld [rIE], a
    ld [rNR52], a

.waitVBlank
    ld a, [rLY]
    cp 144
    jr c, .waitVBlank
    xor a
    ld [rLCDC], a

    ld hl, $8000
    ld b, 16
    xor a
.tile0
    ld [hl+], a
    dec b
    jr nz, .tile0
    ld b, 16
    ld a, $FF
.tile1
    ld [hl+], a
    dec b
    jr nz, .tile1

    ld hl, $9800
    ld bc, 32 * 32
.clearMap
    xor a
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, .clearMap

    ld a, START_X
    ld [wX], a
    ld a, START_Y
    ld [wY], a
    xor a
    ld [wPrev], a
    ld [wInv], a
    ld [rSCX], a
    ld [rSCY], a

    call TileAddr
    ld [hl], 1

    ld a, PAL_NORMAL
    ld [rBGP], a
    ld a, %10010001
    ld [rLCDC], a

MainLoop:
.leaveVBlank
    ld a, [rLY]
    cp 144
    jr nc, .leaveVBlank
.enterVBlank
    ld a, [rLY]
    cp 144
    jr c, .enterVBlank

    ld a, $20
    ld [rP1], a
    ld a, [rP1]
    ld a, [rP1]
    cpl
    and $0F
    swap a
    ld b, a
    ld a, $10
    ld [rP1], a
    ld a, [rP1]
    ld a, [rP1]
    ld a, [rP1]
    ld a, [rP1]
    cpl
    and $0F
    or b
    ld b, a
    ld a, $30
    ld [rP1], a

    ld a, [wPrev]
    cpl
    and b
    ld c, a
    ld a, b
    ld [wPrev], a

    call TileAddr
    ld [hl], 0

    bit 4, c
    jr z, .noRight
    ld a, [wX]
    cp 19
    jr z, .noRight
    inc a
    ld [wX], a
.noRight
    bit 5, c
    jr z, .noLeft
    ld a, [wX]
    and a
    jr z, .noLeft
    dec a
    ld [wX], a
.noLeft
    bit 6, c
    jr z, .noUp
    ld a, [wY]
    and a
    jr z, .noUp
    dec a
    ld [wY], a
.noUp
    bit 7, c
    jr z, .noDown
    ld a, [wY]
    cp 17
    jr z, .noDown
    inc a
    ld [wY], a
.noDown
    call TileAddr
    ld [hl], 1

    bit 0, c
    jr z, .noA
    ld a, [wInv]
    xor 1
    ld [wInv], a
    ld a, PAL_NORMAL
    jr z, .setPal
    ld a, PAL_INVERT
.setPal
    ld [rBGP], a
.noA
    jp MainLoop

; hl = $9800 + wY * 32 + wX
TileAddr:
    ld a, [wY]
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    ld de, $9800
    add hl, de
    ld a, [wX]
    ld e, a
    ld d, 0
    add hl, de
    ret
