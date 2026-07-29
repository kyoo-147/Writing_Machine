# Content contract

## Content item

```yaml
id:
title:
original_url:
source_name:
source_type: official | paper | repository | media | community
author:
published_at:
discovered_at:

category:
content_type: news | demo | paper | repository | benchmark | opinion
summary:
why_it_matters:
technical_explanation:

claims:
  - text:
    status: verified | disputed | unverified
    source_url:
    evidence:
    confidence: high | medium | low

scores:
  novelty:
  visual:
  buildability:
  technical_relevance:
  authority:
  controversy:
  vietnamese_audience:
  total:

angles:
  - name:
    thesis:
    tone:
    risks:

production:
  platform:
  format:
  duration:
  audience:
  voice_profile:
  hook_options:
  script:
  caption:
  hashtags:
  cta:

assets:
  - path:
    source_url:
    type:
    origin: source | imagegen
    usage_rights:
    attribution:

Asset invariants:

- At least one image or video with `origin: source` is required before production.
- Every source asset must retain its original URL and attribution.
- ImageGen illustrations are optional, must be PNG/JPG, and cannot satisfy the source-media requirement.
- SVG, generated placeholders, and unattributed copied media are prohibited.

status: collected | verified | selected | scripted | designed | approved | published
human_approval:
revision_history:
```

## Discovery response

Return a table with:

1. Topic
2. Type and date
3. Why it matters
4. Best angle
5. Visual
6. Primary source
7. Score

## Production package

```text
<content-id>/
|-- brief.yaml
|-- title-and-hooks.md
|-- script.md
|-- caption.md
|-- sources.md
|-- fact-check.md
|-- asset-manifest.yaml
|-- upload-checklist.md
`-- assets/
```
