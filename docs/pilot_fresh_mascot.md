# Pilot: previous fresh book captain

This document records the previous rounded pastel-blue book captain. The current
aircraft outline is documented in `pilot_aircraft_icon.md` and uses
`assets/pilot-aircraft.svg`.

This version was a rounded pastel-blue book captain with black eyes, a small
white beard, and a simple captain cap. It appears directly as the draggable
launcher, with a plain Pilot label and no white button frame or colored badge.
The same image appears in the chat header without a background tile.

Asset: `assets/pilot-book-fresh.png` (transparent PNG). Created with the built-in
`image_gen` tool as an edit of the previous pixel book. The generated file is
copied into the project unchanged. The component embeds the image once and
shares it between both portraits. Rendering is smooth rather than pixelated.

The 64 × 64 px launcher contains a 52 px portrait and a 12 px plain text label.
Drag bounds, keyboard navigation, authentication and chat behavior are unchanged.

## Final generation prompt

```text
Use case: style-transfer
Asset type: refreshing replacement mascot illustration for ExamPilot's floating AI tutor, named Pilot.
Input image: edit target to completely redesign. Preserve ONLY the book character concept, black eyes, a white beard detail, captain hat, and transparency. Discard the old pixel treatment, dark heavy outlines, oversized moustache/beard and ornate gold decorations entirely.
Primary request: Make ONE irresistibly cute, fresh, youthful little BOOK CAPTAIN mascot, with a calm playful educational-app personality. Its body is a soft compact upright hardcover book with very rounded corners, powder-blue/periwinkle cover, a subtle aqua spine, and a tiny ivory page edge visible at the side. Two small rounded BLACK eyes set wide apart, a tiny friendly curved smile, very faint peach cheek accents. Keep the WHITE beard but make it a very small soft cloud-shaped tuft at the bottom of the face, no huge moustache and no long beard. It should feel like a friendly little magical book, not an old man. A small simple WHITE airline captain cap with a muted navy band and a single tiny soft-gold wing emblem sits slightly playfully on the book. The cap should not overwhelm the face. No human skin, face or anatomy.
Art direction: polished charming modern 2D mascot illustration; minimal soft rounded shapes, smooth clean edges, airy low-contrast pastel palette, restrained flat shading, thin soft-blue outlines only when needed, lots of visual simplicity so it reads at 64px. Approachable and fresh rather than formal or ornate. Absolutely NO pixel art, pixelation, stair-step edges, thick black contour, glossy 3D, complex textures, military-looking decorations, heavy shadows or aged facial details.
Composition: square canvas, one centered complete character occupying about 90% of the canvas, complete hat and book inside small margins. Genuine transparent background and clean alpha. No white square, white frame, badge, circle, sticker border/halo, speech bubble, background scenery, floor, cast shadow, surrounding objects, or text. This character itself is the floating click target, rather than a sticker placed on a white button.
Text: none; the interface supplies the name Pilot separately.
```

