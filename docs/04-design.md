# GeoGuard-EO — Design System

> Source: the cinematic reference brief (dark warm base, cream type, film background, glass pill CTA, blur-fade-up motion), adapted for a data-heavy geospatial web app.
> Read before building any UI. Implement tokens first (`frontend/src/styles/tokens.css` + Tailwind theme), then components, then screens.
> All fonts, icons, and assets must be free/open-source (see techspec §0).

---

## 1. Design Principles

1. **One continuous piece.** Warm, calm, cinematic. The login screen carries the emotion; the working screens stay quiet and legible.
2. **Type does the work.** Big confident type, hairlines, generous space. No decoration for its own sake.
3. **No colored accent in the chrome.** Every UI element is cream or dark. Color appears only where data needs it (see §3.3) and is always paired with a text label.
4. **Legibility beats atmosphere.** Text over the film or the map always sits on a scrim or an opaque-enough panel.
5. **Honest and calm voice.** One clear promise, one clear action. Detection results are screening aids, never accusations.

## 2. Adaptations From the Reference (and why)

| Reference says | GeoGuard-EO does | Reason |
|----------------|------------------|--------|
| One self-contained HTML file, no framework | React + Vite + Tailwind; tokens as CSS variables consumed by Tailwind | Our stack (techspec §2) |
| Google Fonts via `<link>` | Self-host the same fonts with `@fontsource` packages (free) | No third-party request at runtime; works offline |
| Specific PRISMA film from a hosted URL | A configurable video slot (`VITE_HERO_VIDEO_URL`) with a poster and gradient fallback; the app never depends on it loading | The PRISMA film is another brand's asset; free-only and offline-safe |
| No coloured accent at all | True for the chrome. **Data-semantic colors** exist only for confidence, status, and map polygons, always with a text label and icon | A review tool must distinguish states at a glance and stay accessible |
| Full-viewport cinematic hero + scroll sections | Cinematic hero on **Login** only. All app screens use the flat dark base with the same tokens | Performance and legibility for tables and maps |
| Scroll sections (cards, pull-quote, CTA) | Defined in §13 as an **optional** public landing page, not in v1 scope unless added to the plan | PRD has no marketing page |

## 3. Tokens

### 3.1 Base and text

```css
:root {
  --base:        #0d0b09;                    /* page background */
  --text:        #f3efe6;                    /* warm cream */
  --text-soft:   rgba(243, 239, 230, .70);
  --text-dim:    rgba(243, 239, 230, .46);   /* decorative / tertiary only */
  --hairline:    rgba(243, 239, 230, .16);
  --hairline-strong: rgba(243, 239, 230, .28);

  --surface-1:   rgba(243, 239, 230, .04);   /* cards */
  --surface-2:   rgba(243, 239, 230, .07);   /* hover, inputs */
  --surface-3:   rgba(243, 239, 230, .11);   /* pressed, selected */
  --panel:       rgba(13, 11, 9, .78);       /* floating panels over map/film */
  --glass:       rgba(243, 239, 230, .10);   /* glass pill fill */

  --radius-card: 20px;
  --radius-ctl:  12px;
  --radius-pill: 999px;

  --ease-out: cubic-bezier(.2, .7, .2, 1);
}
```

**Contrast note:** `--text-dim` is about 4.2:1 on the base, below the 4.5:1 AA bar for small text. Use it only for decorative or non-essential text (or text ≥ 18px). Essential small text uses `--text-soft`.

### 3.2 Spacing, sizes, breakpoints

