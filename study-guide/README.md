# Study Guide

A self-paced, multi-subject study guide with **daily, weekly, monthly and
on-demand tests made only of written and problem-solving questions**.

* **Study guide** – each textbook section becomes a lesson page: overview and
  goals, easy-to-follow lessons, key terms, formulas, step-by-step worked
  examples, common mistakes, real-life applications, self-check problems with
  hints and full solutions, a summary and private notes. Maths renders with
  KaTeX and function graphs are drawn from simple `plot` blocks.
* **Tests** – no multiple choice. Every question needs working or an
  explanation. Numbers are randomised on every attempt, so a retake is a new
  problem. Students can attach photos of handwritten working.
  * *Daily practice* – 4 questions, 25 min, on what the student studied most recently.
  * *Weekly test* – 8 questions, 60 min, on everything studied so far.
  * *Monthly exam* – 12 questions, 100 min, across the whole subject.
  * *On-demand* – the student picks topics, number of questions, difficulty and time.
  Questions are chosen to favour ones not seen recently and topics where the
  student's mastery is lowest.
* **Marking** – each question has a model answer and a marking rubric.
  Final numeric answers are auto-checked. Written work is marked by:
  1. **AI marking** against the rubric (optional; set `ANTHROPIC_API_KEY`), and/or
  2. **student self-assessment** against the rubric (gives a provisional score), and
  3. **the teacher (admin)**, who can confirm or override any mark and leave feedback.
* **Progress** – streaks, score trend, mastery per section, "focus next"
  suggestions and full history. Each student sees only their own data; the
  admin sees everyone's.
* **Accounts** – registration with email confirmation, password reset by
  email, optional invite-only mode and email-domain restriction, admin
  invites, disable/delete accounts.
* **Look and feel** – Poppins (regular and medium weights only, never bold),
  16 soft pastel themes plus a custom colour picker. The theme is saved to
  the student's account, so it follows them to every device.

## Quick start

Requires **Node.js 22.5+** (uses the built-in SQLite module).

```bash
cd study-guide
npm install
cp .env.example .env      # then edit ADMIN_EMAIL, APP_URL, SMTP…
npm start                 # http://localhost:3000
```

On first start the admin account in `ADMIN_EMAIL` is created. If
`ADMIN_PASSWORD` is blank, a one-time "set your password" link is printed in
the server log.

Without SMTP settings, emails (confirmation, reset, invites) are not sent but
are kept in **Admin → Outbox** so you can pass links on, and the admin can
confirm a student's email manually.

### Docker

```bash
docker build -t study-guide .
docker run -p 3000:3000 -v $(pwd)/data:/app/data --env-file .env study-guide
```

All data (SQLite database and uploaded photos) lives in `data/`. Back up that
folder.

### Running behind HTTPS

Set `APP_URL=https://your.domain`, `TRUST_PROXY=true` and
`COOKIE_SECURE=true` when the app sits behind a reverse proxy (nginx, Caddy,
Render, Railway, etc.).

## Adding material

Content is JSON in `content/<subject>/` – see
[`docs/CONTENT_FORMAT.md`](docs/CONTENT_FORMAT.md). New files can be added in
small batches: add the section ids to `subject.json`, drop the section files in
`sections/`, run `npm run validate`, then restart the server or use
**Admin → Content → Reload content**. Students' progress and test history are
kept when content is updated or reloaded.

Current subjects:

| Subject | Units | Test questions | Source |
|---|---|---|---|
| Physics 11 – Chapter 4: Applications of Forces | 9 (4.1–4.6, Investigations, Review & careers, Review problems) | 217 | Nelson Physics 11, chapter 4 |
| Advanced Functions 12 (MHF4U) | 49 (sections 1.2–8.5 plus a review unit per chapter) | 936 | McGraw-Hill Ryerson Advanced Functions |

Section 1.1 (Power Functions) was not in the supplied MHF4U file, so it is not included yet.

## Development

```bash
npm run dev        # restart on change
npm test           # integration tests (auth, privacy, tests, marking, themes)
npm run validate   # check every content file and question template
```

Code layout:

```
src/
  app.js          express app wiring
  config.js       environment settings
  db.js           SQLite schema
  auth.js         passwords, sessions, CSRF, one-time tokens, rate limits
  content.js      content sync + markdown/KaTeX rendering
  plot.js         SVG graphs for ```plot blocks
  expr.js         safe expression evaluator for randomised questions
  tests.js        test generation, scoring, mastery
  grader.js       optional AI rubric marking
  routes/         auth, student and admin pages
  views/          HTML templates
public/           CSS and browser JS
content/          study material (JSON)
```
