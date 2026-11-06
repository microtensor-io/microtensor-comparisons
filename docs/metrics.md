# Metrics

## Arena metrics

Computed by the arena's grader on every summary. The code is `microtensor_subnet/validator/compress.py` in the public subnet repository.

| Metric | Definition |
|---|---|
| Format valid | The summary has the arena's nine headings, each on its own line as a level two heading, in order, with nothing before the first. |
| Within budget | Output tokens are at most min(3,072, max(1,000, 5% of the input tokens)), counted with the Granite tokenizer. |
| Recall | Key facts kept divided by key facts in the item. A key fact is a file path, an error type or a function name taken from the session. It is kept when one of its forms appears in the summary after normalising case, quotes and slashes. |
| Hallucination | Code identifiers in the summary that never appear in the session, divided by all code identifiers in the summary. Common tool and language names are not counted. |
| Continuation | The mean score of the item's probes. A small fixed model reads the summary alone and answers questions such as the last edited file, whether the last test run passed, the last exception and which task the agent is working on. |
| Item score | 0 when the format is invalid or the summary is over budget. Otherwise (1 − hallucination) × (0.5 × recall + 0.5 × continuation). |
| Pass | Item score of at least 0.60. |
| Pass rate | Passed items divided by items, with a Wilson 95% interval (z = 1.96). |

Recall and hallucination are reported as the mean over all 36 summaries of a contestant, including those that failed format. Continuation is the mean over the summaries that could score.

## Study metrics

Computed from the fixed reader's answers. Not measured yet in exp1.

| Metric | Definition |
|---|---|
| Planted fact recall | Correct answers divided by 306, scored by the study's own rules (`ceval/scoring.py` in the replication package). Also reported over the 273 facts the rendered session carries. |
| Confident wrong | A wrong or outdated value given with no sign of doubt, or a lure answered as if it had been discussed, divided by the 360 questions. |
| Commitment pass | The share of the 27 commitment probes where the reader's reply honours the earlier rule, by majority of three blind judge votes. |
| Confident commitment failure | The share where the reply breaks the rule and flags no doubt. |
| Judge agreement | Cohen's kappa between the judge's majority and a second judge on a random 25% of replies. |

The reader sees only a context and one question. The context is the contestant's summary, the full rendered session for the ceiling, or its last 3,072 tokens for the floor. It has no tools and no session.

## Practical metrics

| Metric | Definition |
|---|---|
| Time | Median and 95th percentile of the total time of one compaction. For local models it is measured next to the engine on the GPU machine. For API models it is the provider's response time, and is labelled so. |
| Time to first token | Median, local models only. |
| GPU cost per compaction | The card's hourly price times the measured time of the call. |
| Cost per compaction | For Microtensor models, GPU cost plus the list price of 0.01 USD per million input tokens, with output tokens free. For API models, input and output tokens at the provider's list price. |
| Summary length | Output tokens. |

## Statistics

- Wilson 95% intervals on every rate.
- Paired exact McNemar tests, two sided, of M1 against each frontier contestant on pass (36 pairs), planted fact recall (306 pairs) and commitment pass (27 pairs).
- A headline in the form "M1 keeps X of the frontier's recall at Y of the cost", where X is M1's recall divided by Claude Sonnet 5.5's and Y is the ratio of their costs per compaction.
