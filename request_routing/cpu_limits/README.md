# Request routing on CPU: what fits a 4 core, 20 minute evaluation

Run date: 2026-11-18. Task: request routing.

**Status: complete.** The labelled cases are private and are not in this repository. The encoder is public; the small heads and the bag of tokens model were trained for this test on the labelled cases. Every test across machines used synthetic requests.

## Question

A router reads a request and chooses which of seven specialist models should answer it. Can a small router be scored on CPU inside a sandbox of 4 CPU cores and 4 GiB of memory, with a hard ceiling of 20 minutes per evaluation and a typical run of 10? Does the same file get the same score on every machine? And when the leader and a copy that is no better are scored on the same cases, does the copy stay below a 1% lead, meaning a score at least 1.01 times the leader's?

The score is accuracy: the share of cases whose most likely label is the right one. We also report the log score, exp(−mean log loss), which rewards confident right answers as well.

## Short answer

- **Speed fits.** The e5 files answer 3,000 cases in 0.7 to 4.3 minutes on 4 cores, depending on the machine and the file. The one e5 file the entry check accepts, weight only 8 bit, took 2.9 minutes on the one machine it was timed on, against 2.1 for full precision there. A bag of tokens model needs seconds.
- **Memory fits.** The highest peak was 2.0 GiB, for the full precision file, which is over the size limit. The accepted weight only file peaked at about 1.0 GiB.
- **The same file gets the same score on every CPU tested, if it computes in float.** The bag of tokens model and the full precision e5 gave byte identical answers on five AMD machines of four CPU models, at 1 and 4 threads. An Intel laptop stayed within 0.0000018 of the AMD answers for every float file without changing a label. The weight only file ran on one of the AMD machines.
- **Run time quantisation is the exception.** A file that quantises its activations to 8 bits at run time changed 43 to 51 of 2,100 labels between the laptop and the AMD machines, so its score depends on the machine.
- **A nudged copy stays below a 1% lead.** Noise of 0.01% or 0.1% on every weight changed at most 2 of 200 labels, moved accuracy by at most 0.55% (one case) and the log score by at most 0.07%. The copy with the most changes would beat a 1% lead at most 3% of the time at 350 cases, and practically never at 3,000.
- **A retrained copy needs thousands of cases.** A copy whose head is fitted again on a subsample or resample of the same training cases changes 1.8 to 10.4% of labels. If it were exactly as good as the leader, it would beat a 1% lead in accuracy by luck 9 to 31% of the time at 350 cases, and 0.04 to 4.2% of the time at 3,000, averaged over six copies. The most different copy reaches 6.0% at 3,000.
- **Accuracy is the steadier score for a 1% lead.** For distinct copies the log score gives a lucky win about three times as often as accuracy at 3,000 cases (13% against 4.2% for the bag of tokens model); for close copies the two are about equal. Changing only the confidence moves the log score, while accuracy cannot move.

## Setup

