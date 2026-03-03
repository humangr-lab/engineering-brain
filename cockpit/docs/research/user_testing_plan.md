# User Testing Plan — Ontology Map Toolkit

**Document type**: UX Research Protocol
**Version**: 1.0
**Date**: 2026-02-27
**Toolkit under test**: Ontology Map Toolkit v1.0
**Dataset**: Engineering Brain (33 nodes, ~40 edges, 10 submaps)
**Study duration**: 1 week for all sessions; 30 minutes per participant

---

## 1. Objectives

### 1.1 Primary Objective — Validate the 5-Minute Understanding Metric

This study defines a core success criterion (derived from the SPEC's usability goals and the on-rails zero-config philosophy): a user who has never seen the tool should be able to grasp the high-level architecture of the visualized system within five minutes of first contact. This study will determine whether the current implementation meets that bar. "Grasping architecture" is operationally defined as: the participant can correctly describe the system's major components, identify at least two inter-component relationships, and locate a specific named module without facilitator guidance.

Primary research question: Do users achieve functional orientation within 5 minutes when exploring a 33-node Engineering Brain graph for the first time?

### 1.2 Secondary Objective — Identify UX Friction Points

Beyond the headline metric, this study maps the specific moments where navigation, search, and drill-down cause confusion or error. Friction points are events where a participant pauses for more than 10 seconds without making progress, backtracks unexpectedly, or verbalizes confusion. Prioritized friction points will feed directly into the P0/P1/P2 backlog.

Secondary research question: Which interaction patterns — layout switching, submap entry, Cmd+K search, or node selection — generate the most friction, and why?

### 1.3 Tertiary Objective — Establish a Usability Baseline

A System Usability Scale (SUS) score provides a standardized, benchmark-comparable measure of perceived usability. The target for this study is a SUS score of 68 or above, which corresponds to the industry average for tools rated "good." Scores below 68 indicate systemic usability problems that must be addressed before broader rollout. A Net Promoter Score (NPS) is collected as a secondary satisfaction signal.

Tertiary research question: Does the toolkit meet or exceed a SUS score of 68 as rated by a mixed-expertise participant group?

---

## 2. Participants

### 2.1 Composition and Expertise Profile

A minimum of five participants is required to yield actionable patterns while remaining feasible within a one-week window. The composition intentionally spans expertise levels to surface different failure modes.

| Slot | Profile | Count | Rationale |
|------|---------|-------|-----------|
| P1–P2 | Senior developers (5+ years, architecture exposure) | 2 | Represent the primary user persona; validate core workflow |
| P3–P4 | Junior developers (1–3 years, limited architecture exposure) | 2 | Surface orientation and vocabulary barriers |
| P5 | Non-developer (product manager or UX designer) | 1 | Validate whether visual encodings communicate without code context |

Total: 5 participants. If recruitment allows, extending to 8 participants (adding one more per slot) will materially improve confidence in qualitative patterns.

### 2.2 Recruitment Criteria

All participants must satisfy these baseline criteria:

- **No prior exposure** to the Ontology Map Toolkit or the Engineering Brain visualization. Participants who have seen screenshots or demos must be excluded.
- **Senior and junior developers**: Must have professional experience writing or reviewing code. Familiarity with the concept of software architecture (layers, modules, dependencies) is required. Familiarity with 3D graphics or data visualization tools is not required and should not be used as a filter.
- **Non-developer**: Must have professional experience working with software teams (sprint planning, roadmaps, feature specifications). No coding ability required.
- **Hardware**: Must be able to attend a session on a 1920×1080 display running Chrome latest. Remote participants will be excluded unless screen sharing fidelity can be guaranteed.

Participants may be sourced from internal colleagues not involved in this project, external developer communities, or UX research panels. Screener questions: (1) "Have you used or seen the Ontology Map Toolkit?" (2) "Describe your coding experience in years and primary role."

### 2.3 Compensation and Scheduling

Each participant receives a $50 gift card for a 30-minute session. Sessions are scheduled with at least 30 minutes of buffer between them to allow the facilitator to reset the environment and review notes. All five sessions should be completed within one calendar week to limit external variable drift (product updates, word-of-mouth leakage).

Recommended schedule: 2 sessions on day 1 (pilot + P1), 2 sessions on day 3 (P2 + P3), 2 sessions on day 5 (P4 + P5), with day 2 and day 4 reserved for note synthesis and task adjustment if the pilot reveals problems.

---

## 3. Environment Setup

### 3.1 Hardware and Browser

- **Display**: 1920×1080, external monitor if laptop is used
- **Browser**: Chrome (latest stable release), no extensions active, hardware acceleration enabled
- **Input**: Mouse and keyboard (no trackpad-only sessions — 3D orbit control requires precise mouse movement)
- **Audio**: Participant microphone active for think-aloud recording

### 3.2 Dataset Configuration

The toolkit is loaded with the Engineering Brain dataset:

- 33 nodes representing the Engineering Brain architecture (adapters, epistemic modules, learning modules, retrieval, MCP server, validation, seeds)
- Approximately 40 edges encoding relationships (CONTAINS, DEPENDS_ON, CALLS, GENERATES)
- 10 submaps providing drill-down views for dense subsystems
- Default orbital layout on initial load
- Dark theme active (the toolkit's default)

No custom schema overrides. The inference engine's automatic configuration is what is being tested. The facilitator must not alter the dataset or schema between sessions.

### 3.3 Recording Protocol

Every session is recorded with both screen capture and audio. The screen recording must capture the full browser window at native resolution. Audio captures the participant's think-aloud narration and facilitator prompts. Recordings are stored in a private, access-controlled folder. Participants provide written informed consent before recording begins.

Screen capture software: OBS Studio or equivalent with lossless local recording. Audio: system microphone or headset, monitored for quality before the session begins.

### 3.4 Facilitator Script

**Introduction (read verbatim)**:

> "Thank you for joining. I am going to show you a software visualization tool we are testing. I want to be clear: we are evaluating the tool, not you. There are no right or wrong answers. If something is confusing, that is the tool's problem, not yours.
>
> I will ask you to think aloud as you explore — describe what you see, what you expect to happen, and what surprises you. I cannot answer questions about how the tool works, but I can confirm whether a task is complete.
>
> Do you have any questions before we begin?"

**During-session prompts (use sparingly, only when participant is silent for more than 15 seconds)**:

- "What are you thinking right now?"
- "What do you expect would happen if you clicked there?"
- "What would you try next?"

Facilitators must not say "good job," "correct," "almost," or any word that implies evaluation of participant performance. If a participant explicitly asks for help, respond with: "I want to see how you would approach it on your own. What would you try first?"

---

## 4. Task Scenarios

Each task is presented on a printed card to avoid the participant reading ahead. The facilitator reads the task aloud, then places the card in front of the participant. Time starts when the facilitator finishes reading. The facilitator silently records start time, completion time, error events, and notable verbalizations.

### T1 — Orientation (Time limit: 2 minutes)

**Prompt**: "Take a moment to explore what you see. Don't click anything yet. Tell me: what does this visualization represent? What do the colors mean? What do the shapes mean? What do you think the lines between elements represent?"

**Success criteria**: Participant correctly identifies at least 3 of the following visual encodings without prompting — node color encodes category/type, node size encodes significance or complexity, connecting lines represent dependencies or relationships, the 3D space is navigable, the floating labels are node names.

**Data to collect**: Number of visual encodings identified, time to first verbalization about system meaning (not just "it's a graph"), any misinterpretations that persist after initial exploration.

**Failure signal**: Participant identifies fewer than 3 encodings within 2 minutes, or articulates a fundamentally wrong mental model ("these look like servers," "these are calendar events") without self-correcting.

### T2 — Navigation (Time limit: 3 minutes)

**Prompt**: "Find the module called Crystallizer. Once you find it, tell me what you can learn about it from the interface."

**Success criteria**: Participant navigates to the Crystallizer node AND opens or reads its detail panel. Both conditions must be met. Simply hovering without reading the panel does not count.

**Data to collect**: Navigation path taken (search vs. manual orbit vs. auto-tour), time to locate the node, time to open the detail panel, content read aloud from the panel, any confusion about what information the panel contains.

**Failure signal**: Participant cannot locate the node within 3 minutes, or locates it but does not discover the detail panel interaction.

### T3 — Drill-Down (Time limit: 3 minutes)

**Prompt**: "There is a submap for the Seed Knowledge Files section of this system. Enter that submap and describe the pipeline you see inside it."

**Success criteria**: Participant successfully enters the Seed Knowledge Files submap AND verbally identifies at least 3 distinct nodes visible within it. The description does not need to be technically accurate — the criterion is spatial orientation within the submap, not domain knowledge.

**Data to collect**: Time to locate the submap entry point, navigation method used (click on node vs. breadcrumb vs. minimap), number of nodes identified inside, whether the participant understands they have entered a drill-down view (vs. thinking the view changed for another reason), exit behavior.

**Failure signal**: Participant cannot find the submap entry within 3 minutes, enters the submap but cannot identify any interior nodes, or expresses fundamental confusion about the hierarchical navigation model.

### T4 — Search (Time limit: 2 minutes)

**Prompt**: "Use the keyboard shortcut Command-K to open the search panel. Search for the word 'security'. Count how many results appear."

**Success criteria**: Participant opens the search overlay using Cmd+K AND locates search results containing "security"-related nodes. An exact count is not required for success — identifying that results exist and reading at least one result aloud is sufficient.

**Data to collect**: Whether participant knows the Cmd+K shortcut (prior knowledge vs. discovery), time from prompt to overlay open, search term entered, results listed, whether participant clicks a result to navigate, any confusion about result ranking or presentation.

**Failure signal**: Participant cannot open the search overlay within 30 seconds (shortcut undiscoverable), or opens it but cannot interpret the results.

**Note**: If the participant is on a non-Mac keyboard without a Command key, the facilitator should clarify: "On this keyboard, use Ctrl+K."

### T5 — Layout Comparison (Time limit: 2 minutes)

**Prompt**: "Switch the visualization from the current layout to the Pipeline layout. Then switch to the Orbital layout. After trying both, tell me which you prefer and why."

**Success criteria**: Participant successfully switches between at least two named layouts AND articulates a stated preference with any reasoning (even "I don't know, this one feels clearer" qualifies).

**Data to collect**: Time to find the layout switcher control, number of attempts before successful switch, layouts explored, verbalized preference, any confusion about what changed between layouts, whether the participant understands the conceptual difference between pipeline and orbital organization.

**Failure signal**: Participant cannot find the layout switcher within 90 seconds, or switches layouts but cannot articulate any preference or observation about the difference.

### T6 — Conversation Mode (Time limit: 3 minutes) — *requires F-15 implementation*

**Prompt**: "Open the chat panel and ask the AI: 'What is the most connected module in this system?' Observe how the system responds."

**Success criteria**: Participant opens the chat panel, submits a natural language query, and observes the AI response (text + map highlight). Participant can articulate whether the response was useful.

**Data to collect**: Time to discover chat panel toggle, query phrasing (verbatim), whether participant notices map highlights triggered by agent, perceived response quality (Likert 1-5), follow-up questions attempted, BYOK setup friction (if applicable).

**Failure signal**: Participant cannot locate the chat panel within 60 seconds, or the AI response is nonsensical/empty, or the participant does not notice the spatial map actions triggered by the agent.

**Note**: This task is conditional on F-15 being implemented. If testing occurs before F-15, skip T6 and note its absence in the analysis report. The 5-minute understanding metric (Section 1.1) is evaluated using T1-T5 only.

---

## 5. Metrics

### 5.1 Quantitative Metrics

The following quantitative data points are recorded for each task and each participant:

| Metric | Collection method | Aggregation |
|--------|-------------------|-------------|
| Task completion rate (%) | Binary pass/fail per task | Median across participants per task |
| Time-on-task (seconds) | Stopwatch, task start to completion or timeout | Median per task; flag outliers >2 SD from mean |
| Error count | Facilitator tally (wrong click, wrong shortcut, navigated to wrong node) | Total per task per participant |
| Click count | Session recording frame analysis (post-session) | Median per task |
| Time-to-first-meaningful-interaction | From recording load to first intentional orbit/click | Per participant; target <30 seconds |

A task is marked as "completed with assistance" if the facilitator provided a non-leading prompt (e.g., "what would you try next?") that directly preceded the successful action. Completed-with-assistance counts separately from clean completion.

### 5.2 Qualitative Metrics

- **Think-aloud transcripts**: Full transcription of participant verbalizations per session. Transcripts are tagged with task ID, timestamp, and event type (confusion, delight, expectation violation, unexpected discovery).
- **Preference rankings**: For T5 (layout comparison), participants rank layouts. Across all five participants, a preference distribution is computed.
- **Mental model descriptions**: From T1, participant descriptions of the visualization are coded for accuracy and completeness using a rubric derived from the actual node taxonomy.
- **Post-task verbal debrief**: After all five tasks, the facilitator asks three open questions: (1) "What was the most disorienting moment?" (2) "What worked better than you expected?" (3) "If you could change one thing, what would it be?"

### 5.3 System Usability Scale (SUS)

The SUS questionnaire is administered immediately after the five tasks, before the verbal debrief. Participants rate each item on a scale of 1 (Strongly Disagree) to 5 (Strongly Agree).

**The 10 SUS items** (administered in this exact order, with no re-ordering):

1. I think that I would like to use this system frequently.
2. I found the system unnecessarily complex.
3. I thought the system was easy to use.
4. I think that I would need the support of a technical person to be able to use this system.
5. I found the various functions in this system were well integrated.
6. I thought there was too much inconsistency in this system.
7. I imagine that most people would learn to use this system very quickly.
8. I found the system very cumbersome to use.
9. I felt very confident using the system.
10. I needed to learn a lot of things before I could get going with this system.

**Scoring formula**:

Items 1, 3, 5, 7, and 9 are positively worded (odd items). Their contribution = raw score − 1.

Items 2, 4, 6, 8, and 10 are negatively worded (even items). Their contribution = 5 − raw score.

Sum all ten contributions, then multiply by 2.5.

```
SUS Score = ( (Q1−1) + (5−Q2) + (Q3−1) + (5−Q4) + (Q5−1)
             + (5−Q6) + (Q7−1) + (5−Q8) + (Q9−1) + (5−Q10) ) × 2.5
```

The result is a score between 0 and 100. Score interpretation:

| SUS Score | Grade | Adjective |
|-----------|-------|-----------|
| ≥ 85 | A | Excellent |
| 72–84 | B | Good |
| 68–71 | C | Acceptable (study target) |
| 51–67 | D | Poor |
| ≤ 50 | F | Awful |

The study target is a SUS score of 68 or above. Individual SUS scores are averaged across all five participants. If standard deviation exceeds 15 points, participant profiles should be analyzed separately (senior vs. junior vs. non-developer) before reporting a single aggregate score.

### 5.4 Net Promoter Score (NPS)

After the SUS questionnaire, ask: "On a scale of 0 to 10, how likely are you to recommend this tool to a colleague who works on software systems?"

- Promoters: 9–10
- Passives: 7–8
- Detractors: 0–6

NPS = % Promoters − % Detractors. With 5 participants the NPS is directional only, not statistically robust. Report raw scores and distribution rather than a calculated NPS percentage.

---

## 6. Analysis Template

### 6.1 Quantitative Aggregation

After all sessions are complete, compile a per-task results table:

| Task | Completion rate | Median time (s) | Median errors | Median clicks |
|------|-----------------|-----------------|---------------|---------------|
| T1 Orientation | % | s | n | n |
| T2 Navigation | % | s | n | n |
| T3 Drill-Down | % | s | n | n |
| T4 Search | % | s | n | n |
| T5 Layout | % | s | n | n |

Flag any task where completion rate falls below 80% as a P0 friction source. Flag any task where median time exceeds the task time limit as a P1 friction source.

Also compute: aggregate 5-minute understanding metric. This is defined as whether a participant completes T1 + T2 within the combined 5-minute window (2 min + 3 min). This is the primary success metric from the SPEC.

### 6.2 Friction Identification

For each verbalized confusion or task failure event, record:

- **Friction ID**: sequential (F-001, F-002, …)
- **Task**: which scenario triggered it
- **Participant count**: how many of 5 participants experienced it
- **Severity**: 1 (cosmetic), 2 (minor delay), 3 (task failure), 4 (session abandonment)
- **Description**: what happened, verbatim quote if available

Priority score = participant count × severity. Sort descending. The top 3 friction points by priority score are the primary recommendations.

### 6.3 Affinity Mapping

Qualitative feedback from think-aloud transcripts and verbal debriefs is clustered using affinity mapping:

1. Each distinct observation or comment is written on a separate card (digital or physical).
2. Cards are grouped by theme without predefined categories.
3. Themes that emerge from 3 or more participants are treated as confirmed findings.
4. Themes from 1–2 participants are flagged as hypotheses requiring further investigation.

Common affinity themes to watch for: "visual overload," "layout orientation confusion," "color meaning unclear," "search results ranking," "submap entry discoverability," "detail panel content depth," "auto-tour usefulness."

### 6.4 Report Template

The final report is delivered as a 3–5 page document with the following structure:

**Executive Summary** (one page): SUS score, 5-minute understanding pass rate, top 3 friction points, overall recommendation (ship / ship with minor fixes / hold for redesign).

**Per-Task Results Table**: The quantitative aggregation table from section 6.1, annotated with completion rate color coding (green ≥ 80%, yellow 60–79%, red < 60%).

**Friction Heatmap**: A visual mapping of friction events onto the five task scenarios, with severity indicated by color intensity. Produced from the friction identification table in section 6.2.

**SUS Score**: Per-participant scores, aggregate score with standard deviation, comparison to the 68 target, and breakdown by expertise group (senior developer, junior developer, non-developer) if variance is high.

**Recommendations**: Three tiers:

- **P0** (block release): Issues where completion rate < 60% or task failure causes participant to lose all orientation. Must be fixed before any broader rollout.
- **P1** (fix in next iteration): Issues where completion rate 60–79%, or where friction is consistent across 3+ participants but does not cause failure.
- **P2** (backlog): Issues raised by 1–2 participants, or qualitative preferences without corresponding task failure.

---

## 7. Pilot Test

A pilot session is conducted before the five main sessions. The pilot participant should match the senior developer profile (the primary target persona) but is excluded from the final analysis.

**Pilot objectives**:

1. Validate that task prompts are unambiguous — if the pilot participant asks "what does 'submap' mean?" the T3 prompt must be reworded.
2. Validate task timing — if any single task exceeds its time limit in the pilot, the difficulty level is too high. Adjust either the task scope (narrower goal) or the time limit (add 60 seconds) before the main study.
3. Validate facilitator script flow — confirm that 30 minutes is sufficient for 5 tasks + SUS + debrief.
4. Validate recording setup — confirm that screen capture and audio are both clean before any main session.

**Adjustment trigger**: If pilot task completion rate is below 50% on any single task, that task is rewritten before the main study begins. A completion rate of 50–79% in the pilot warrants task prompt clarification only. A completion rate of 80%+ in the pilot proceeds to main study unchanged.

The pilot session is run no later than two days before the first main session, leaving time to revise materials.

---

## Appendix A: Session Checklist

Before each session:

- [ ] Browser cache cleared, no history of the toolkit URL
- [ ] Toolkit loaded to initial state (orbital layout, dark theme, Engineering Brain dataset)
- [ ] Screen recording software active and tested
- [ ] Audio recording active and tested
- [ ] Task cards printed and ordered (T1 through T5)
- [ ] SUS questionnaire printed (one copy per participant)
- [ ] Consent form signed before recording begins
- [ ] Stopwatch or timing app ready
- [ ] Observation notes template open

After each session:

- [ ] Recording saved and labeled with participant ID (P1–P5, not by name)
- [ ] Raw time-on-task notes transferred to aggregation sheet
- [ ] Friction events logged with ID, task, count, severity
- [ ] SUS scores calculated immediately (formula in section 5.3)

---

## Appendix B: Data Privacy

Participant names are never stored alongside session recordings or analysis data. Each participant is assigned a pseudonymous ID (P1 through P5) at recruitment. The mapping between real name and participant ID is stored in a separate, access-controlled document and deleted after compensation is processed. Session recordings are retained for 90 days after the final report is delivered, then permanently deleted.

Participants are informed of recording and data handling in the consent form before any session begins.
