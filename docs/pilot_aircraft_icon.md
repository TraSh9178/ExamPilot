# Pilot: previous robotic aircraft head

The current original robot icon is documented in `pilot_robot_icon.md` and uses
`assets/pilot-robot.svg`.

This version was an aircraft head with a robot-inspired design:
metallic blue shell, cyan cockpit eyes, mechanical wings, engine rings and a
small status light. The front-view nose and wings retain the aircraft silhouette.
It has a transparent background without an image border or button frame.

Asset: `assets/pilot-aircraft.svg`. It is a hand-authored vector with a transparent
background, internal gradients, no external resources or scripts, and remains
crisp at small sizes. The lighting is static, without blinking or animation.
The component embeds it once as an `image/svg+xml` data URI and shares it between
the 52 px launcher image and the 38 px chat header image.

The 64 × 64 px launcher, Pilot label, authentication, dragging, keyboard controls
and chat behavior retain their existing implementation. The decorative images
have empty alt text and are hidden from assistive technology; the button retains
its accessible name and keyboard focus outline.
