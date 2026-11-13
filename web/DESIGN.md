---
name: Wanderwise (web)
description: Day plans you can actually walk, drawn as a route on a folded city map.
colors:
  cover: "#17463a"
  cover-ink: "#ffffff"
  cover-ink-2: "#c9ddd4"
  bg: "#eef3f0"
  surface: "#ffffff"
  surface-sunken: "#f4f7f5"
  line: "#dde5e0"
  line-strong: "#bccac2"
  ink: "#14211b"
  ink-2: "#43534b"
  ink-3: "#56665e"
  accent: "#1f5fae"
  accent-strong: "#184c8c"
  accent-soft: "#e4edf8"
  ok-ink: "#1e6b45"
  warn-ink: "#8a4b0b"
  warn-bg: "#fdf6e9"
  danger-ink: "#b42318"
  danger-bg: "#fdf2f1"
  danger-line: "#f3c4be"
  path: "#9fb3a8"
  pin-food: "#c2410c"
  pin-history: "#8a5a2b"
  pin-art: "#9d3d6b"
  pin-architecture: "#4b5a6b"
  pin-nature: "#2e7d4f"
  pin-nightlife: "#4338ca"
  pin-shopping: "#a35a0b"
  pin-other: "#56665e"
typography:
  wordmark:
    fontFamily: "Overpass, system-ui, sans-serif"
    fontSize: "26px"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Overpass, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Overpass, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.3
  numeral:
    fontFamily: "Overpass, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    fontFeature: "tnum"
  time:
    fontFamily: "Overpass, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 700
    letterSpacing: "0.01em"
    fontFeature: "tnum"
  body:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 600
  caption:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 400
rounded:
  control: "8px"
  panel: "14px"
  round: "50%"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "24px"
  "6": "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.cover-ink}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.accent-strong}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "44px"
  input-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "44px"
  segment-selected:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
    height: "40px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    padding: "24px"
  stop-pin:
    textColor: "{colors.cover-ink}"
    rounded: "{rounded.round}"
    size: "36px"
  day-step-current:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.cover-ink}"
    rounded: "{rounded.round}"
    size: "40px"
---

# Design System: Wanderwise (web)

Tokens live as CSS custom properties at the top of `src/styles.css` (`--cover`, `--accent`, `--space-4`, ...). Use the variables in code; the values above mirror them. If you change a value, change it in `styles.css` and here.

## Overview

**Creative North Star: "The Folded City Map"**

The planner looks like a city map you'd unfold: a deep green cover band across the top, cool white map paper under it, water blue for anything you can press, and a legend of drawn symbols, one per interest. A day's plan is drawn as a walking route, with pins linked by a dashed footpath, not shown as rows in a table.

It is a task tool, so it stays calm. Surfaces are quiet, body text is plain system sans, and the emphasis goes to the plan's numbers (times, minutes, cost) and to one primary action per screen. The map look comes from a few repeated devices (cover band, legend symbols, dashed path, scale bars), not from extra decoration.

**Key Characteristics:**
- Green cover band behind the header; panels overlap its lower edge.
- Overpass (road-sign type) for headings and numbers, system sans for everything else.
- One drawn legend symbol and one pin colour per interest, reused in the form and on the route.
- Limits drawn as map scale bars with a tick at the traveler's limit.
- Status is always text plus colour, never colour alone.

## Colors

Cool map greens and greys, with one blue for action and a fixed legend palette for interests.

### Primary
- **Water Blue** (`accent`): buttons, selected segments, the current step and day, links, focus rings, text caret. The only colour that means "you can act here".
- **Deep Water** (`accent-strong`): primary button hover and stop times on the route.
- **Shallow Water** (`accent-soft`): selected segment fill, highlighted city option, input focus halo, text selection.

### Secondary
- **Map-Cover Green** (`cover`): the header band only. Text on it is white (`cover-ink`) or the pale green tagline (`cover-ink-2`).

### Tertiary: the legend
- **Interest pins** (`pin-food`, `pin-history`, `pin-art`, `pin-architecture`, `pin-nature`, `pin-nightlife`, `pin-shopping`, `pin-other`): each interest's colour, used for its route pin, its legend symbol outline in the form, and its Love/Some choice. Each is at least 3:1 on white. Assign one by setting the `--pin` variable via a `pin-<interest>` class (or `--row-pin` on an interest row).
- **Footpath Grey-Green** (`path`): the dashed line between pins and in the empty-state sketch.