| Part | What we used |
|---|---|
| Task | Seven labels, one per request: `compress` (shrink a session for a model to resume), `extract` (copy values into named fields), `classify` (pick one of a fixed set of labels), `translate`, `summarise` (shorten a text for a person), `code` (write, fix or explain code) and `frontier` (judgement, advice, planning, long original writing, or a specialist task plus analysis) |
| Cases | A set of 501 labelled requests from a single source, 65 to 76 per label, 169 tagged hard. The labels have not had a second check. Requests run 5 to 25 words, 9 to 47 tokens. Mostly English, some in other languages |
| Split | 301 cases to train, 200 held out (132 easy, 68 hard), stratified by label and difficulty. Five fold cross validation over all 501 as a second view |
| Model file | For this test, one ONNX file per model. It takes token ids and an attention mask, int64, 128 positions per request, and returns seven float32 probabilities, one per label. Opset 13 to 21, default domain operators only, float arithmetic: weights may be stored as 8 bit integers and expanded to float, but quantising activations at run time is rejected. One self contained file under 150 MiB (157 MB) |
| Tokenizer | The same for every model: `tokenizer.json` of `intfloat/multilingual-e5-small` at `614241f622f53c4eeff9890bdc4f31cfecc418b3` (250,002 tokens), with its special tokens, cut and padded to 128 |
| Runtime | ONNX Runtime 1.20.1 on the CPU, 4 threads, extended graph optimisations. onnx 1.17.0, numpy 1.26.4, tokenizers 0.20.3 |
| Scoring | Cases go to the model in batches of 50, with the same number of cases for every label (to within one) and 40% of them hard. The score is accuracy. Log loss is the mean of −ln p(right label), with p floored at 0.0001; the log score is exp(−log loss) |
| Machines | Cloud CPU instances with 4 vCPUs each: AMD EPYC 4564P (two instances), 4565P, 9575F and 9754, all with AVX-512 and AVX-512 VNNI, Linux, Python 3.12. An Intel Core i7-1255U laptop with AVX2 and AVX-VNNI and no AVX-512, Windows, Python 3.10, same library versions |
| Synthetic requests | 2,100 requests of 5 to 25 words drawn at random from a fixed word list, 300 per label, the same on every machine. Used for every timing and cross machine test |

The models:

| Model | File | How it was made |
|---|---|---|
| Bag of tokens | 7.0 MB | Logistic regression on the tokens of the request, each token's weight averaged over the request, written straight into ONNX as a lookup, a mean and a softmax |
| e5, full precision | 470.4 MB | `multilingual-e5-small` at the revision above, `onnx/model.onnx`, mean pooled and normalised, with a logistic regression head trained on the 301 cases. Over the 150 MiB limit; measured for comparison |
| e5, published 8 bit file | 118.4 MB | The same construction from `onnx/model_qint8_avx512_vnni.onnx`, with its own head trained on that file's vectors. The file quantises its activations to 8 bits at run time |
| e5, run time 8 bit, our quantisation | 118.1 MB | The full precision file quantised with ONNX Runtime's dynamic quantiser, once with 8 bit and once with 7 bit weights |
| e5, weight only 8 bit | 119.2 MB | The full precision file with every large weight stored as 8 bit integers and a scale per column or row, expanded to float when the model runs. All arithmetic is float |

Every AMD machine rebuilt the full precision and published 8 bit e5 files from the public encoder and the trained heads, and the first EPYC 4564P instance also built our quantised and weight only files from them. Every rebuilt file was byte identical to ours. The bag of tokens file was copied.

## Accuracy

On the 200 held out cases, in batches of 50, on the laptop. The run time 8 bit rows would give other figures on the AMD machines.

| Model | Accuracy | Easy | Hard | Log loss |
|---|---|---|---|---|
| Bag of tokens | 0.785 | 0.795 | 0.765 | 0.605 |
| e5, full precision | 0.910 | 0.962 | 0.809 | 0.253 |
| e5, weight only 8 bit | 0.915 | 0.962 | 0.824 | 0.255 |
| e5, published 8 bit file | 0.890 | 0.932 | 0.809 | 0.266 |
| e5, run time 8 bit, 8 bit weights | 0.920 | 0.939 | 0.882 | 0.247 |
| e5, run time 8 bit, 7 bit weights | 0.905 | 0.939 | 0.838 | 0.277 |

Five fold cross validation over all 501 cases, with the head fitted again in each fold: bag of tokens 0.840 (easy 0.846, hard 0.828), e5 full precision 0.924 (0.967, 0.840).

In plain terms:

- The bag of tokens model reaches 78.5% on the held out cases and 84% in five fold cross validation, and the hard tag barely lowers it. The set is easy to tell apart by its words, so it says little about real requests.
- The e5 head is 12.5 points better on the held out cases, and for it the hard cases are clearly harder.
- Each overall accuracy above carries a standard error of about 2 to 3 points; the easy figures (132 cases) about 2 to 3.5, and the hard figures (68 cases) about 4 to 5.

## Timing and memory

