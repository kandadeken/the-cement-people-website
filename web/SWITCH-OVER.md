# Switching thecementpeople.com to the Astro site, and switching back

The exact steps for the switch-over phase. **Nothing here is done until that
phase is approved.** Until then the live site is the root `index.html` on
`main`, served by GitHub Pages with "Deploy from a branch".

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