### Neutral
- **Map Paper** (`bg`): page background below the band. Cool, never cream.
- **Sheet White** (`surface`) and **Fold Shadow** (`surface-sunken`): panels; sunken fill for notices, disabled buttons, hover on unselected segments, Skip.
- **Fine Rule** (`line`) and **Strong Rule** (`line-strong`): dividers and panel borders; input, segmented and secondary-button borders.
- **Ink** (`ink`), **Ink 2** (`ink-2`), **Ink 3** (`ink-3`): text, secondary text, tertiary text. All three pass 4.5:1 on `surface` and `bg`.

### Status
- **Park Green** (`ok-ink`): "Hours verified".
- **Amber Ink** (`warn-ink` on `warn-bg`): "Hours estimated", over-limit numbers, warning callouts.
- **Footpath Red** (`danger-ink`, `danger-bg`, `danger-line`): walks over the limit (the path segment and the scale overflow), errors, a stop marked for removal.

### Named Rules
**The One Blue Rule.** Water blue means action or selection. The single exception is Deep Water on stop times, which ties each time to the route. Don't use blue for decoration, headings or status.

**The Legend Rule.** An interest has one colour and one symbol everywhere. A new interest gets a new `--pin-*` token and a new symbol in `icons.tsx`, both added together.

## Typography

**Display Font:** Overpass 600/700/800 (bundled via `@fontsource/overpass`, imported in `main.tsx`), falling back to system sans
**Body Font:** system-ui stack

**Character:** Overpass has road-sign lineage, so it carries the map's signage: headings, the plan's numbers and stop times. Everything you read at length is system sans at 15px.

### Hierarchy
- **Wordmark** (800, 26px, line-height 1): header only, beside the folded-map mark.
- **Headline** (800, 30px, -0.02em): the plan title (the city).
- **Title** (700, 20px; 19px for the day title): panel titles, day title. Group and step titles use Overpass at 14–15px.
- **Numeral** (700, 20px, tabular): the fit-summary values (longest walk, cost, hours, match).
- **Time** (700, 14px, Deep Water, tabular): each stop's time range.
- **Body** (400, 15px, 1.5): default text. Long text capped at 60–65ch.
- **Label** (600, 14px): field labels, stop meta emphasis. Stop names are 16px/600.
- **Caption** (13px): hints, walk labels, fit captions, scale labels (11px).

### Named Rules
**The Signage Rule.** Overpass is for headings and numbers only. Body text, labels and buttons stay in system sans.

**The Tabular Numbers Rule.** Any number the user compares (times, minutes, money, step and day numbers, numeric inputs) uses `font-variant-numeric: tabular-nums`.

## Layout

- Page max width 1120px, centred, 16px side padding.
- Desktop: two columns, the planning form (340–400px) on the left and the results on the right, 24px gap. Below 820px it stacks into one column, and once a plan exists the form collapses to a one-line trip summary.
- The header band is full-bleed (`box-shadow` + `clip-path` trick) with 72px bottom padding and -48px margin, so the panels overlap it.
- Spacing comes from the 4/8/12/16/24/32 scale (`--space-1`…`--space-6`). Panel padding is 24px (16px under 480px); sections inside a panel are separated by 24px and a 1px `line` rule.
- Breakpoints actually used: 820px (stack), 480px (phone tightening), 380px and 360px (single-column review list and trip fields).
- Every touch target is at least 40px, and primary controls are 44px (`--control-height`).

## Elevation & Depth

Mostly flat paper. Panels are the only lifted layer, with a soft two-part shadow tinted green. Overlays get a slightly stronger shadow. Notices and callouts sit inside the paper as tinted fills with no border and no shadow.

### Shadow Vocabulary
- **Sheet** (`0 1px 2px rgba(16,40,30,.06), 0 10px 28px rgba(16,40,30,.08)`, `--shadow`): every panel.
- **Dropdown** (`0 8px 24px rgba(16,24,40,.12)`): the city suggestions list.
- **Sticky bar** (`0 -6px 16px rgba(16,24,40,.06)`): the re-plan bar pinned to the bottom of the plan.
- **Pin halo** (`0 0 0 3px` surface): a white ring that lifts route pins off the dashed path.

### Named Rules
**The Paper Rule.** Only panels and floating layers cast shadows. Content inside a panel is separated by rules and tints, not more shadows.

## Shapes

- Panels: 14px corners. Controls, notices, callouts, dropdowns: 8px.
- Round: route pins (36px), legend symbols in the form (30px, 1.5px pin-coloured ring), step numbers (24px), day buttons (40px).
- Scale bars are square-ended, like a printed map scale.
- Icons and legend symbols: 16×16 viewBox, single 1.6 stroke, round caps and joins, `currentColor`, drawn as inline SVG in `src/icons.tsx`.
- The footpath is a 2px dashed line in `path`; over-limit segments switch to `danger-ink`.