Times are for 2,100 synthetic requests on 4 threads; the 10 minute and 3,000 case columns are scaled from them. End to end means the full scorer built for this test: the model process starts, checks the file, warms up, and answers every batch over HTTP while the scorer counts the result. Model only means the tokenizer and the model called directly in batches of 50, with no scorer or HTTP.

| Model | Accepted by the entry check | Time for 2,100 cases | Timed on | Cases in 10 minutes | 3,000 cases | Peak memory (MiB) |
|---|---|---|---|---|---|---|
| Bag of tokens | Yes | 1.3 to 2.6 s | Five AMD machines, end to end | over 470,000 | under 4 s | 347 to 349 |
| e5, published 8 bit file | No, run time quantisation | 29 to 155 s | Five AMD machines, end to end | 8,100 to 43,500 | 41 to 221 s | 770 to 778 |
| e5, full precision | No, over 150 MiB | 41 to 180 s | Five AMD machines, model only | 7,000 to 30,400 | 59 to 257 s | 2,069 |
| e5, weight only 8 bit | Yes | 121 s | First EPYC 4564P instance, model only (full precision 86.8 s there) | about 10,400 | about 173 s | 1,047 |

Notes:

- Memory on the AMD machines is the peak resident size of the model process over the 350 and 2,100 case runs. The full precision and weight only rows come from one Windows process on the laptop that loads the tokenizer and the model and answers 500 requests. The same measure read 298 MiB for the bag of tokens model, against 347 to 349 MiB for its model process on Linux, so these two rows may read about 50 MiB low.
- The published 8 bit file was timed before the rule against integer arithmetic was added to the entry check.
- With ONNX Runtime's QDQ optimisations turned off, the weight only file took 93 s on the same machine and matched its default answers to within 0.0000019, with no label changed.

Per machine:

| Machine | Bag of tokens, end to end | e5 published 8 bit, end to end | e5 full precision, model only |
|---|---|---|---|
| EPYC 4564P, first instance | 2.0 s | 50.5 s | 86.8 s |
| EPYC 4564P, second instance | 1.3 s | 32.5 s | 59.6 s |
| EPYC 9575F | 1.7 s | 29.0 s | 41.4 s |
| EPYC 9754 | 1.7 s | 39.9 s | 77.2 s |
| EPYC 4565P | 2.6 s | 154.8 s | 180.2 s |

Machines differ a lot, and each was timed once: the two 4564P instances differ by 1.5 to 1.6 times, and the 4565P instance ran e5 4.3 to 5.3 times slower than the 9575F. Every request is padded to 128 tokens, so the length of a request does not change the model's time.

## Copies of one model on the same cases

A takeover rule can compare a new entry with the current leader on the same cases, by scoring the leader again alongside each challenger. What decides it is how far two entries of equal quality land apart on the same cases. Every chance below assumes the copy is exactly as good as the leader, and is for one copy in one evaluation; a challenger that sends several copies gets a chance with each.

### Nudged copies

Every weight of the leader multiplied by (1 + d × random noise), 10 copies per level for the bag of tokens model and 4 for e5 at full precision, scored on the 200 held out cases. The accuracy and log score changes are relative to the leader.

| Leader | Noise d | Labels changed, of 200 | Accuracy change | Log score change | Chance of a 1% lead in accuracy, copy with most changed labels: 350 cases | 3,000 cases |
|---|---|---|---|---|---|---|
| Bag of tokens | 0.01% | 0 | 0 | −0.003% to +0.004% | under 0.2% | about 0 |
| Bag of tokens | 0.1% | 0 | 0 | −0.025% to +0.036% | under 0.2% | about 0 |
| Bag of tokens | 1% | 0 to 2 | −1.3% to +0.6% | −0.27% to +0.35% | 8.5% | 0.001% |
| Bag of tokens | 10% | 3 to 9 | −2.5% to +1.3% | −3.9% to +1.7% | 26% | 2.2% |
| e5, full precision | 0.01% | 0 to 1 | 0 to +0.55% | −0.007% to +0.003% | 0.6% | about 0 |
| e5, full precision | 0.1% | 0 to 2 | 0 to +0.55% | −0.067% to +0.030% | 3.0% | about 0 |
| e5, full precision | 1% | 1 to 5 | −1.1% to +0.55% | −0.77% to +0.23% | 11.5% | 0.08% |

