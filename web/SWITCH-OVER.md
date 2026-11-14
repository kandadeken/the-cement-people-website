# Switching thecementpeople.com to the Astro site, and switching back

> **Done on Saturday 14 November 2026, about 8 pm**, approved by Daniel. The
> pre-checks passed (tag `v2-pre-astro` and `main` both on `37aa70f`, latest
> build green), the three steps below were carried out, and the checks after
> passed: custom domain and "Enforce HTTPS" kept, DNS check successful, the
> live files byte-for-byte the tested build, estimate, WhatsApp, PDF, search,
> menu and phone layout all working, robots.txt, sitemap and favicons served,
> no noindex. The rollback below stays valid as long as the root
> `index.html` is kept (at least two weeks, then reviewed, not deleted
> automatically).

The exact steps, kept as the record of how it was done and for the rollback.

Everything happens in the repository's **Settings** on GitHub; no code
changes, no DNS changes. Allow about 15 minutes, at a quiet time for the
business (not during opening hours: Monday to Saturday, 7 am to 5 pm).

## Before you start

- [ ] The latest "Astro publishing" run on `main` is green (Actions tab).
      Its "Publish" job shows as skipped; that is expected.
- [ ] The preview at https://kandadeken.github.io/ has been checked on a
      phone and a computer and matches what you expect.
- [ ] Tag the current state so it can always be found again:
      `v2-pre-astro` on the latest `main` commit (Claude does this).
- [ ] **Verify the tag, don't assume it** (required; stop if either check
      fails). On GitHub, Code -> Tags must list `v2-pre-astro`, and it must
      point at the exact commit `main` is on at that moment (the same short
      code as the newest commit on `main`). From a computer:
      `git ls-remote origin refs/heads/main refs/tags/v2-pre-astro` must
      print the same commit for both. If `main` has moved since tagging,
      re-tag before going on.
- [ ] Note down, from Settings -> Pages: the custom domain
      (`thecementpeople.com`) and that "Enforce HTTPS" is ticked.

## Switch over (3 steps)

1. **Settings -> Pages -> Build and deployment -> Source:** change
   "Deploy from a branch" to **"GitHub Actions"**. The live site does not
   change yet: nothing has been published by Actions.
2. **Settings -> Secrets and variables -> Actions -> Variables tab -> New
   repository variable:** name `ASTRO_LIVE`, value `true`.
3. **Actions -> Astro publishing -> Run workflow** on `main`. It builds,
   checks and tests the site again, then the "Publish" job puts it live.
   Takes about 5 minutes.

## Check it worked (straight after)

- [ ] Settings -> Pages still shows the custom domain `thecementpeople.com`
      and "Enforce HTTPS" ticked. If the domain field is empty, type
      `thecementpeople.com` and Save.
- [ ] https://thecementpeople.com opens the Astro site: the Contact section
      shows the full address, opening hours and email (the old site only
      shows "Kasoa, Ghana").
- [ ] On a phone: add items, open the estimate, send it to WhatsApp, save
      the PDF, search, use the menu.
- [ ] Claude runs the live checks against the real address
      (`TCP_SITE_URL=https://thecementpeople.com python -m pytest tests`),
      including robots.txt, the sitemap and the favicon.
- [ ] Search Console: the property is still verified (Settings ->
      Ownership verification). Nothing in the code verifies it, so the
      switch should not affect it.

## Roll back (if anything is wrong)

1. **Settings -> Pages -> Source:** change back to **"Deploy from a branch"**,
   branch `main`, folder `/ (root)`, Save.
2. Wait 2 to 5 minutes. GitHub serves the root `index.html` again: the old
   site, unchanged, on the same address.
3. Set the variable `ASTRO_LIVE` to `false` (or delete it), so later merges
   don't publish the Astro site by mistake.
4. Check the custom domain and "Enforce HTTPS" in Settings -> Pages, as
   above.

The old `index.html` stays in the repository until the Astro site has run
without problems for an agreed period. Removing it is its own pull request.

## Why this is safe

- The domain's DNS records point at GitHub Pages, not at a particular way of
  building the site, so they never change.
- The publishing workflow refuses to package a build that is marked
  noindex, blocks search engines, has the wrong domain or canonical address,
  links to a missing file or lacks any product (`scripts/check-build.mjs`),
  and runs the full test suite on the exact files it publishes.
- Two builds from the same commit are checked to be identical, so the files
  that were tested are the files that go live.
