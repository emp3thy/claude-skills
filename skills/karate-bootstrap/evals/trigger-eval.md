# Trigger eval for karate-bootstrap

Checks that the skill's description makes Claude Code pick `karate-bootstrap` for the requests
it is for and leave it alone for the ones it is not. This repository's tests never call a
model, so the automated part is `tests/test_kb_skill_md.py` (the description must carry the
key terms of every prompt below and must say it is not for unit tests). The model-in-the-loop
part is manual.

## How to run the manual part

1. Install the skill (README, "karate-bootstrap") in a Claude Code session with no other
   karate-related skill.
2. For each prompt below, start a fresh conversation in a repository that matches the prompt
   and paste it verbatim.
3. Record whether Claude invoked `/karate-bootstrap` (or announced it was using the skill)
   before doing anything else.
4. Pass criterion: every "must fire" prompt fires; no "must not fire" prompt fires. Record the
   run date and model in the table at the end.

## Must fire

- Add karate tests to this service.
- Bootstrap integration tests for this repo; it has none.
- Build a testcontainers suite for this service so it runs in our ADO pipeline.
- We need a first set of Karate feature files for the deals API, running against real
  Postgres and Artemis in containers.
- Give this Spring Boot app a ground-truth integration test suite I can run locally.

## Must not fire

- Add unit tests for DealService.
- Write JUnit tests for the validator class.
- Increase the unit test coverage of the pricing module.
- Run the existing Karate suite and tell me what fails.

## Runs

| Date | Model | Must fire | Must not fire | Notes |
|------|-------|-----------|---------------|-------|
| (none yet) | | | | |