How the chance is counted: each case where the copy picks another label is as likely to gain a right answer as to lose one, and every changed label is treated as changing whether the case is right. Take the share of labels changed by the copy that changed the most, and count how often the gains minus the losses among N cases reach 1% of the leader's right answers. Where no label changed, 200 cases cannot rule out a rate of about 0.15%, which would give up to 0.2% at 350 cases.

### Retrained copies

Each copy keeps the encoder and fits only the head again, in each of five folds. A close copy fits it on a random 90% of the fold's training cases; a distinct copy fits it on a resample of those cases with replacement. There are 6 of each, against a leader fitted on all the fold's training cases. The e5 leader and its copies use the published 8 bit encoder file for the request vectors.

In accuracy the copies all scored the same as the leader or a little lower on all 501 cases; in log score all but one did (one close e5 copy was 0.10% higher). So the chances below, which assume equal quality, lean high for these copies. Each is the average over the six copies, with the most different copy shown separately.

| Leader, five fold accuracy | Copies | Labels changed | Accuracy lower by | Chance of a 1% lead in accuracy: 350 cases | 1,000 | 3,000 | 5,000 | Most different copy, 3,000 |
|---|---|---|---|---|---|---|---|---|
| Bag of tokens, 0.840 | Close | 3.2 to 4.6% | 1.2 to 2.9% | 22% | 6.5% | 0.53% | 0.06% | 0.99% |
| Bag of tokens, 0.840 | Distinct | 7.4 to 10.4% | 2.9 to 5.5% | 31% | 16% | 4.2% | 1.3% | 6.0% |
| e5 on the published 8 bit file, 0.924 | Close | 1.8 to 2.6% | 0 to 1.5% | 9.4% | 1.9% | 0.04% | 0.00% | 0.09% |
| e5 on the published 8 bit file, 0.924 | Distinct | 4.8 to 7.2% | 1.1 to 3.9% | 20% | 9.0% | 1.4% | 0.21% | 2.4% |

The same chances with the log score instead of accuracy:

| Leader | Copies | 350 cases | 1,000 | 3,000 | 5,000 | Most different copy, 3,000 |
|---|---|---|---|---|---|---|
| Bag of tokens | Close | 18% | 6.2% | 0.49% | 0.06% | 1.3% |
| Bag of tokens | Distinct | 35% | 26% | 13% | 7.1% | 15% |
| e5 on the published 8 bit file | Close | 11% | 2.4% | 0.05% | 0.00% | 0.14% |
| e5 on the published 8 bit file | Distinct | 28% | 17% | 4.9% | 1.7% | 7.5% |

How the chance is counted: for accuracy as for the nudged copies, but with the measured share of cases where each copy gains or loses a right answer. For the log score, a 1% higher log score means a mean log loss lower by ln(1.01) = 0.00995. The chance is a normal approximation from the standard deviation of the per case difference in log loss on the 501 cases; chances below about 0.1% sit far in its tail and are rough.

In plain terms:

- At a few hundred cases, a copy that is no better beats a 1% lead in accuracy about one time in ten to one time in three. At 3,000 cases it is about one in twenty five or less on average, one in seventeen for the most different copy, and much less for close copies.
- On the log score, distinct copies still win 4.9 to 13% of the time at 3,000 cases. A confident miss can add up to 9.2 to the log loss (the cap set by the 0.0001 floor), so a few cases weigh heavily when two models are compared.

### Changing only the confidence

Raising every probability to the power 1/T and normalising (T from 0.5 to 2 on the held out cases, 0.8 to 1.25 across all 501) never changes a label, so accuracy cannot move. The log score can: on the 200 held out cases it rose by up to 0.70% for the bag of tokens model (T = 1.1) and 0.31% for e5 at full precision (T = 0.9). Across all 501 cases, with five fold heads and e5 on the published 8 bit file, it rose by at most 0.18% for the bag of tokens model and not at all for e5. Neither reaches 1% here, but a leader with poorly set confidence would leave that gap open to a copy that changes nothing else.

