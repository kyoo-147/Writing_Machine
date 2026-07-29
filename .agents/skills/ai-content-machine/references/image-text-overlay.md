# Image text overlay

Read this reference before adding any text to a source image.

## Approval gate

1. Collect and present the unmodified source images first.
2. Ask whether the user wants summary text on the images.
3. Treat no answer as no permission. Do not modify an image while the decision is pending.
4. A long post caption does not imply permission to place text on the image.

## Analysis before placement

For every approved image:

1. Detect image dimensions and aspect ratio.
2. Measure local luminance and contrast.
3. Identify existing text, faces, logos, charts, UI, and visually salient subjects.
4. Mark those regions as protected.
5. Choose a low-saliency region with enough padding and contrast.
6. Prefer top or bottom safe areas only when they do not cover important content.
7. Use a solid or softly blurred backing panel, outline, or shadow when the image alone cannot provide reliable contrast.

## Copy rules

- Put only the hook, short summary, number, date, or key point on the image.
- Keep each overlay concise: normally one headline and at most one supporting line.
- Keep detailed explanation, attribution, links, and nuance in the post caption.
- Never invent a claim to make the overlay more dramatic.
- Preserve Vietnamese diacritics and exact product names.

## Output rules

- Preserve every downloaded source asset unchanged.
- Save overlays as new versioned PNG/JPG files.
- Never create SVG.
- Record the source path, output path, overlay text, placement, contrast treatment, and approval state in the asset manifest.
- Inspect the rendered result before delivery. Reject text that covers important content, lacks contrast, or becomes unreadable on a TikTok crop.
