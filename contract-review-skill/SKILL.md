---
name: contract-review-skill
description: Run a fixed set of five review prompts (Payment Terms, Changes and Claims, Schedule and Delay, Risk Transfer, Termination and Disputes) against a construction contract and publish one two-pane page with the full contract on the left and the five short results on the right, with clickable section citations. Use this whenever the user says "run the contract review", "run this against the contract", "contract review skill", asks for a side-by-side summary of a construction contract, subcontract, prime contract, or owner-GC agreement, or attaches a contract and wants the key terms pulled out, even if they never name the skill. If no contract is provided, ask for one.
---

# Contract Review Skill

This skill takes one construction contract, runs five fixed prompts against it, and publishes a page that shows the whole contract next to the five results. Every contract gets the same five lenses, so results are comparable from one contract to the next and anyone on the team can run it without writing prompts.

The page does three things beyond showing text side by side. Each result cites sections like "(Art. 3.2)", and clicking a citation scrolls the contract to that section. Small numbered tags in the contract margin show which results cite each section, so a reader can see where each topic lives. A "Show in contract" button on each result highlights every section it cites.

## Step 1: Get the contract

The contract can arrive as an attachment, a Drive link or file name, a local path, or pasted text. If the user did not provide one, ask one short question and nothing else: which contract should this run against, and can they attach it or share a Drive link. Do not ask which party they represent or which prompts to run. The prompt set is fixed.

## Step 2: Turn it into plain text

Write the contract to `contract.txt` in the working directory. The build script links citations by matching the article and section numbers printed in the contract, so the numbering has to survive extraction.

- PDF: `pdftotext contract.pdf raw.txt` (check the tool exists first), then `python <this-skill>/scripts/prepare_text.py raw.txt contract.txt`. PDF text comes out one visual line at a time, often with a section number on a line of its own, and the prepare script rejoins it into one paragraph per clause. Use `--drop REGEX` for running headers, footers, and letterhead, and `--until REGEX` to stop before pages of tables or listings. For a page with a table, `pdftotext -layout` keeps the columns together. If the text is empty or garbled, the PDF is probably scanned. Use the pdf skill to OCR it and tell the user you did.
- Word: `pandoc contract.docx -t plain --wrap=none -o contract.txt`, or python-docx if pandoc is missing.
- Pasted text or Drive documents: save the text as is.

Keep one paragraph per block, separated by a blank line, with each section number at the start of its line ("3.2 Contractor shall pay..."). Remove repeated page headers, footers, and page numbers if they clutter the text.

Include exhibits that carry terms, such as a proposal with qualifications, supplementary conditions, or an insurance exhibit, because they often change the main agreement. Leave out pages that are only tables or listings, such as a schedule of values, a specification index, or a wage determination. They garble in extraction and add nothing to the five topics. Whatever you leave out, say so in the page subtitle and in your reply, since the results can only speak to the text on the page.

Read the file once to confirm the headings look right before going on. PDF text layers sometimes scramble a line or drop a sentence, so if a clause reads wrong, check that page against the PDF and note any gap you cannot fix.

## Step 3: Run the five prompts

Read `references/prompts.md`. For each of the five prompts in order, apply the shared instructions plus that prompt to the contract and write the result. Do this inline rather than with subagents. Five short results from one contract is cheap and keeps the wording consistent. Treat each prompt as independent: each result should draw only on the contract text, not on conclusions from the other prompts.

Hold to the rules in the shared instructions, because the page depends on them:

- 100 to 150 words per result.
- Cite the section number for every point, using the numbering printed in the contract, in the form "(Art. 3.2)" or "(Section 3.2)". These become the links. A citation that does not match a real section cannot link, and a reader will notice.
- Cite exhibit items as "(Ex. A.7)", where A is the exhibit letter and 7 is the numbered item. Roman-numeral parts work too, as in "(Ex. A.II)".
- Write "Not addressed in this contract" for a topic the contract text you were given does not cover. Never fill a gap from general industry practice. If the contract leans on documents that were not included, such as specifications or general conditions, the subtitle and your reply should say so, because a topic marked "not addressed" may live there.

## Step 4: Write results.json

```json
{
  "contract_title": "Northline Mechanical Subcontract",
  "subtitle": "Bayou City Builders, LLC · Harmon Medical Office Building",
  "results": [
    {"title": "Payment Terms", "body": "Pay applications are due by the 25th (Art. 3.1). ..."},
    {"title": "Changes and Claims", "body": "..."}
  ]
}
```

`title` is the heading from the prompts file. `body` is plain prose, or short lines beginning with "- " for a list. Separate paragraphs with a blank line. `subtitle` is optional: use the parties and project if the contract names them.

## Step 5: Build the page

```bash
python <this-skill>/scripts/build_page.py contract.txt results.json contract-review.html --page-title "Northline Subcontract Review"
```

The page title is the artifact's name in the gallery. Make it a specific two to four word name, usually the contractor or project plus "Review".

The script prints a report. Read it:

- **Unresolved citations**: a result cited a section number that does not exist in the contract text. Search the contract for the right number, fix the result in results.json, and rebuild. If the text really has no such section, remove the citation.
- **Zero sections detected**: the contract text has no recognizable headings, so nothing will link. Check `contract.txt` for lost line breaks or unusual numbering, fix the extraction, and rebuild.
- **Word counts outside 90 to 170**: tighten or expand that result and rebuild.

Do not edit the generated HTML by hand. To change the look, change the template inside the script so every future run benefits.

## Step 6: Publish and finish

Publish `contract-review.html` with the Artifact tool, using a short generic icon such as "contract" and a one-sentence description naming the contract. The page is already designed and follows the artifact page rules, so there is no need to rewrite it.

The page contains the full contract text and is private until the user shares it. Say so in one short line when you hand it over. Then give the user one or two sentences on what came out: the topics the contract does not address and the one or two flags that matter most, since those are what they will look for first. Do not recap the steps.

## Notes

- The results are summaries drawn from the contract text. The page footer says they are not legal advice, and results should be checked against the cited section.
- To add a follow-up chat to the page, load the artifact-capabilities skill and add an "ask Claude" capability to the template. The base version does not include one.
- For a page outside Claude, such as GitHub Pages, add `--standalone` to the build command. It writes a complete HTML document instead of the artifact version. `--intro-file` takes an HTML fragment, such as a heading, a paragraph, and a few links, that is shown above the sample.