## Same file, same score

Each model answered the same 2,100 synthetic requests on every machine it ran on:

| Model | Five AMD machines, 1 and 4 threads | Intel laptop against the AMD machines |
|---|---|---|
| Bag of tokens | Byte identical | Byte identical |
| e5, full precision | Byte identical | Differs by at most 0.0000016 (mean 0.00000007); no label changed |
| e5, weight only 8 bit | Ran on the first EPYC 4564P instance only | Differs by at most 0.0000015 (0.0000018 with QDQ optimisations off); no label changed |
| e5, published 8 bit file | Byte identical | Differs by up to 0.26; 51 of 2,100 labels changed (2.4%) |
| e5, run time 8 bit, 8 bit weights | Ran on the first EPYC 4564P instance only | Differs by up to 0.21; 50 labels changed (2.4%) |
| e5, run time 8 bit, 7 bit weights | Ran on the first EPYC 4564P instance only | Differs by up to 0.23; 43 labels changed (2.0%) |

The full scorer built for this test, run end to end on 350 and on 2,100 synthetic cases, gave the same score and byte identical results on all five AMD machines, for the bag of tokens model and for the published 8 bit file. On the laptop, the 200 held out cases gave byte identical answers at 1, 2 and 4 threads for the bag of tokens model, e5 at full precision and the published 8 bit file.

What this shows:

- **Float arithmetic agrees across these CPUs.** The AMD machines agree to the byte. The Intel laptop, which differs in instruction set, operating system and Python version, differs only in the last digits of a probability. The closest call between the top two labels in the 2,100 requests was 0.000067 for e5 at full precision, about 40 times the largest difference, so no label moved. A request much closer to a tie than that could still flip between machines.
- **Quantising activations at run time does not agree with the laptop.** The published 8 bit file was byte identical on the five AMD machines, but changed 51 of its 2,100 labels between the laptop and the AMD machines; our two quantised files changed 50 and 43 against one AMD machine. Storing the weights in 7 bits, the usual guard against overflow in the integer arithmetic, did not remove it. Storing the weights in 8 bits and computing in float removes the difference and keeps the accuracy (0.915 against 0.910 at full precision).
- **Run time quantisation also ties a request's answer to its batch.** The published 8 bit file quantises each batch's activations together. On the same 200 held out cases, batches of 50 gave log loss 0.266 and one batch of 200 gave 0.258, with the same accuracy but different easy and hard splits. The bag of tokens model and e5 at full precision gave the same results either way.

## What this means

On 4 cores in 20 minutes, a small router can be scored on thousands of cases with time to spare, and on the CPUs tested the same file gets the same score as long as it computes in float. Unlike a model that writes text, a classifier hardly moves when its weights move a little: a copy nudged by 0.1% or less changed at most 2 of 200 labels and, at 3,000 cases, practically never clears a 1% lead.

A 1% lead needs enough cases. On this set, at about 3,000 cases per evaluation, a retrained copy that is no better beats the leader in accuracy about one time in twenty five or less on average, and one in seventeen for the most different copy. At a few hundred cases it does so one time in ten to one time in three. Accuracy holds that line better than the log score for distinct copies; for close copies the two are about equal.

Limits of this run:

- The labelled set is small and from a single source, and its labels have not had a second check. The accuracies above say more about the method than about real requests, and a set where models disagree more would need more cases.
- No AMD machine without AVX-512 was available on the day. The laptop is the only machine with another instruction set, and it also runs another operating system and Python version. The weight only file and our own quantised files were compared with one AMD machine only.
- Each instance had 4 vCPUs and the model used 4 threads. No run applied a 4 GiB memory limit; the peaks above show the headroom.
- The chances for copies assume equal quality, use the spread measured on 200 or 501 cases of this set, and are for one copy in one evaluation.
