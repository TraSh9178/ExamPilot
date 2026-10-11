# Pilot mascot: original captain concept

This document records the first portrait. The restored original robot is
documented in `pilot_robot_icon.md` and uses `assets/pilot-robot.svg`.

Pilot is ExamPilot's cartoon airline captain and AI study assistant. The same
portrait appears on the draggable launcher and in the chat header. Labels and
assistant message attribution use the name Pilot.

Asset: `assets/pilot-mascot.png` (transparent PNG). Generated with the built-in
`image_gen` tool; the selected output was copied into the project unchanged.
The component embeds the asset once as a data URI and reuses it for the header,
so page navigation does not depend on an external image host or relative image paths.

The launcher remains 64 × 64 px. Authentication, account/course isolation,
chat storage, dragging, and question submission use the existing implementation.

## Final generation prompt

```text
Use case: stylized-concept
Asset type: transparent mascot portrait icon for the floating AI assistant on the ExamPilot study website. The character is named Pilot; the website currently uses a white, bright blue (#2166DB), and dark navy (#102044) palette.
Primary request: Create ONE original, friendly, cute cartoon airline captain character, a polished colorful 2D mascot portrait. Large expressive approachable face, cheerful gentle smile, short dark hair, wearing a recognizably professional airline captain's white peaked cap with navy band and a small golden wing emblem, white shirt, navy tie, navy uniform shoulders with understated golden epaulette stripes. Compact head-and-shoulders bust, with the cap clearly visible, facing the viewer. Face and cap are the strongest readable shapes. Soft rounded forms, clean bold silhouette, very restrained shading, crisp illustration edges, tasteful modern educational-app mascot style.
Composition: square canvas, single centered character taking about 88% of the canvas; complete cap and shoulders inside frame with a small margin. Strong readability as a 64px chat-launcher icon. The character is a human airline captain, not a robot. Transparent background, no scene, no circle, no surrounding frame, no airplane, no speech bubble, no extra objects.
Text: no text or lettering anywhere, no watermark. Pilot's name will be added separately in the interface.
Output: actual transparent PNG with clean alpha edges, one finished mascot asset.
```
