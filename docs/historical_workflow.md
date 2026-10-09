### The approach

I use a GPT–Claude council approach to examine technical problems from different perspectives. I configure roles and instructions, compare the reasoning, and test the proposed solution in my project before accepting it.

My inputs are the problem description, relevant code, error logs and project constraints. The models help with diagnosis and review; I run commands, inspect the repository and apply changes.

### Role setup

*Reconstructed role instructions — the original wording was not retained. These are proposed prompts for reproducing the approach.*

| Role | Purpose | Receives |
|---|---|---|
| Technical analyst | Propose explanations and ordered debugging steps | Problem, evidence and constraints |
| Critical reviewer | Challenge assumptions and suggest tests | Problem, evidence and the proposed analysis |
| Me | Verify the diagnosis and choose the change | Both analyses and the actual test results |

**Technical analyst**
> Analyze the supplied technical problem. Separate observations from hypotheses. Compare plausible causes and propose the smallest tests that distinguish them. Explain the suggested change, its risks and its success criteria. Do not assume access to files or logs that were not supplied.

**Critical reviewer**
> Review the proposed diagnosis against the original evidence. Identify unsupported assumptions, missed explanations and risky changes. Prefer a discriminating test over agreement. State what evidence would confirm or reject the recommendation.

### Article Platform · PostgreSQL connection issue

**Actual project case — 1 September 2026.** The council-style walkthrough below is reconstructed from the resolved issue, rather than a saved model conversation.

| Step | Case |
|---|---|
| Symptom | Prisma returned `P1000 Authentication failed` when connecting through `localhost:5432`. |
| Competing checks | Incorrect credentials versus connection to a different PostgreSQL instance. |
| Distinguishing evidence | Authentication inside the intended container worked; the host connection on port 5432 reached another PostgreSQL instance. |
| Change | Expose the container as `5434:5432` and point `DATABASE_URL` to `127.0.0.1:5434`. |
| Verification | `prisma migrate dev --config prisma.config.ts --name init` applied `20260901183240_init` and reported that the database was in sync with the schema. |

The useful distinction was **wrong credentials versus wrong destination**. The acceptance criterion was a successful migration against the intended database.

### My Python workbench

Personal Agent Workbench develops this idea into my own application: two independent proposals run in parallel, a dedicated critic reviews both, and a synthesizer produces the final recommendation.

- Editable roles and model assignments.
- Structured responses validated at each stage.
- Inspectable inputs, outputs, timing and API attempts.
- A shared request budget and explicit failure handling.
- Human review before implementation.

The purpose is to make reasoning and handoffs inspectable. Agreement between agents still needs verification against the project.
