# AI English Spoken Tutor: UI and product content

Source document for NotebookLM. It describes what the product is, who uses it, how it looks, every screen, the exact on-screen wording, and the numbers behind the dashboards. Figures marked "sample" are placeholders, not measurements.

---

## 1. The product in one paragraph

A spoken English tutor for a school (Grades Pre-Group to 8). A teacher runs a live class on a shared smart board. Up to 20 students speak to an AI tutor ("Ms. Asha") by voice. The tutor asks questions, listens, corrects grammar and explains each mistake in simple English. A separate admin portal lets the school manage classes, schedules and students, and see how each student is doing week by week, chapter by chapter, including what the AI cost.

**Why the design is shaped this way (from the school's tender documents):**
- Replies must feel instant: the target from the end of a student's speech to the tutor's first word is under 500 ms (hard ceiling 850 ms, penalty above 1,000 ms).
- AI cost must stay under $3.00 per 45-minute class and be visible live.
- Student voices and transcripts are sensitive: no recordings kept, no training on student data, encryption at rest and in transit.
- The tutor must stay on school topics, speak kindly and age-appropriately, and the teacher must always be able to mute or override it.

## 2. Who uses it

| Person | Where | What they need |
|---|---|---|
| Students (up to 20 per class) | The shared classroom board; they answer by voice, by tapping, or by typing | See the question, speak without fear of being wrong, hear kind corrections |
| Class teacher | Classroom board plus the live-class screen in the admin portal | Mute the tutor, take over, see who has a hand up, see cost and speed |
| School admin | Admin portal | Create classes, set the weekly schedule, add students, review each student's progress and cost |

There are **two portals**:
1. **Classroom portal**: the smart board seen by the whole class. Dark blue stage.
2. **Admin portal**: management screens on a laptop. Light background with a dark navy sidebar.

Students do **not** have individual logins or tablets in the current design. The classroom board is the student experience.

## 3. Visual identity

### Classroom portal
- **Feel:** a calm, bright classroom board. Big, friendly, readable from the back of the room.
- **Colours:** board deep blue `#0E2256` with glow `#1F449B`; chalk yellow `#FFD44D` (main accent, primary buttons, "now" states); paper `#F6F8FF` (the white board card); ink `#18213F` (text on paper); right/correct green `#1E9E5A`; mistake/fix red `#D9434A`; hand-raised blue `#5CA9FF`.
- **Fonts:** Baloo 2 (headings, rounded and friendly) and Atkinson Hyperlegible (reading text, chosen for clarity).
- **Signature elements:** the illustrated teacher character; a "voice ribbon" (a row of vertical bars that move when someone speaks); rounded cards; mint and red used only for right and wrong.
- **Sizes:** the screen is designed at 1600 × 900. Question text is 60 px, option text 32 px, body text 22 to 26 px.

### Admin portal
- **Feel:** clean and calm, built for daily use.
- **Colours:** navy `#101B3A` (sidebar, primary buttons); sun orange `#FF8A1F` (accent, charts); background `#F1F4FA`; mint for good, coral for needs help, amber for caution.
- **Fonts:** Bricolage Grotesque (headings and numbers) and Figtree (text).
- **Signature elements:** voice ribbon in the brand mark; large friendly numbers on dashboard cards; accuracy shown as a coloured bar (green 70% and above, orange 50 to 69%, red below 50%).

### Writing style (both portals)
- Plain, short, active sentences. Sentence case. No jargon.
- Buttons say exactly what they do: "Add class", "Add student", "Add to schedule", "Next question".
- Errors say what went wrong and how to fix it. They do not apologise.
- Empty screens invite the next action ("No classes yet. Add your first class on the right.").
- The tutor is encouraging: "Good try!", "Spot on!", "Almost there!". It never says "wrong" to a child. It says "Not yet" or "Let's fix it".

## 4. Classroom portal

### 4.1 The fixed frame (same on every screen)
1. **Top bar:** small "Aa" logo, class name ("Class 8 · English") with the lesson name below, a progress strip of 5 pills (green done, yellow now, grey to come) with the label "Question 3 of 5", five tool buttons (lessons, repeat, chat, sound, full screen), and the clock.
2. **Left column, teacher:** the teacher character in a soft spotlight; below it a name chip "Ms. Asha" with a voice ribbon (moving when she speaks, still when she is quiet); below that a white speech bubble with what she says.
3. **Centre, the board card:** a large white rounded card. Always starts with a small tag (for example "Choose the right answer"), then a big heading, then the content.
4. **Right column, the rail:** cards stacked top to bottom: a timer (when a question is timed), "Speaking now" (who, with a status chip), "Hands up" (up to 3 names in order), "Class" (class score and an avatar stack with "18 of 20 here").
5. **Bottom dock:** a status bar describing what is happening now, with a voice ribbon; buttons "Type instead", "Hands up", and a lesson action such as "Next question"; and a large round microphone button on the right.

### 4.2 Reusable components
- **Answer card:** letter badge (A to D) and answer text. Four states: ready (white), picked (yellow outline), right (green with a tick), wrong (red with a cross). Others dim after answering.
- **Banner:** a wide strip for feedback. Green ("Spot on, Diya!"), red ("Good try, Kabir. The answer is B."), yellow (hints and pause notices).
- **Sentence marks:** a mistake is underlined in red with a pink background; the fix is shown in green.
- **Chips:** small labels. "Your turn" (yellow), "Listening" (blue), "Correct" (green), "1 fix" (red), "Mic off" (grey).
- **Microphone button:** three states. Idle (yellow), live (yellow with a glowing ring), off (grey with a slash).
- **Student tile:** avatar with first-name initial, first name, a small ribbon. States: speaking (yellow outline), hand up (blue with a number badge), mic off (faded), not here (faded).
- **Timer ring:** circular countdown with the time in the middle.

### 4.3 The 12 screens

| # | Screen | Purpose | What is on it |
|---|---|---|---|
| 1 | Lesson picker | Start a class | A sheet over the board: "Choose today's lesson". Four cards: "Present simple: he, she, it" (5 questions), "Past simple: finished actions" (5 questions), "A or an?" (4 questions), "Free practice" (yellow card: "Say any English sentence. The tutor corrects it and explains each mistake."). A "Voice: US female" chip. Teacher says: "Good morning, Class 8! Pick a lesson to begin." |
| 2 | Lesson intro | Teach the rule before questions | Tag "Today's lesson". Heading "Present simple: he, she, it". Rule: "When the subject is he, she or it, the verb takes -s or -es." Example sentence broken into labelled word blocks: She (who) · goes (verb + es) · to school (where) · every day (when). Yellow banner "Say it with Ms. Asha: He goes to school every day." Two compare boxes: "I go · You go · We go" and "He goes · She plays". Button "Start questions". |
| 3 | Question (multiple choice) | Ask | Tag "Choose the right answer". Heading "Which sentence is correct?" Options A "He go home.", B "He goes home.", C "He going home.", D "He gose home." Rail shows timer 0:24, Diya "Your turn", hands up Kabir, Meera, Rohan, class score "2 of 2 right". Dock: "Say A, B, C or D, or tap an option". Teacher: "Listen carefully. Then say A, B, C or D." |
| 4 | Right answer | Celebrate and explain | Green tag "Correct". Green banner "Spot on, Diya! He goes home." B turns green with a tick, others dim. Box "Why: With he, she and it, the verb takes -s or -es." Teacher: "Spot on! With he, she and it, the verb takes -es. Say it with me: He goes home." |
| 5 | Wrong answer | Kind correction | Red tag "Let's fix it". Red banner "Good try, Kabir. The answer is B. Look at the green card." The student's pick A turns red with a cross; B green with a tick. Same "Why" box. Rail chip says "Not yet". Teacher: "Good try! With 'he' we say 'goes', not 'go'. Say it with me: He goes home." |
| 6 | Student speaking | Say a sentence correctly | Tag "Say it correctly". Heading "Fix this sentence". Red box "Not quite right: He play cricket on Sunday." White box "What I hear" showing live words as they are recognised ("He plays cricket on…" with a blinking cursor) and a large voice ribbon. Mic glowing. Dock "Listening to Kabir…". |
| 7 | Free practice correction | The tutor's output for any sentence | Red box "Aarav said: She don't likes to wake up early." Green box "Say it like this: She doesn't like to wake up early." "What changed" list: don't → doesn't ("With she, use doesn't."), likes → like ("After doesn't, the verb stays simple."). Yellow tip: "after 'doesn't', never add -s to the verb." Teacher: "Good try, Aarav! Two small changes." |
| 8 | Hands-up queue | Choose who speaks | Heading "Who speaks next?" with a switch "One student / Raised hands / Take turns". Grid of all 20 students. Diya speaking; Kabir, Meera, Rohan with badges 1, 2, 3; Aarav "Mic off"; Neel and Yash "Not here". Dock "Kabir is next. Get ready!" |
| 9 | Class chat | Read the conversation | A panel over the right side listing the conversation: Ms. Asha's questions and replies, each student's answer with a chip ("Right", "1 fix", "No mistakes"). |
| 10 | Lesson complete | Finish | Green tag "Lesson complete". Heading "Brilliant work, Class 8!" Big ring "4/5", star row (4 of 5 filled), "The class got 78% of its spoken sentences right." Boxes "Words to remember: goes, plays, watches" and "Best streak: Diya, 4 right in a row". Button "Another lesson". |
| 11 | Tutor paused | Teacher override | The tutor is greyed out. Yellow bar "Your teacher paused the tutor. Wait for your teacher. Hands can stay up." Dock "The tutor is paused. Your teacher will start it again." Mic off. |
| 12 | Component sheet | Reference | All components in one place: colours, answer card states, sentence marks, buttons, chips, status bar, progress, rail card, timer, banners, student tile. |

## 5. Admin portal

### 5.1 Screens that are built and working (real data)
Left sidebar: brand "Open Minds Tutor · Admin", then **Classes**, **Schedule**, **Students**, and a link back to the **Classroom board**.

**Classes**
- Shows a card for every class: name, grade and teacher, and a chip with the student count ("8 students"). Clicking a card opens that class's students.
- "Add a class" form: Class name (required, up to 40 characters), Grade (Pre-Group, then Grade 1 to 8), Teacher (optional).
- Messages: success "Added Class 3C"; duplicate "A class named Class 3C already exists."; empty "No classes yet. Add your first class on the right."

**Schedule**
- A Monday to Saturday week. Each session shows time range ("09:55–10:40"), class name, lesson title and a remove button.
- "Add a class to the week" form: Class, Day, Starts at, Minutes (default 45, allowed 10 to 120), Lesson.
- A class cannot have two overlapping sessions on the same day. Message: "Class 6B already has a session at 09:55 that day." A session may start the minute the previous one ends.
- Messages: "Added to the schedule", "Session removed". If there are no classes: "Add a class first, then come back to schedule it."

**Students (by class)**
- A class picker at the top, then a table: Roll, Student (avatar and name, opens that student's dashboard), Accuracy this week (coloured bar), Last assessment (date), remove button.
- "Add a student" form: First name (required), Last name, Roll number. Only these fields are collected, on purpose.
- Removing a student asks "Remove Aarav and all their results?" and deletes their results too.
- Empty: "No students in this class yet. Add the first one on the right." No data this week: "No assessments this week".

**Student dashboard** (the main analytics screen)
- Header: "← Class 6B", student name, "Class 6B · Roll 5".
- Four summary cards:
  1. **Accuracy this week** with a change chip against last week ("▲ 12 points vs last week", or "No last week to compare").
  2. **Speaking this week** in minutes, with the number of assessments.
  3. **Cost this week** with the all-time total ("$0.0143 in total").
  4. **Chapters attempted** with the total number of attempts.
- **Accuracy by week:** line chart, last 8 weeks, weeks without an assessment show as gaps.
- **Cost by week:** bar chart, last 8 weeks.
- **Where the cost comes from:** a split bar of voice versus tutor replies, with the rates used written underneath.
- **Latest assessments:** last 8, each with lesson name, score ("4/5", green at 70% and above) and date.
- **Chapter by chapter** table: Chapter, Attempts, Accuracy bar, Speaking minutes, Cost, Last taken, and a "Needs practice" chip when accuracy is below 60%.
- Empty state: "No assessments yet. Results appear here after the student finishes a lesson."

### 5.2 Screens designed as mock-ups only (not built yet)
- **Sign in:** school email and password, or school single sign-on.
- **Overview:** live classes strip with progress and cost against the $3.00 limit; cards for classes today, reply time, spent today, uptime; "Where the reply time goes" (waiting for silence, writing down speech, thinking of a reply, speaking it); "Needs a look" alerts; recent classes.
- **Live class:** buttons **Mute AI**, **Override session**, **End class**; the 20 student tiles; speaking order with a mode switch (One student, Raised hands, Take turns); live transcript with corrections; this class's cost and reply time.
- **Lessons:** lesson list with grades and status, and a step editor.
- **Reports:** class accuracy trend, most common mistakes, students needing a nudge.
- **Cost and usage:** per-class live cost, the $3.00 per class limit (warn at 80%, pause the tutor at 100%), cost split.
- **Safety and settings:** topics the tutor stays on, filters on every reply, tutor tone by grade band, privacy facts (voice recordings not stored, transcripts encrypted, never used to train models).

## 6. How the numbers are worked out

- **Accuracy** = total correct answers ÷ total questions, pooled across assessments. A 1-of-1 test and a 1-of-9 test together give 2 of 10 = 20%, not an average of 100% and 11%.
- **Week** = Monday to Sunday. The weekly chart shows the last 8 weeks, oldest first.
- **Chapter** = one lesson. Chapter totals add up attempts, accuracy, speaking minutes and cost per lesson, in the order the lessons are taught.
- **Cost** = voice cost + tutor cost.
  - Voice = speaking minutes × a per-minute rate. Placeholder rate: $0.0006 per minute (about a $0.75/hour GPU shared by 20 live streams).
  - Tutor = tokens ÷ 1,000 × a rate. Placeholder rate: $0.0002 per 1,000 tokens.
  - Both rates are sample figures to be replaced with measured server costs.
- **What one assessment record stores:** student, lesson, correct, total, speaking seconds, tokens used, time taken.

## 7. Data the admin portal holds

| Item | Fields |
|---|---|
| Class | name (unique), grade (0 = Pre-Group, up to 8), teacher |
| Student | first name, last name, roll number, class |
| Session | class, weekday (Mon to Sat), start time, minutes, lesson |
| Assessment | student, lesson, correct, total, speaking seconds, tokens, time |

## 8. Known gaps and open decisions

- **No login yet.** The admin portal is open to anyone who can reach it. A sign-in step is needed before real use.
- **Encryption at rest** for student records is not set up yet (the tender requires it).
- **The classroom board does not record results yet.** The admin portal has the place to receive them; hooking the board up to send each student's result is a later step. Demo data is used for now.
- **Latency:** measured on a laptop, about 2.1 to 2.3 seconds from end of speech to the tutor's first sound, against the tender's 0.5 second target. A GPU server is expected to bring this to roughly 0.7 to 1.0 second; sub-0.5 second needs streaming speech recognition as well. Estimates, not measurements.
- **Cost rates** are placeholders.
- **Later idea, parked:** admin uploads school books and the tutor teaches only from them (retrieval from documents). Not part of the tender; keep it as a future roadmap item.
