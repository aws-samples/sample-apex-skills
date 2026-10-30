---
sidebar_position: 1
title: Blog standard
description: "How we write and lay out posts on the APEX Skills blog: titles, descriptions, structure, images, links, visual design and a pre-publish checklist."
---

# Blog standard

Every post under `misc/website/blog/` follows this standard, so posts read well, look like the rest of the site and show up well in search results and link previews. Each rule cites a source (listed at the end, all read on 2026-10-30). A rule marked **our choice** has no outside source: it is a house rule we picked.

The first post (2026-10-23) predates this standard and does not yet meet rules 3, 5, 8 and 12.

Runbook standards will sit beside this page later.

## File and front matter

- **File:** `misc/website/blog/YYYY-MM-DD-<slug>.md`, or a folder `YYYY-MM-DD-<slug>/index.md` to keep its images beside it [S8]. The date comes from the file name or a `date` key [S9].
- **Keys:** `slug`, `title`, `description`, `authors`, `tags` and `image` are required (our choice). `keywords` is allowed and becomes `<meta name="keywords">` [S9].
- **New author or tag:** add its key to `blog/authors.yml` or `blog/tags.yml` in the same pull request [S8].
- **Voice:** "conversational, friendly, and respectful without using slang or being overly colloquial or frivolous" [S18].
- **Public content:** this repo is public. No internal names, hostnames or paths, and no ticket or decision ids from outside it. Our choice.
- **Review:** a post lands by pull request and is reviewed like any other change.

## Writing

1. **Title: 60 characters or fewer, sentence case, says what the reader gets.** Google sets no length limit but truncates title links "to fit the device width" and asks for "descriptive and concise" titles [S1]; its article guidance says "long titles may be truncated on some devices" [S3]. Use sentence case for all titles and headings [S6]. The 60-character limit is our choice; for scale, counted on 2026-10-30, the GitHub engineering blog index listed 19 titles with a median of 58 characters and the Cloudflare blog index 19 with a median of 64 [S12, S13]. Keep punctuation simple: "Punctuation can be a sign that your heading is too complicated" [S6]. A subtitle goes in `description`, not after a colon in the title.
2. **Description: one or two sentences, unique to the post.** It becomes `<meta name="description">` and `og:description` [S9]. Google asks for a description that is unique per page and "truly descriptive", with no keyword strings; it sets no length limit but truncates to the device width [S2]. Our choice: aim for 160 characters or fewer, so the key point survives truncation.
3. **Intro: lead with the conclusion.** Users scan: "79 percent of our test users always scanned" (NN/g, 1997 study); write in the inverted pyramid, starting with the conclusion [S7]. The first paragraph says what was decided or learned and who it is for.
4. **Truncate marker after the intro.** Use `<!-- truncate -->` in `.md` and `{/* truncate */}` in `.mdx` [S8]; our config warns on a post without one (`onUntruncatedBlogPosts`) [S9].
5. **Structure for scanning.** Use meaningful sub-headings (not clever ones), bulleted lists and one idea per paragraph [S7]. As a guide, not a rule, aim for about half the words of conventional writing (NN/g, 1997 study) [S7]. Headings are descriptive, sentence case, one H1 per page (the title) and no skipped levels [S6]. Use `##` and `###` only: our choice, to keep the outline shallow for readers who scan [S7].
6. **Length: 800 to 2000 words; split anything longer into a series.** Our choice.
7. **Code: short, runnable, with a language tag on every fence.** Our choice. Show the smallest excerpt that makes the point and link to the full file in the repo.
8. **Images: meaningful alt text and descriptive file names.** Alt text conveys the image's meaning, "which typically isn't a literal description" [S11]; Google wants alt text that is "information-rich" and in context, without keyword stuffing, and file names that are "short, but descriptive" [S4]. Put a diagram's detail in the body text too [S11]. Set `image` front matter for the social card (`og:image`) [S9]. Google's Article rich-result guidance asks for 16x9, 4x3 or 1x1 and at least 50K pixels (width x height) [S3]; we use 16x9 for the social card too (our choice).
9. **Links: text that makes sense on its own.** Never "click here" or "this article"; use the destination's title or a short description [S5].
10. **Authors and tags from the registries only.** Authors are keys in `blog/authors.yml` and tags are keys in `blog/tags.yml` [S8]; our config throws on inline authors or tags (`onInlineTags` [S9], `onInlineAuthors` [S17]).
11. **No em dashes (U+2014).** Use a colon, a comma or a new sentence. Our choice, for blog posts.
12. **End with one next step**: a link to the repo docs, the decision record, or how to give feedback. Our choice.

