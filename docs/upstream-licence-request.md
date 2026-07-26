# Draft: licence request to the upstream project

Post this yourself, from your own GitHub account, as a new issue on
<https://github.com/karpathy/llm-council/issues>.

Check the existing issues first — if someone has already asked, add a short
`+1` with one line on what you built instead of opening a duplicate. A
thread with several people asking is more persuasive than three separate
threads.

---

**Title:**

```
Consider adding a LICENSE file
```

**Body:**

```
Thank you for putting this out. The anonymised peer review with self-vote
exclusion is a genuinely good idea and it has been more useful than the
weekend it took you suggests.

The repository currently has no LICENSE file, which means default copyright
applies and derivative work can't be redistributed. A number of us have
built substantially on the idea and would like to publish our versions with
proper attribution back to you.

Would you consider adding MIT or Apache-2.0? It would take a minute and
would unblock everyone who wants to build on this openly.

Either way, thank you for the weekend you spent on it.
```

---

## Notes on doing this well

**Say nothing else.** No mention of GST, India, your firm, or what you have
built. The moment the request reads as "please help my product", it becomes
a favour he has to evaluate rather than a housekeeping item he can close in
thirty seconds. Keep it about the repository.

**Do not ask for endorsement, review or partnership.** He has publicly said
he will not support the project. Asking for anything beyond a licence file
invites a no.

**Expect silence.** Twenty-three thousand stars generate a great deal of
noise. Silence is not refusal, and it is not personal. Do not follow up more
than once, and not sooner than a month.

**If he adds a licence**, thank him in the thread, in one line, and update
the NOTICE file here to reflect it. That is also the moment — and only then
— to mention what you built, briefly, if the conversation invites it.

**If he never responds**, the fallback is straightforward: the surviving
upstream code is roughly three hundred lines of ordinary plumbing
(HTTP calls, JSON writes, route scaffolding). Rewriting it removes the
dependency entirely and leaves the project wholly owned. Nothing about the
compliance layer is affected either way.
