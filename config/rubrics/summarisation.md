# Summarisation Judge Rubric

Score each candidate from 0.0 to 1.0 against the task prompt and source
material. Use the full range.

- Faithfulness: no unsupported claims, wrong entities, wrong quantities, or
  reversed causal/timing relationships.
- Coverage: includes the central facts required by the source and the task,
  with no important omission that changes the meaning.
- Instruction adherence: follows requested format, length, JSON shape, bullet
  count, and required mentions.
- Clarity: concise, coherent, and not padded with irrelevant detail.

Guidance:
- 1.0 means faithful, complete for the requested scope, and instruction-clean.
- 0.7 means mostly correct but missing or weakening a material point.
- 0.4 means partially useful but with major omissions or format problems.
- 0.0 means wrong, unrelated, empty, or unusable.
