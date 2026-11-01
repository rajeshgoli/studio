# 1. Working in this repo

I am Rajesh, I own the repo and am the only human on it. Studio is where I make videos with agents: songs and talking videos. It runs on my Mac Studio: recording happens there, and everything else can be viewed remotely.

This file is the whole standing contract. Read all of it.

**Explain music and audio in plain words.** I am not trained in music. Define every musical or technical term when you use it, or say it plainly.

**Media never goes in git.** Recordings, takes, reference recordings (often copyrighted), renders and everything built from them stay on the Mac; `.gitignore` covers them. Check `git status` before every commit and never force-add an ignored file.

**My files are mine.** Never delete a take, recording or project file you did not create in this session. Look at the target before removing anything, and move rather than delete. A recording studio may be in use: don't restart its service without telling me first.

**Share files as absolute paths.** I am often remote through sm. End any message that hands over a file with its full path, and never `open` or play anything on the Mac.

## 2. Your workflow

**Name yourself.** Before you begin work, check your name with `sm me`. If it is `claude-<slug>`, `codex-fork-<slug>`, or anything similar, replace it with `sm name st-<newname>`. A name that says what you are doing (ticket and role, or the song or video you are producing) beats `claude-<slug>`, because a name that says what you were doing is what lets me restore you. The `st` prefix tells me you're working on Studio rather than another repo.

**Worktrees.** Every agent works in its own worktree under `~/worktrees/st-<ticket>-<slug>`, build outputs inside. Never switch branches or build in `~/projects/studio`: other agents share it, and it stays on `main`. Productions (each song or video, with its media) are not in this repo: they live in a separate content checkout, `$STUDIO_CONTENT` (default `../studio-content`). A producer works there and follows that checkout's own instructions, coming here only to change code.

**Claim your work.** Start a ticket with `sm ticket <N> --setup-worktree` and work in the worktree it prints (plain `sm ticket <N>` if you already have one). When you open a PR, or take over someone else's, run `sm pr` from its branch. Put `Closes #<N>` in the PR body for each ticket the PR finishes; "Implements #N" does not close it. Reviewers and scouts don't claim. When you are retired, sm deletes your worktree if nothing would be lost; if something there must outlive you, run `sm worktree keep --reason "<why>"`.

**Heavy work goes through the queue.** Renders, source separation and long-running services go through `sm queue run` with a memory budget; sm kills unqueued commands that pass about 1 GiB. Quick checks can run directly.

Workflow as usual:
1. Check your change: type-check the animation, look at stills for anything visual, and run a queued render for anything that changes the final video. For audio, measure what you can (levels, pitch, timing) and say plainly that you could not listen.
2. If I need to test something let me know exactly what to try out. If you can test directly that's preferred.
3. Once all feature requests above are completed and verified, you may exit to step 4. If I have feedback or if you find live test failures, repeat steps 1 and 2 until exit to 4 criteria is met.
4. Once functionality is in place, create a PR for your changes.
5. Use instructions in Review loop section to get your PR in a clean mergeable state.
6. Once clean, `gh pr merge --squash --delete-branch --match-head-commit <reviewed sha>`. For any blocker, such as conflicts, fix it or ask me. Then delete any local branches and worktrees you created.
7. In `~/projects/studio`: `git pull --ff-only`, so the checkout that services run from is `main`.
8. Let me know.

**Memos.** Direction-setting work (a new mode, anything I must decide) starts as a memo ticket: write `docs/working/<ticket>_<name>_memo.html` from `docs/memo_template.html` (keep its print and dark-mode buttons), publish it with `sm doc publish`, and wait for my sign-off before building. Define every term at first use. Once I approve a memo, it becomes a lane goal on the sm board (`sm board lane add <goal-ticket>`), with its sub-tickets under it (`sm board under <ticket> <goal>`).

## 3. Review loop

**Requesting a review.** Request with `sm request-review <pr-number>`. This is registration only; sm picks the reviewer and wakes you when the review is on the PR. Go idle and wait — do not poll. If sm refuses, or wakes you saying no reviewer could take it, tell me and stand by. Do not post `@codex review` yourself.

Before acting on a review, confirm it belongs to your current request and was posted after your latest push. A review existing is not enough on its own.

Then:

1. **Classify every finding: valid, partially valid, or invalid.** Do not skip this. A review is not gospel — push back with reasoning where it is wrong.
2. **Correctness only** — no document nits, no wording preferences, no nits about following process for process's sake. That excludes process *preference*, not process *correctness*: when the thing under review is a workflow, an instruction file, CI, or a build script, its behaviour is the correctness surface, and a defect in it is a correctness finding however procedural it sounds.
3. **Any unresolved P1 blocks.** A P1 is resolved either by fixing it or by answering it: a P1 you classify invalid, with your reasoning posted on the PR, is resolved and does not block. If the reviewer re-raises the same P1 after reading your reasoning, that is a real disagreement: escalate it rather than looping. A round that returns only P2 or lower, or a clean review, exits the loop. Do not keep chasing P2s and P3s.
4. Fix, push, and re-review at the exact head. Fewest rounds to correctness — which does not mean dropping correctness issues.

## 4. Repo reference

- `songs/` - song shorts: analysis, generated score, mix, recording studio and animation. `songs/README.md` explains each step, setting, and where songs live.
- `docs/memo_template.html` - memo skeleton.

Setup on a fresh checkout:

```bash
cd songs && uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -r requirements.txt
(cd remotion && npm install)
```
