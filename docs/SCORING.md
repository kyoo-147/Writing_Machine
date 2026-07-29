# Trend scoring

Every normalized story receives a score from 0 to 100:

| Signal | Weight | Evidence |
|---|---:|---|
| Novelty | 25% | Publication age; decays over the first 30 days |
| Visual strength | 20% | Demo, image, video, multimodal or robotics evidence |
| Buildability | 15% | Repository, source, API, SDK or implementation detail |
| AI engineering relevance | 15% | Models, agents, inference, research and benchmarks |
| Source authority | 10% | Primary repositories, papers and official domains |
| Discussion | 10% | Log-scaled engagement where the connector exposes it |
| Audience fit | 5% | Configurable editorial signal |

Connector-provided signals override heuristics. Deduplication first canonicalizes URLs, removes tracking parameters and then clusters titles with token-set Jaccard similarity. Stories present in the publishing archive are excluded before ranking.