## Visual design

The theme renders the post title at `font-size: 3rem` (2rem under 576px) through a hashed CSS module class [S10, BlogPostItem/Header/Title]. The site overrides it in `misc/website/src/css/custom.css` through the stable `plugin-blog` class that the built HTML puts on every blog page (post, list and tag pages), since the hashed class name can change between theme versions:

| Element | Desktop | 576px and below |
|---|---|---|
| Post page title (`.plugin-blog article > header > h1`) | 2.25rem, line height 1.2 | 1.75rem |
| List and tag page titles (`.plugin-blog article > header > h2`) | 1.75rem, line height 1.25 | 1.5rem |
| Post body (`.plugin-blog article .markdown`) | max width 70ch | same |

The sizes are our choice. The measure is about 70 characters (`70ch`), inside the 45 to 90 [S14] and 50 to 75 [S15] ranges; `ch` is the width of "0", so it does not guarantee WCAG 1.4.8's "no more than 80 characters or glyphs" [S16]. Body line height stays at 1.5 or more, per WCAG 1.4.8 "at least space-and-a-half" [S16]; the site sets 1.75.

The blog keeps its "Recent posts" sidebar and shows reading time (`showReadingTime`) [S9]. The blog is linked from the top navbar and from the docs sidebar, between Examples and Workshop.

Check a new post on desktop and at 375px width, in both light and dark themes, before merge.

## Pre-publish checklist

- [ ] Title is 60 characters or fewer, sentence case, no em dash (`python3 -c 'print(len("<title>"))'`).
- [ ] `description` is set, unique, about 160 characters or fewer.
- [ ] `authors` and `tags` are keys in `authors.yml` and `tags.yml`.
- [ ] `<!-- truncate -->` sits after the intro; the intro states the conclusion.
- [ ] Headings are `##` and `###` only, sentence case, descriptive.
- [ ] Every code fence has a language; every image has alt text and a descriptive file name; `image` is set for the social card.
- [ ] No "click here" links; every repo link resolves.
- [ ] `grep -c "$(printf '\342\200\224')" <post>` prints 0 (U+2014 as octal bytes: works in any locale, holds no em dash).
- [ ] `npm run build` in `misc/website` passes with no blog warnings; the page is checked on desktop and at 375px width, in light and dark themes.

## Sources

All read on 2026-10-30.

- S1 Google, Title links: https://developers.google.com/search/docs/appearance/title-link
- S2 Google, Snippets and meta descriptions: https://developers.google.com/search/docs/appearance/snippet
- S3 Google, Article structured data: https://developers.google.com/search/docs/appearance/structured-data/article
- S4 Google, Image SEO: https://developers.google.com/search/docs/appearance/google-images
- S5 Google developer style guide, Link text: https://developers.google.com/style/link-text
- S6 Google developer style guide, Headings: https://developers.google.com/style/headings
- S7 Nielsen Norman Group, How users read on the web: https://www.nngroup.com/articles/how-users-read-on-the-web/
- S8 Docusaurus, Blog: https://docusaurus.io/docs/blog
- S9 Docusaurus, plugin-content-blog API: https://docusaurus.io/docs/api/plugins/@docusaurus/plugin-content-blog
- S10 Docusaurus v3.10.1 theme source: https://github.com/facebook/docusaurus/tree/v3.10.1/packages/docusaurus-theme-classic/src/theme (BlogPostItem/Header/Title, BlogLayout, BlogPostPage) and docusaurus-theme-common/src/utils/ThemeClassNames.ts
- S11 W3C WAI, Informative images: https://www.w3.org/WAI/tutorials/images/informative/
- S12 GitHub engineering blog index: https://github.blog/engineering/
- S13 Cloudflare blog index: https://blog.cloudflare.com/
- S14 Butterick, Practical Typography, Line length: https://practicaltypography.com/line-length.html
- S15 Baymard Institute, Line length readability: https://baymard.com/blog/line-length-readability
- S16 W3C, Understanding WCAG 2.1 SC 1.4.8 Visual presentation: https://www.w3.org/WAI/WCAG21/Understanding/visual-presentation.html
- S17 Docusaurus v3.10.1 source, `options.ts:76`: https://github.com/facebook/docusaurus/blob/v3.10.1/packages/docusaurus-plugin-content-blog/src/options.ts
- S18 Google developer style guide, Voice and tone: https://developers.google.com/style/tone
