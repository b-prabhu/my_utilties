# Content format

All study material lives in `content/<subject-id>/`. It is plain JSON so new
material can be added in small batches (e.g. 5 source files at a time) without
touching code. Content is re-synced into the database every time the server
starts (and from **Admin → Content → Reload content**).

```
content/
  physics-11/
    subject.json          # subject + chapter list
    sections/
      4-1.json            # one file per textbook section
      4-2.json
```

## subject.json

```json
{
  "id": "physics-11",
  "name": "Physics 11",
  "description": "Grade 11 University Physics",
  "chapters": [
    { "id": "ch04", "number": 4, "title": "Applications of Forces",
      "sections": ["4-1", "4-2", "4-3", "4-6"] }
  ]
}
```

## sections/<id>.json

| field | type | notes |
|---|---|---|
| `id` | string | file name without `.json` |
| `number` | string | e.g. `"4.1"` |
| `title` | string | |
| `estimatedMinutes` | number | self-paced study time |
| `overview` | markdown | 2–4 sentence hook |
| `objectives` | string[] | "By the end you can…" |
| `lessons` | `{id,title,body}`[] | `body` is markdown; the main teaching text |
| `keyTerms` | `{term,definition}`[] | |
| `formulas` | `{name,latex,meaning}`[] | `latex` without `$` delimiters |
| `workedExamples` | `{title,problem,steps[],answer}`[] | each step is markdown |
| `misconceptions` | `{myth,fact}`[] | |
| `realWorld` | `{title,body}`[] | practical applications |
| `practice` | `{question,hint,solution}`[] | self-check problems inside the guide |
| `summary` | string[] | |
| `questions` | Question[] | the **test bank** (see below) |

Markdown supports GitHub tables and maths: inline `$F_N = mg$`, display `$$\mu_S = \frac{F_{S\,max}}{F_N}$$`.

## Test-bank questions

Every question is **subjective or problem solving** – no multiple choice,
true/false or fill-in-the-blank.

```json
{
  "id": "4-2-q07",
  "type": "problem",              // problem | conceptual | explain | analysis | design
  "difficulty": 2,                // 1 easy, 2 medium, 3 challenging
  "vars":    { "m": { "min": 80, "max": 140, "step": 5 },
               "F": { "min": 300, "max": 420, "step": 10 } },
  "derived": { "FN": "m*9.8", "muK": "F/FN" },
  "text": "You drag a {{m}} kg trunk across a floor at constant velocity with a horizontal force of {{F}} N ...",
  "parts": [
    { "label": "a", "text": "Calculate the coefficient of kinetic friction.",
      "answer": { "expr": "muK", "unit": "", "sig": 2 } },
    { "label": "b", "text": "Explain why a friend pulling up on the trunk makes it easier to drag." }
  ],
  "modelAnswer": "(a) $F_N = mg = {{FN:3}}$ N ... $\\mu_K = {{muK:2}}$\n\n(b) ...",
  "rubric": [
    { "point": "Identifies that constant velocity means F_net = 0 so F_K = F_a", "marks": 1 },
    { "point": "Calculates F_N = mg correctly", "marks": 1 },
    { "point": "Correct μ_K with no units", "marks": 1 },
    { "point": "Explains that upward pull reduces F_N and therefore F_K", "marks": 2 }
  ]
}
```

* `vars` – randomised per test so each attempt has fresh numbers.
  `{min,max,step}` (optionally `"decimals": 1` to always show e.g. `2.0`) or `{choices:[…]}`. A bare `{{m}}` shows as many decimals as the step implies.
* `derived` – evaluated in order; may use earlier vars/derived values.
* Placeholders `{{expr}}` or `{{expr:sig}}` (round to `sig` significant
  digits) work in `text`, part `text` and `modelAnswer`.
* Expressions support `+ - * / ^ ( )`, numbers, variable names and
  `sqrt abs min max round`.
* `parts[].answer` (optional) lets the app auto-check a final numeric
  answer (±2 % by default, override with `"tol": 0.05`). Working and
  explanations are graded against the `rubric` by the AI grader (if
  configured) or by the admin.
* Total marks for a question = sum of rubric marks.
* Use g = 9.8 N/kg (m/s²) throughout, matching the textbook.

## Expressions

Besides `+ - * / ^ ( )` expressions may use `sqrt abs min max round floor ceil
sin cos tan asin acos atan exp ln log` (`log` is base 10), `logb(b, x)` and the
constants `pi` and `e` (a variable of the same name wins). Trig functions use
radians. Multiplication must be explicit: `2*x`, not `2x`.

## Graphs

Any markdown field can contain a fenced `plot` block, rendered as an SVG graph:

````
```plot
title: y = x^3 - 4x and its x-intercepts
f: x^3 - 4*x | label=y = x³ − 4x
f: 1/(x-1) | dashed
domain: -4, 4
range: -8, 8
points: (-2,0), (0,0), (2,0)
asymptote x: 1
asymptote y: 0
ticks: 1, 2
xticks: pi
```
````

`f:` lines (up to four) are functions of `x`; `range` is optional
(auto-scaled), `ticks` sets the x and y grid step, `xticks: pi` labels the
x-axis in multiples of π/2. Placeholders work inside plot blocks in questions,
so a graph can follow randomised values, e.g. `f: {{a}}*(x-{{h}})^2+{{k}}`.

## Authoring tips

* Leave a space between a LaTeX brace and a placeholder: `\frac{ {{a}} }{ {{b}} }`.
  `\frac{{{a}}}` is ambiguous and the validator will reject it.
* Run `npm run validate` after every change.
