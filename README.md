# Contract Review Skill

A Claude skill that runs the same five review prompts against a construction contract and builds one page with the full contract on the left and the five results on the right.

This repository is an example. It shows how a skill like this is put together and what it can produce, using a publicly posted county contract. The prompts are a starting point for a first read of a construction contract, and the results are summaries that should be checked against the clauses they cite. Nothing here is legal advice.

[See the sample page](https://marcus-erickson.github.io/ContractReviewSkill/) · [Download the skill](https://github.com/marcus-erickson/ContractReviewSkill/raw/main/contract-review-skill.skill)

## What it does

You give Claude a contract and say "run the contract review against this contract." The skill reads the contract, runs five fixed prompts against it, and publishes a page that shows the contract next to the results. Because the prompts are fixed, every contract is read through the same five lenses. Results are comparable from one contract to the next, and anyone on a team can run it without writing prompts.

The five lenses are:

- Payment Terms
- Changes and Claims
- Schedule and Delay
- Risk Transfer
- Termination and Disputes

Each result is 100 to 150 words and cites the sections it relies on. When the contract does not cover a topic, the result says "Not addressed in this contract" instead of filling the gap from general practice.

On the page, selecting a section reference in a result scrolls the contract to that clause. Small numbered tags in the contract margin show which results cite each section, and a button under each result highlights every section it cites.

The page Claude publishes also has an **Ask Claude** tab beside the results. The viewer can ask their own questions about the contract, and answers cite sections that link to the clause. Each question spends the viewer's own Claude usage, and a very long contract is searched instead of sent whole. The sample on GitHub Pages is a static page and does not include the chat, because it only works inside Claude.

## The sample

`index.html` is the skill run against the agreement between Fort Bend County, Texas and Brookstone, LP for the Justice Center Expansion (RFP 17-037). The county posted the agreement publicly, and the [source PDF](https://agendalink.fortbendcountytx.gov/docs/2017/CCTR/20170214_2900/25417_R17-037.Brookstone.Agreement.pdf) is on its agenda site. The page shows the agreement and Exhibit A, the contractor's proposal. It leaves out the schedule of values, the specification listing, and the wage determination, because they are tables that do not extract cleanly. The signature blocks in the posted copy are blank.

## Use the skill

1. Download `contract-review-skill.skill` from this repository.
2. Add it to Claude as a custom skill.
3. Attach a construction contract (PDF, Word, or text) to a conversation and ask Claude to run the contract review. If no contract is attached, Claude asks for one.

Claude publishes the result as a private page that you can share from the page's Share menu.

## Change the prompts

All five prompts live in one file:

```
contract-review-skill/references/prompts.md
```

To change what the skill pulls out of a contract, edit that file. Each prompt has a numbered heading and a quoted block of text.

- The heading becomes the title of the panel on the page, so `## 1. Payment Terms` produces a panel called Payment Terms.
- The quoted block under the heading is the prompt. Change the topics it lists, or add the ones you care about.
- The page supports one to six panels. To add another, add a section in the same format.
- The shared instructions at the top apply to every prompt. Keep the line about citing section numbers, because the clickable links depend on it. The build script warns about any result outside 90 to 170 words, so if you change the target length, update that check in `scripts/build_page.py` as well.

After editing, rebuild the download so the link serves the new prompts:

```
python3 build_skill.py
```

Commit the updated `contract-review-skill.skill`. Anyone who installs it again gets the new prompts.

## Rebuild the sample page

The inputs for the sample are in `example/`. `contract.txt` is the contract text and `results.json` holds the five results. To regenerate `index.html`:

```
python3 contract-review-skill/scripts/build_page.py example/contract.txt example/results.json index.html \
  --page-title "Contract Review Skill" --standalone --intro-file example/intro.html
```

Without `--standalone`, the script writes the version that Claude publishes as an artifact, with the Ask Claude tab (add `--no-chat` to leave it out). With it, the script writes a complete HTML page that works on GitHub Pages or any other web host, with the text from `example/intro.html` above the sample. Edit that file to change the introduction, the buttons, or the links at the top of the page.

## How it works

1. Claude extracts the contract to plain text. For PDFs it uses `pdftotext`, and `scripts/prepare_text.py` rejoins the line-by-line output into one paragraph per clause.
2. Claude runs the five prompts from `references/prompts.md` and writes the results to `results.json`.
3. `scripts/build_page.py` builds the page. It finds the numbered sections in the contract, turns citations such as "Section 3.2" or "Ex. A.7" into links, and reports any citation that does not match a real section so it can be fixed before publishing.

The model writes the results, and the scripts handle layout and linking, so the page behaves the same way on every run.

## Repository layout

```
.
├── README.md
├── index.html                      Sample page, served by GitHub Pages
├── contract-review-skill.skill     The downloadable skill
├── build_skill.py                  Rebuilds the .skill file from the skill folder
├── example/
│   ├── contract.txt                Contract text used for the sample
│   ├── results.json                The five results shown in the sample
│   └── intro.html                  Introduction shown above the sample on the page
└── contract-review-skill/          The skill itself
    ├── SKILL.md                    Instructions Claude follows
    ├── references/prompts.md       The five prompts
    ├── scripts/build_page.py       Builds the two-pane page
    ├── scripts/prepare_text.py     Cleans up text extracted from PDFs
    └── evals/                      A test case with a fictional subcontract
```

## Limits

- The results come only from the text that is on the page. If a contract relies on documents that were not included, such as specifications or general conditions, a topic marked "not addressed" may be covered there.
- Linking depends on the section numbering printed in the contract. Scanned PDFs need OCR first, and unusual numbering schemes may link fewer citations.
- The results are summaries and not legal advice.
