# Studio content

Text Studio shows that is not in an upstream repo. Studio writes nothing here except use-case
templates (`senseai-studio check --write-templates`).

| file | what it decides |
|---|---|
| `modalities.yaml` | which data a sense can run on, by the library schema's `modality` |
| `pipeline.yaml` | the ten pipeline steps and how each is checked (used until profiles has `docs/pipeline/steps.yaml`) |
| `use_cases/<niche>.<sense>.md` | the Use cases tab, written by the founder |

## Use cases

One Markdown file per niche and sense. `niche` is the library entry's `niche` field when it has
one, else the clade key (`felidae`). Front matter:

```yaml
---
species: [felidae, panther_vision]   # clade keys or profile names the case is about
status: idea                         # idea | validated
evidence: []                         # run ids that back the claims (bench / Studio runs)
---
```

Write under four headings: **The job**, **Where human perception fails**, **What the model
offers**, **Caveats**. Put each claim in its own list item: Studio shows the species+sense
pipeline step beside every list item, so a reader sees "step 3/10" next to the claim. Raw HTML is
escaped. Delete `template: true` once the file is written.
