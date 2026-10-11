# Pilot: front-view aircraft outline

The current assistant icon is a simple blue outline of an aircraft viewed from
the front: rounded nose, cockpit windows, two wings and engines. It has no
mascot face, beard, captain hat, pixel rendering, image border or button frame.

Asset: `assets/pilot-aircraft.svg`. It is a hand-authored vector with a transparent
background, no external resources or scripts, and remains crisp at small sizes.
The component embeds it once as an `image/svg+xml` data URI and shares it between
the 52 px launcher image and the 38 px chat header image.

The 64 × 64 px launcher, Pilot label, authentication, dragging, keyboard controls
and chat behavior retain their existing implementation. The decorative images
have empty alt text and are hidden from assistive technology; the button retains
its accessible name and keyboard focus outline.
