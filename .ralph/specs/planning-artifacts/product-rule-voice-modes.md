# Product Rule — Voice Experience Mode Selection

## Rule ID
PR-VOICE-001

## Status
Approved

## Summary
Each Salon must always offer the possibility of speech-to-speech as an experience option.

Two speech-to-speech experience variants are available:
- Tier 1: speech-to-speech with announcements present and a lower cost per second used
- Tier 2: speech-to-speech without announcements and a higher cost per second used

At Salon creation, the host chooses whether they want the speech-to-speech experience for themselves or not. At join time, each participant independently chooses whether they want the speech-to-speech experience or not.

## Product Rule
1. A Salon always offers the possibility of speech-to-speech as an experience option.
2. Speech-to-speech must be available in two pricing modes:
   - Mode A: with announcements present and a lower cost per second used
   - Mode B: without announcements and a higher cost per second used
3. At creation time, the host chooses whether they want to enable the speech-to-speech experience for themselves.
4. At join time, each participant chooses whether they want the speech-to-speech experience for themselves.
5. A Salon may contain a mix of participants using Base mode and participants using speech-to-speech mode.
6. Base mode must remain available and functional even when speech-to-speech is enabled for the Salon or for a participant.
7. Speech-to-speech is an opt-in enhancement for users who want a more natural live experience, with a lower-cost ad-supported variant and a higher-cost ad-free variant.
8. The system must treat Base mode and speech-to-speech mode as separate execution paths for audio handling, with speech-to-speech adding the live AI interpreter layer.

## Functional Requirements
- The host must be able to decide at Salon creation whether they personally use:
  - Base mode
  - Speech-to-speech with announcements and lower cost per second
  - Speech-to-speech without announcements and higher cost per second
- Participants must be able to decide at join time whether they personally use:
  - Base mode
  - Speech-to-speech with announcements and lower cost per second
  - Speech-to-speech without announcements and higher cost per second
- The system must preserve each user’s selected mode for the duration of the Salon unless they change it explicitly.
- Speech-to-speech mode must not block or degrade the Base mode experience for other participants.

## Expected Product Behavior
- In Base mode, the user experiences transcription and TTS only.
- In speech-to-speech mode with announcements, the user experiences the live interpreter path with announcements present and a lower cost per second used.
- In speech-to-speech mode without announcements, the user experiences the live interpreter path without announcements and a higher cost per second used.
- The host controls their own experience choice at creation time, and each participant controls their own experience choice at join time.

## Business Intent
This rule enables a clear product segmentation:
- Base mode supports a simple, accessible, lower-cost experience.
- Speech-to-speech with announcements supports a lower-cost entry point for live interpretation.
- Speech-to-speech without announcements supports a higher-value, ad-free experience with a higher per-second cost.

## Success Metrics
The following metrics should be tracked to evaluate whether the rule achieves its product goals:
- Speech-to-speech adoption rate: percentage of participants who opt into speech-to-speech when it is available.
- Lower-cost tier adoption rate: percentage of speech-to-speech users selecting the announcements-present variant.
- Ad-free tier adoption rate: percentage of speech-to-speech users selecting the no-announcements variant.
- Base mode completion rate: percentage of Salon sessions that successfully complete in Base mode without fallback or abandonment.
- Speech-to-speech satisfaction score: average user rating or feedback score for the live interpreter experience.
- Speech-to-speech conversion rate: percentage of users who upgrade from Base mode to speech-to-speech in a subsequent session.
- Session success rate: percentage of sessions that complete without critical audio, translation, or routing failures.
- Cost efficiency ratio: relative operating cost per successful session between Base mode and the two speech-to-speech variants.
