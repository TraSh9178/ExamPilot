# Pilot: original robot icon restored

The current assistant icon is the original blue robot with an antenna, round
eyes and a smile. Its geometry is copied exactly from the `tutor-robot` SVG in
`assets/tutor_assistant.html` at the first delivered Floating Tutor commit,
`850434a50c01b64cec213f323fb987b77160a4b0`.

Asset: `assets/pilot-robot.svg`. The standalone SVG fixes its original blue
color to `#2166db`, with a transparent background and no external dependencies.
It is embedded once as an `image/svg+xml` data URI and shared by the launcher
and chat header. The Pilot name and current transparent button remain in use.

This is an icon-only restoration. Current authentication, account isolation,
drag bounds, mobile safety margins, Esc support and chat behavior remain in
place; no historical application or interaction code is restored.