- Spacing scale (px): 4, 8, 12, 16, 24, 32, 48, 64, 96, 128.
- Max content width: 1200px for content pages; maps and tables may go full-bleed.
- Breakpoints: `sm 640`, `md 900` (the reference's collapse point), `lg 1280`, `xl 1536`.
- Below 900px: hide the top nav link row (use a menu button), collapse grids to one column, stack the hero column.

### 3.3 Data-semantic colors (the only colors allowed)

Muted so they sit inside the golden, warm palette. Never used alone: always with a label and an icon or shape.

| Token | Hex | Use |
|-------|-----|-----|
| `--sem-high` | `#e8735a` | Confidence `high`, polygon stroke |
| `--sem-medium` | `#e6b455` | Confidence `medium` |
| `--sem-low` | `#9aa79b` | Confidence `low` |
| `--sem-ok` | `#8fbf9f` | Succeeded, confirmed |
| `--sem-danger` | `#e8735a` | Failed, destructive actions (same hue family as high; distinguished by icon/label) |
| `--sem-info` | `#f3efe6` | Neutral info uses cream, not a color |

Each must be checked at ≥ 4.5:1 against `--base` and against `--panel` before use as text; as fills they are used at 12–20% opacity with a solid stroke.

### 3.4 Tailwind mapping (`tailwind.config`)

```ts
theme: {
  extend: {
    colors: {
      base: 'var(--base)', cream: 'var(--text)',
      soft: 'var(--text-soft)', dim: 'var(--text-dim)',
      hair: 'var(--hairline)', 'hair-strong': 'var(--hairline-strong)',
      s1: 'var(--surface-1)', s2: 'var(--surface-2)', s3: 'var(--surface-3)',
      panel: 'var(--panel)', glass: 'var(--glass)',
      high: 'var(--sem-high)', medium: 'var(--sem-medium)', low: 'var(--sem-low)', ok: 'var(--sem-ok)',
    },
    fontFamily: {
      display: ['"Inter Tight"', 'Inter', 'system-ui', 'sans-serif'],
      sans: ['Inter', 'system-ui', 'sans-serif'],
      mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
    },
    borderRadius: { card: '20px', ctl: '12px' },
  },
}
```

## 4. Typography

**Modern sans only. No serif. No italic anywhere** (including emphasis: use weight or `--text` vs `--text-soft`, not italics).

| Role | Font | Weight | Notes |
|------|------|--------|-------|
| Wordmark / display | Inter Tight | 500 | Tight tracking `-.045em`, line-height `.86` |
| Headings | Inter Tight | 500–600 | Tracking `-.03em` to `-.02em` |
| Body / UI | Inter | 400 / 500 | `font-feature-settings: 'cv11', 'ss01'` optional; `tabular-nums` for numbers |
| Labels / IDs / coordinates | JetBrains Mono | 400 / 500 | Uppercase eyebrows with `.12em` tracking |

Scale (px, desktop → mobile):

| Token | Size | Line height | Use |
|-------|------|-------------|-----|
| `display-xl` | clamp(64, 11vw, 176) | .86 | Login wordmark |
| `h1` | clamp(36, 4.5vw, 64) | 1.02 | Page titles on hero-like pages |
| `h2` | clamp(28, 3vw, 44) | 1.1 | Section headings |
| `h3` | 22 | 1.25 | Card titles |
| `body-lg` | 18 | 1.55 | Lead lines |
| `body` | 15–16 | 1.55 | Default |
| `small` | 13 | 1.45 | Table cells, helper text |
| `eyebrow` | 11–12 mono | 1.3 | Step numbers, section labels |

Line length for prose ≤ 68 characters.

## 5. Legibility Layers (film and map)

Two fixed layers over the film (login) and, in a lighter form, over the map:

```css
.bg-video { position: fixed; inset: 0; width: 100%; height: 100%; object-fit: cover; z-index: 0; }
.scrim {
  position: fixed; inset: 0; z-index: 1; pointer-events: none;
  background:
    radial-gradient(120% 90% at 50% 50%, transparent 55%, rgba(13,11,9,.55) 100%),
    linear-gradient(to bottom,
      rgba(13,11,9,.72) 0%, rgba(13,11,9,.18) 22%,
      rgba(13,11,9,.08) 55%, rgba(13,11,9,.62) 100%);
}
.vignette {
  position: fixed; inset: 0; z-index: 2; pointer-events: none;
  box-shadow: inset 0 0 220px 70px var(--base);
}
```

Never a flat dark box: the middle of the film stays nearly clear. Tune opacity so cream text passes 4.5:1 at its actual position over the film (check in a screenshot).

**Floating panels over the map** (filters, legends, controls) use `--panel` + `backdrop-filter: blur(16px)` + 1px `--hairline` border, radius `--radius-card`. Fall back to a solid `--base` at 92% opacity where `backdrop-filter` is unsupported.

## 6. Components

**Top bar (app).** Left: small wordmark `GeoGuard` with superscript `EO` (no logo mark). Center or left: nav links (Dashboard, Parcels, Scans, Detections, Settings) as text with a 1px underline for the active item. Right: user menu (name, role badge). Height 64px, bottom hairline. Below 900px links move into a menu sheet.

**Buttons.**
- *Primary (glass pill):* `--glass` fill, 1px `--hairline-strong` border, `backdrop-filter: blur(14px)`, radius pill, padding 12px 12px 12px 22px, label Inter 500 15px, plus a **circular icon button** on the right (40px, 1px hairline, arrow icon). Hover: lifts 2px (`translateY(-2px)`), icon circle rotates 45°. Focus: 2px cream outline, 3px offset.
- *Secondary:* transparent, 1px hairline, radius pill, no icon circle. Hover: `--surface-2`.
- *Ghost/text:* cream text, underline on hover.
- *Destructive:* secondary style with `--sem-danger` text and a trash icon; always confirmed in a modal.
- Disabled: 40% opacity, no hover transform, `aria-disabled`.

**Inputs.** 44px height, radius `--radius-ctl`, `--surface-1` fill, 1px hairline, cream text, placeholder `--text-dim`. Focus: border `--hairline-strong` + 2px cream outline. Labels above in `small` Inter 500. Errors: message below with an icon and text (not color alone).

**Cards.** Radius 20px, 1px hairline, `--surface-1` fill, padding 24–32px. Optional mono step number top-left, `h3` title, two lines of `--text-soft` copy. Hover (interactive cards only): border to `--hairline-strong`, `translateY(-2px)`.

**Badges/chips.** Pill, 1px border, 12px mono or Inter 500 uppercase. Confidence badge: colored dot/shape + text (`HIGH`, `MEDIUM`, `LOW`); never color only. Status chips (`new`, `confirmed`, `dismissed`, `field visit`) are neutral cream outlines with distinct icons; only `confirmed` may use `--sem-ok`.

**Tables.** No zebra fills. Row height 48px, bottom hairlines, sticky header with mono uppercase labels, numbers right-aligned with `tabular-nums`, row hover `--surface-2`, selected row `--surface-3` with a left 2px cream bar. Mobile: rows collapse into cards.

**Tabs/segmented control.** Text tabs with a 1px underline for active; for Upload/Draw use a pill segmented control (`--surface-1`, active `--surface-3`).

**Modals and sheets.** `--panel` at 92% + blur, radius 20px, hairline border, 24–32px padding, focus trapped, `Esc` closes, first field focused, backdrop `rgba(13,11,9,.6)`.

**Toasts.** Bottom-center, `--panel`, hairline, icon + message, auto-dismiss 5 s (errors persist until dismissed), `role="status"` (errors `role="alert"`).

**Progress.** 2px cream line on a hairline track for scan progress, with a mono step label (`OPTICAL_CHANGE 62%`). Indeterminate uses a slow sliding segment (disabled under reduced motion; show text only).

**Empty / loading / error states.** Empty: mono eyebrow, `h3`, one line, one primary action. Loading: skeletons in `--surface-1` with a slow shimmer (off under reduced motion). Error: what happened, why if known, one retry action.

**Before/after slider.** Two images stacked, draggable handle: 1px cream vertical line with a 40px circular grip (hairline, `--panel`). Labels `BEFORE` and `AFTER` in mono at the corners on small `--panel` chips with dates. Keyboard: `←/→` moves 5%, `Shift+←/→` 20%; `role="slider"` with `aria-valuenow`, `aria-label`.

## 7. Map Styling

- **Library:** MapLibre GL JS with `terra-draw` for drawing.
- **Basemap:** free OSM raster tiles from `BASEMAP_URL`, darkened to sit in the theme using raster paint properties (for example lower `raster-brightness-max`, lower `raster-saturation`, warm `raster-hue-rotate`). Do not hard-code a tile provider; keep attribution visible. A satellite basemap toggle is allowed only if the chosen source's terms permit it.
- **Parcels:** 1.5px cream stroke, fill cream at 6%, dashed stroke when selected in a form; label at higher zooms in mono.
- **Detections:** stroke and 16% fill in the confidence color (`--sem-high|medium|low`), 2px stroke; selected detection gets a 3px cream halo. Also encode confidence with a marker shape at the centroid (filled circle, ring, small dot) so it works without color.
- **Legend:** floating `--panel` bottom-left, lists confidence classes with color + shape + label.
- **Controls:** zoom, compass, basemap toggle in a vertical `--panel` stack, 40px targets.
- **Draw mode:** cursor crosshair, vertices as 10px cream dots, live area chip near the cursor, `Enter` to finish, `Esc` to cancel, `Backspace` removes the last vertex.

## 8. Screens

**Login (cinematic hero).**
- Full-viewport, single non-scrolling screen at 1280×800.
- Film behind everything (`.bg-video`, `.scrim`, `.vignette`).
- Bottom-left: enormous wordmark `GeoGuard` with small superscript `EO`, Inter Tight 500.
- Bottom-right column (stacks on mobile): short line: “Watch protected land from above. Verify on the ground.” Then the sign-in form (email, password) in a `--panel` glass card, and the primary glass-pill button “Sign in”.
- Top: nothing but a small centered row of quiet links if needed (for example “Docs”); no logo in the nav because the wordmark is the logo.
- Errors appear inline in the card; failed-login cooldown shows a calm message.
- Forced password change uses the same layout with a different card.

**App shell.** Flat `--base`, top bar (§6), content max width 1200px, 32px page padding (16px on mobile). Page header: mono eyebrow + `h1` or `h2` + one lead line + primary action on the right.

**Dashboard.** Row of 3 stat cards (New detections, Last scan, Active schedules), the “new since your last visit” list, the onboarding checklist card (mono step numbers `01`–`04`), and a small overview map.

**Parcels.** Split: table left, map right (stacked on mobile). “Add parcels” opens a page with the Upload/Draw segmented control and the map.

**Scan create/detail.** Form in cards; detail page with a progress line, step label, scenes used, and a results summary by confidence.

**Detections list.** Split list/map. Filter bar above the list (chips + selects). Hovering a row highlights the polygon and vice versa.

**Detection detail.** Two columns: left map + before/after slider; right metrics card (area, confidence, score, sensor agreement, parcel, dates), status actions (Confirm, Dismiss, Needs field visit), history list. Disclaimer line in `--text-soft`: “Satellite detection is a screening aid. Verify on the ground before acting.”

**Schedules, Users, Settings.** Table + slide-over form. Destructive actions in a confirm modal.

## 9. Motion

**Entrance (blurFadeUp), page-level elements only:**

```css
@keyframes blurFadeUp {
  from { opacity: 0; filter: blur(18px); transform: translateY(30px); }
  to   { opacity: 1; filter: blur(0);    transform: translateY(0); }
}
.rise { animation: blurFadeUp 1s var(--ease-out) forwards; opacity: 0; }
```

Stagger with `animation-delay`. Login: nav items 0–290 ms, wordmark 400 ms, sub-line 560 ms, form/CTA 700 ms. App pages: header 0 ms, first content block 120 ms, second 240 ms; nothing later.

**Scroll reveals (optional landing / long pages):** blocks start `opacity: 0; translateY(26px)` and transition over `.85s` when an `IntersectionObserver` (`threshold: .14`, `rootMargin: '0px 0px -8% 0px'`) fires; unobserve after revealing. Implement as a `Reveal` component/hook.

**Hover/press:** buttons and interactive cards lift 2px, 200 ms `--ease-out`; icon circle rotates 45°.

**Reduced motion (`prefers-reduced-motion: reduce`):** disable entrance and reveal animations (show everything at rest), remove hover transforms, stop shimmer and sliding progress, **do not autoplay the film** (show the poster frame), and keep functional state changes instant.

**Video fallback:** muted, `autoplay loop playsinline`; a small script calls `video.play()` on `canplay` and on window `load`, catching and ignoring rejections. If the video fails or `VITE_HERO_VIDEO_URL` is empty, the poster image or a warm gradient (`--base` to a faint golden radial) fills the background and the page looks intentional.

## 10. Accessibility

- All text ≥ 4.5:1 against its actual background (test over the film and over the map panels), except `--text-dim` used only for decoration.
- Full keyboard operation; visible focus ring (2px cream, 3px offset) on every interactive element.
- Color is never the only signal (confidence and status use text and shape).
- Semantic landmarks (`header`, `nav`, `main`), one `h1` per page, associated labels and error text (`aria-describedby`).
- Maps: provide the same information in the adjacent table/list; the map is an enhancement, not the only path. Drawing has a keyboard-accessible fallback (upload GeoJSON) and a coordinate entry option in v1.1.
- Modals trap focus and restore it on close; live regions for toasts and scan progress.
- Images have alt text; before/after images have descriptive labels with dates.
- Touch targets ≥ 44px on mobile.

## 11. Performance Rules

- `filter: blur` and `backdrop-filter` are expensive: use entrance blur only on a few page-level elements, never on table rows or list items; keep backdrop blur to a handful of panels.
- Fixed video layer only on Login; the app pages have no video.
- Compress the hero video (short loop, H.264/WebM, ≤ 5 MB target) and provide a poster; lazy-load nothing above the fold.
- Fonts: self-host WOFF2 subsets (Latin), `font-display: swap`, preload the two most used weights.
- Map: simplified geometries in lists; do not re-render polygons on every hover.

## 12. Voice and Copy

Calm, confident, specific. One promise, one action. No brochure copy.

| Place | Copy |
|-------|------|
| Login line | Watch protected land from above. Verify on the ground. |
| Primary CTAs | Sign in · Add parcels · Run scan · Confirm · Generate report |
| Empty parcels | No parcels yet. Add the land you want to watch. |
| Empty detections | Nothing new. Your parcels look unchanged since the baseline. |
| Scan running | Reading satellite scenes. This can take several minutes. |
| Failure (no clear scenes) | No clear optical scenes in that period. Try a wider window or a different season. |
| Disclaimer | Satellite detection is a screening aid. Verify on the ground before acting. |
| Dismiss reasons | Bare soil · Cloud shadow · Seasonal change · Other |

Avoid alarmist wording (“violation found”, “illegal”). Use “possible new construction”.

## 13. Optional Public Landing Page (not in v1 unless added to the plan)

Same palette and motion as the reference, below the login-style hero:

1. **Three-card section** with eyebrow `HOW IT WORKS`, heading “Land changes. You'll know.”, lead line, and cards:
   - `01` **The parcels** — Draw or upload the land you want to watch. One outline is enough to start.
   - `02` **The scans** — Radar and optical satellites, compared automatically, on a schedule you choose.
   - `03` **The evidence** — Before and after imagery, area, and confidence, ready for a report.
2. **Pull-quote band** (hairline top and bottom, centered, `h2` size): only real user words if they exist; otherwise omit the band rather than invent a testimonial.
3. **Closing CTA** “Watch the land.” with the glass-pill button, then a footer row: wordmark, copyright line, three quiet links.

## 14. Implementation Notes

- Files: `frontend/src/styles/tokens.css`, `frontend/src/styles/fonts.css` (via `@fontsource/inter`, `@fontsource/inter-tight`, `@fontsource/jetbrains-mono`), `tailwind.config.ts`, `src/components/ui/*` (Button, GlassPill, Input, Card, Badge, Table, Tabs, Modal, Toast, Progress, BeforeAfter, Reveal), `src/features/map/*`.
- Build the UI kit as small, reusable components first (implementation plan task 6.2) so this design can be applied or adjusted in one place; final polish happens in task 8.2.
- Report PDFs (task 7.1) are print documents: white background, dark text, same fonts if embedded (register TTFs), no film, no dark theme.
- Dark theme only in v1. A light theme is out of scope.
- Visual QA checklist for each screen: 1280×800 and 390×844; keyboard-only pass; reduced-motion pass; contrast check over film/map; loading, empty, and error states present.

## 15. Do and Don't

**Do:** keep chrome cream on dark; use hairlines instead of shadows; pair every color with text; keep the login hero to one screen; use mono for IDs, coordinates, and step numbers; keep motion slow and quiet.

**Don't:** add a colored accent to buttons or links; use serif or italic type; put text directly on the film or map without a scrim/panel; animate table rows; use pure black or pure white; depend on the video loading; copy the PRISMA film, name, or copy.
