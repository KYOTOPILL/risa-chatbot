# Prosecution: the deployment should not go ahead as described

1. **Unauthenticated admin page on a shared server.**
Evidence: "The admin page currently has no authentication." It can upload and delete documents and re-index. On a deployed server, anyone who can reach it can delete the leave policy or upload a false travel-allowance document. The bot would then give employees wrong HR answers with full confidence. The case file also says "sensitivity of the data was raised as a concern," so the exposure is of HR material. Cost: poisoned or erased policy answers, a possible data leak, and an HR liability with no audit trail.

2. **Capacity is unknown, yet CPU-only is chosen.**
Evidence: "Server specs (cores, RAM) and number of concurrent users are not yet decided." An 8B model on CPU generates slowly, and Ollama serves requests largely one at a time per loaded model. Top-k 4 with chunk size 800 builds a long prompt, and Thai text tokenizes into many tokens. Latency per answer could be tens of seconds, and queues grow with each added user. The record contains no latency measurement. Cost: an unusable chatbot at launch, or a hardware purchase made after the fact.

3. **"Live evals passed 10/10" does not support deployment.**
Evidence: "Live evals passed 10/10 on the current setup." Ten questions is too small a sample to estimate real accuracy. The record does not say whether the evals ran on the CPU server, whether they were in Thai, or whether they covered refusals and out-of-scope questions. The settings (max cosine distance 0.6, top-k 4) were tuned on that same small set. Cost: false confidence, with wrong HR answers found only by employees.

4. **Unfinished configuration goes live.**
Evidence: "HR contact in config is still a placeholder." The bot's fallback when it cannot find an answer presumably sends employees to that contact. A placeholder there sends employees to a dead end exactly when the bot is least useful. This is also a sign that the deployment checklist has not been worked through. Cost: failed escalations and lost trust in the tool on day one.

5. **No stated owner, access control or data handling for sensitive HR data.**
Evidence: the record says only that sensitivity "was raised as a concern." It names no network boundary, no user authentication on the chat page, no logging policy, and no backup of the "local index directory." Chat logs may hold employees' personal circumstances (leave, scholarship). Cost: privacy exposure with no mitigation plan, and a re-index from scratch after a disk failure.