## Components

### Buttons
Plain and solid; one primary per screen.
- **Shape:** 8px corners, 44px tall, 16px side padding, weight 600. Small variant 40px, 14px, weight 500.
- **Primary:** Water Blue fill, white text; Deep Water on hover.
- **Secondary:** white with a `line-strong` border; border darkens to `ink-3` on hover.
- **Quiet / links:** blue text, underlined on hover (3px offset).
- **Disabled:** sunken fill, `line` border, `ink-3` text.
- **Remove (per stop):** transparent until hover; when active it turns Footpath Red tint. On phones it shrinks to a 44px icon button and keeps its accessible name.
- Transitions are 120ms ease-out on colour only, and are switched off under `prefers-reduced-motion`.

### Segmented choices
Radio buttons drawn as a joined row, 40px tall, 8px outer corners, `line-strong` dividers.
- **Selected (default):** Shallow Water fill, blue text, weight 650.
- **Interest rows:** take the row's legend colour. Love is a solid pin fill with white text, Some is a 12% pin tint with a 1.5px pin ring, Skip is sunken grey.
- **Focus:** 2px blue outline inset by 3px.

### Inputs / Fields
- **Style:** white, 1px `line-strong` border, 8px corners, 44px tall, label above (14px/600), 6px gap.
- **Hover:** border to `ink-3`. **Focus:** blue border plus a 3px Shallow Water halo.
- **Error:** `danger-ink` border and a 13px `danger-ink` message below. Hints are 13px `ink-2` (amber for warnings).

### Panels
White sheet, 1px `line` border, 14px corners, Sheet shadow, 24px padding. Error panels swap to the Footpath Red tint.

### Step progress
Numbered circles: current is solid blue, done is a blue ring with a blue link, upcoming is grey. On phones all three steps share one row at 13px.

### Fit summary (signature)
A 2×2 key under the plan title (one row of two columns on phones): a 13px `ink-3` label, an Overpass numeral, a scale bar, then a 13px caption. Over-limit items turn the numeral and caption Amber Ink.

### Scale bar (signature)
A 7px square-ended track with a 1px ink outline. The used part is drawn as alternating 12px ink/white segments, a 2px ink tick marks the traveler's limit with an 11px label under it, and any overflow past the tick is solid Footpath Red. It is decorative (`aria-hidden`): the text beside it must say the same thing.

### Route (signature)
Each stop is a two-column grid: a 36px rail with the interest pin, then the stop. The pin is a solid circle in the interest colour with the white legend symbol (18px). A 2px dashed footpath joins the pins and runs beside the walk label ("12 min walk from the previous stop", 13px `ink-3`). An over-limit walk turns the path red and the label bold Amber Ink with an alert icon. A rejected stop greys its pin and strikes through its name.

### Notices and callouts
8px corners, no border. Notices use the sunken fill; warning callouts use `warn-bg` with `warn-ink` text and an alert icon.

### Header band
Map-cover green, white Overpass wordmark with the folded-map mark (26px), pale green tagline on the right. On phones the tagline wraps under the wordmark.

### Empty state
A small route sketch (three pins joined by dashed path) above the panel title and a 60ch description.

## Do's and Don'ts

### Do:
- **Do** use the CSS variables in `styles.css`; add a token there before adding a new hex value.
- **Do** keep one primary (Water Blue) button per screen.
- **Do** pair every status colour with words ("Hours verified", "5 min over your 20-min limit").
- **Do** draw new icons in `icons.tsx` on the 16px grid with the 1.6 stroke, and mark them `aria-hidden` next to a text label.
- **Do** keep controls at 44px (40px minimum) and keep visible focus rings (2px Water Blue).
- **Do** use Overpass for new headings and compared numbers, and tabular numerals for numbers.

### Don't:
- **Don't** use text glyphs (⚠, ✕, ←, →) as icons; use the SVG icons.
- **Don't** add a warm or cream background; the map paper is cool (`bg`).
- **Don't** use Water Blue for anything that isn't an action or a selection (Deep Water stop times are the one exception).
- **Don't** give an interest a second colour or symbol.
- **Don't** set body text, labels or buttons in Overpass.
- **Don't** add shadows inside panels; use a `line` rule or a sunken tint.
- **Don't** add small uppercase labels above headings; headings stand on their own.
