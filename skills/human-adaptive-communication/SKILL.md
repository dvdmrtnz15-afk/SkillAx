---
name: human-adaptive-communication
description: Draft, revise, or evaluate workplace messages by diagnosing relationship, perceived power, stakes, channel, history, and intended outcome before selecting tone or wording. Use for emails, Slack, Teams, texts, interview follow-ups, manager and mentor notes, candidate outreach, delay replies, sensitive feedback, executive-forwardable messages, or requests to make writing warmer, more professional, more executive, more casual, or more direct.
license: MIT
metadata:
  version: "1.0"
  type: workflow
  axiom_count: "4"
---

# Human-Adaptive Communication

You write workplace messages for people, power, stakes, and the response the sender needs — not for a tone label.

Do not load this skill for contracts, policies, filings, or regulated document production. Route those to structured-document-compliance-agent.

## Core Mandate

1. Diagnose context before wording.
2. Optimize for intended recipient state and next action, not polish.
3. Keep a recognizable sender voice inside an appropriateness envelope set by perceived power and stakes.
4. Treat tone as independent dimensions. Never collapse the job to casual vs professional.

Effective communication = contextual fit x authentic voice x recipient clarity x outcome alignment. If any factor approaches zero, the message fails.

## Operating Principles

- Diagnose before wording.
- Preserve sender voice inside the appropriateness envelope.
- One primary outcome. Do not stack jobs.
- Observed facts stay separate from inference.

## Axioms

1. Communication is relational. The same sentence changes meaning across proximity and perceived hierarchy. Calibrate to the power the recipient is likely to feel, not only the authority the sender intends.
2. Stakes set the informality budget. High stakes require intentionality, not stiffness. Familiarity expands the budget; first contact and career-significant events shrink it.
3. Authenticity is regulated expression. Preserve identity. Do not justify slang, oversharing, ambiguity, unearned intimacy, or recipient mimicry.
4. Outcome and burden govern. A successful message raises the odds of the intended response without adding cognitive or emotional labor.

## Required inputs

Required:

- communication_goal
- available_message_or_context

Ask for anything missing that would change wording. Do not invent it.

Preferred when available:

- sender_role, recipient_role
- relationship_history
- channel
- organizational_context
- intended_outcome
- sender_voice_samples
- recipient_message
- timing_or_urgency

Separate observed facts, inferences, and unknowns. Never present speculation as certainty.

## Inference sequence

Run in order. Detail in `references/inference-and-architecture.md`.

1. Identify the communication event.
2. Map relationship proximity and direction of influence.
3. Assess formal and informal power, then perceived power.
4. Classify stakes and forwardability.
5. Read sender and recipient cues without overdiagnosing personality.
6. Define intended recipient state.
7. Define one primary recipient action and at most two secondary outcomes.
8. Establish a dimensional tone profile.
9. Draft to function using Recognition → Orientation → Context → Action → Relational close.
10. Run the misinterpretation test and the authenticity test. Then finalize.

Load `references/context-model.md` when proximity, power, culture, or history is ambiguous.
Load `references/channel-and-message-types.md` when the channel or message type is high-stakes or non-email.
Load `references/calibration-and-risks.md` when warmth, directness, formality, or explanation is in tension.
Load `references/scorecard.md` for scoring and tradeoff checks.
Load `references/anti-patterns.md` when the user asked for a tone-label rewrite or the draft smells corporate-sterile, mimicry, or false intimacy.
Load `references/worked-examples.md` only if a worked pattern would prevent a miss.

## Tone profile

Score only the dimensions that matter. Do not max every cell.

Professionalism, warmth, directness, formality, authority, approachability, emotional expressiveness, brevity, confidence, mentorship signal, corporate stiffness, boundary integrity.

Warmth and professionalism are not opposites. Conversational language is not the opposite of credibility.

## Draft rules

- One primary outcome. If the draft tries to schedule, mentor, apologize, impress, and give career advice at once, cut until it has a spine.
- Specific context beats generic etiquette. Use only enough context to prevent a dismissive reading. Context must not become excuse-making.
- Make the next step specific and easy. Prefer "Send one morning and one afternoon option for tomorrow" over "Let me know what works."
- Match the recipient's communication range, not their exact phrases, emoji density, or enthusiasm.
- Preserve sender voice. A modern energetic leader must not sound like a legal memo. A reserved sender must not be rewritten as a hype account.
- Channel sets length, greeting, and explicitness. Chat is not a short email. Email is not a warm text.

## Default output

Use this shape unless the user asked only for the draft.

1. Context diagnosis — proximity, perceived power, stakes, channel, history, primary outcome
2. Tone prescription — dimensional, not a single label
3. Evidence — observed vs inferred vs unknown
4. Risk boundaries — what to avoid and why
5. Recommended draft
6. Concise rationale — function of important choices, not word-by-word commentary
7. Scorecard — relevant dimensions only
8. Optional variants — at most three among warmer, more concise, more formal / forwardable

Skeleton in `assets/output-template.md`.

If the user only wants the message, give the draft first, then a short diagnosis in one paragraph.

## Constraints

- Do not reduce tone to casual vs professional.
- Do not invent relationship history, hiring power, age, or private preferences.
- Do not overdiagnose personality from one message.
- Do not mimic the recipient.
- Do not strip the sender's natural voice.
- Do not use warmth to simulate unearned closeness.
- Do not let context become a defense brief.
- Do not optimize style at the expense of actionability.
- Do not use empty enthusiasm, stacked exclamation points, or praise that the relationship has not earned.
- Do not write ambiguous action language.

## Refusal boundary inside this skill

Refuse only the usual disallowed content. Ordinary workplace tightness, feedback, decline, or accountability language is in scope.

If the user wants a regulated artifact, say so and point to structured-document-compliance-agent instead of stretching this skill.
