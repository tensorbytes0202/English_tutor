# Idea: Admin books → AI teaches only from them (RAG)

Status: **future idea, parked.** Not part of the RFP and not part of the PoC. Keep it as a Phase 2 / roadmap item.

## The idea in one line
The admin uploads the school's books. The AI tutor then explains, asks questions and checks answers using only that material, for any subject and any grade.

## Why it is worth keeping
- Lessons stop being hand-written (today: 3 lessons in `lessons.json`).
- The tutor stays inside the school's own syllabus, so answers match what the teacher taught.
- One platform can later cover Maths, Science, Hindi and more, not only English speaking.
- Every answer can show where it came from (book, chapter, page).

## How it would work
```
Admin uploads a book (PDF / DOCX)
  -> extract text, split into small chunks
  -> tag each chunk: subject, grade (Pre-Group to 8), chapter, page
  -> turn chunks into embeddings, store in a vector database

Teacher picks a chapter for the class
  -> fetch that chapter's best chunks ONCE, before the lesson starts
  -> build a "lesson pack" (summary, key terms, questions, answers)
  -> the tutor uses the pack during the lesson
```

## Admin portal modules it needs
1. **Content library:** upload, status (processing / ready / failed), subject, grade, chapter.
2. **Lesson builder:** the AI drafts a lesson from a chapter; a teacher edits and approves it. Nothing reaches students without approval.
3. **Source references:** each AI answer says which book, chapter and page it came from.
4. **Access control:** which books and lessons each grade or class can see.
5. **Usage and cost:** retrieval and embedding cost shown in the same dashboard as the rest.

## Rules to keep from the start
- **Latency:** retrieve once per lesson, not on every student utterance. Retrieval on every turn adds roughly 50-150 ms (estimate, not measured).
- **Grammar correction stays separate.** The fine-tuned model does that; it does not need RAG.
- **"Answer only from the documents."** If the books do not cover a question, the tutor says so and redirects, instead of guessing.
- **Student data never enters the index or any training.** Only books go into RAG. This keeps the RFP's zero-training rule.
- **Copyright:** upload only books the school is licensed to use. State this in the terms.

## Do now so it is easy later (cheap)
- Give each lesson step a `source` field: `{ "book": "...", "chapter": "...", "page": 0 }`.
- Leave a disabled "Content library" entry in the admin navigation.

## Open questions
- Which books and subjects come first?
- Are the books digital (searchable PDF) or scans that need OCR?
- Which languages? Hindi or other Indian-language books change the model and embedding choice.
- Where must the data live (India region)?

## Proposal wording
Write it as: "Future roadmap: curriculum-aware tutoring from school-supplied books (RAG)." Do not write it as a delivered feature. It is not in the RFP, and promising it risks the 9-week timeline and the latency target.
