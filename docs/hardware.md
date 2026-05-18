# Hardware and Assembly

This guide covers the original hardware design, wiring concept, and enclosure assembly.

## Bill of Materials

| Qty | Code | Description |
| --- | --- | --- |
| 1 | [XC9001](http://jaycar.com.au/p/XC9001) | Raspberry Pi 3B+ |
| 1 | [XC9020](http://jaycar.com.au/p/XC9020) | Raspberry Pi Camera |
| 1 | [LA5077](http://jaycar.com.au/p/LA5077) | Narrow Fail-Safe Door Strike |
| 1 | [WC6026](http://jaycar.com.au/p/WC6026) | Cables |
| 1 | [XC4514](http://jaycar.com.au/p/XC4514) | Power supply module |
| 1 | [XC4419](http://jaycar.com.au/p/XC4419) | Relay board |
| 1 | [PT3002](http://jaycar.com.au/p/PT3002) | 4-way terminal block |
| 1 | [HB6251](http://jaycar.com.au/p/HB6251) | Waterproof enclosure |
| 1+ | [HM9509](https://jaycar.com.au/p/HM9509) | Acrylic sheet |

The original build uses the [XC4514](https://jaycar.com.au/p/XC4514) with a 12V power supply to provide power to both the door strike and the Raspberry Pi.

You may also need:

- Raspberry Pi power supply, such as [MP3536](https://jaycar.com.au/p/MP3536).
- 12V power source for the door strike.
- [XC9021](https://jaycar.com.au/p/XC9021) night vision camera.
- [WC7756](https://jaycar.com.au/p/WC7756) micro USB extension lead.

## System Overview

![system overview](../images/system.png)

The Raspberry Pi camera watches the door area and detects faces. When a face is detected, the software checks whether that identity is known and allowed:

- Known and allowed: activate the relay and unlock the door.
- Known and denied: keep the door locked.
- Unknown: save a new identity and keep the door locked.

The web UI shows detected identities and lets you allow, deny, rename, merge, or delete them.

![web interface](../images/screenshot.png)

## Wiring

The general schematic uses the [XC4514](https://jaycar.com.au/p/XC4514) to power the Raspberry Pi from the same supply as the relay and door strike. A 4-way terminal block makes mounting and connecting cables easier.

![schematic](../images/schematic.png)

The software controls the relay from the Raspberry Pi GPIO pin configured by `DOORLOCK_RELAY_PIN`.

## Cut Acrylic

The [HB6251](https://jaycar.com.au/p/HB6251) enclosure is 80 mm wide, so cut an acrylic panel at least 80 mm wide so it can fit into the case.

Mark a straight line 80 mm from the edge of the acrylic and score the line with a knife. It works better if you score both sides.

![cutting acrylic](../images/cut.jpg)

Place the scored line on the edge of a bench or table and press down until the acrylic snaps cleanly.

![force](../images/push.jpg)

Use spare acrylic if needed; it can take a few tries to get a clean edge.

## Prepare Regulator

The regulator is adjustable and should be set to 5.0-5.1V before connecting it to the Raspberry Pi.

It is safer to power the Pi through a micro USB connector than directly through the 5V pins. You can use a cut cable or an extension lead such as [WC7756](https://jaycar.com.au/p/WC7756).

![Adjusting the regulator](../images/voltage.jpg)

This step is optional if you power the Pi separately.

## Mounting

Use double-sided tape, screws, or nylon washers to mount the regulator, relay, and camera onto the acrylic base.

![mounting](../images/mount.jpg)

The camera can be attached last once it is connected to the Raspberry Pi.

Secure loose power wiring with zip ties or hot glue so it cannot move inside the enclosure.

## Terminal Block

Drill four holes in the housing to line up with each terminal. If you want better splash protection, place the holes on the underside of the wall-mounted unit.

![terminals](../images/terminals.png)

One red/black pair should be power input and the other should be output for the latch. Mark these clearly once mounted.

![prepare](../images/prepare.jpg)

There are two wiring styles:

- General: the relay shorts the latch terminals when activated.
- 12V active: the latch terminals provide 12V when activated.

Choose the wiring style based on whether your door strike has its own supply or uses the supply inside the enclosure.

![two connection types](../images/case.png)

Once the hardware is mounted, fit the acrylic sheet into the enclosure and test the relay before final installation.

![Connected up](../images/power.jpg)
