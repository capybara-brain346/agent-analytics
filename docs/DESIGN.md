---
name: Agent Analytics
description: A light product console for agent traffic and its evidence, built on the Webzero design system.
colors:
  ink: "#0f1113"
  body: "#3b434e"
  muted-text: "#5a6270"
  grey: "#6b7280"
  faint: "#a2a8b0"
  hairline: "#e6e8eb"
  seam: "#f0f1f3"
  stone: "#fafaf9"
  wash: "#edeef0"
  row-hover: "#f4f5f6"
  border-hover: "#c9cdd3"
  track: "#eeeff1"
  jade: "#0ba96c"
  jade-deep: "#078054"
  jade-press: "#06603e"
  jade-tint: "#e6f7f0"
  pass: "#1f7a4d"
  warn-mark: "#cf8b2e"
  warn-text: "#a0611a"
  warn-tint: "#faf1e3"
  fail: "#c33a22"
  fail-tint: "#fbeeeb"
  neutral: "#c9cdd3"
typography:
  screen-title:
    fontFamily: "Instrument Sans"
    fontSize: "16px"
    fontWeight: 600
    letterSpacing: "-0.02em"
  panel-title:
    fontFamily: "Instrument Sans"
    fontSize: "15px"
    fontWeight: 600
    letterSpacing: "-0.015em"
  metric:
    fontFamily: "Instrument Sans"
    fontSize: "38px"
    fontWeight: 500
    letterSpacing: "-0.04em"
  body:
    fontFamily: "Instrument Sans"
    fontSize: "13px"
    fontWeight: 400
  table-identity:
    fontFamily: "JetBrains Mono"
    fontSize: "14px"
    fontWeight: 500
  column-header:
    fontFamily: "JetBrains Mono"
    fontSize: "12px"
    fontWeight: 500
rounded:
  key-badge: "4px"
  pill: "5px"
  segmented-item: "6px"
  button: "7px"
  menu: "8px"
spacing:
  panel-body: "16px 18px 18px"
  workspace: "18px 20px 28px"
  metric-cell: "16px 18px 18px"
components:
  button-primary:
    backgroundColor: "{colors.jade-deep}"
    textColor: "#ffffff"
    rounded: "{rounded.button}"
    height: "34px"
  button-secondary:
    backgroundColor: "#2a2e34"
    textColor: "#ffffff"
    rounded: "{rounded.button}"
    height: "34px"
  button-standard:
    backgroundColor: "#ffffff"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    height: "34px"
  nav-item-active:
    backgroundColor: "{colors.wash}"
    textColor: "{colors.ink}"
    height: "34px"
  panel:
    backgroundColor: "#ffffff"
  evidence-sheet:
    backgroundColor: "#ffffff"
    width: "560px"
---

# Design System: Agent Analytics

## Overview

**Creative North Star: "The Evidence Console"**

The console follows the Webzero product console layer. It is light and flat. Hairlines separate content. Stone is the only workspace ground. Jade marks live things and the main action. Everything else is ink and grey.

The system has no decorative image layer, no gradients, and no resting shadows. Records stay in view: dense tables, aligned figures, and small charts. This record describes the code in `apps/dashboard`.

**Key Characteristics:**
- Light theme only. White panels on a Stone workspace.
- Square containers with 1px hairline borders.
- Whole-row clickable tables with seams, no zebra, no vertical rules.
- Evidence labels beside claims and values.
- Short state changes and no page-load animation.

## Colors

The frontmatter holds the source values. Tokens are CSS variables in `src/app/styles/tokens.css`. Do not write hex values in other style files.

### Text
- **Ink:** titles, figures, identity text, and the active nav item.
- **Body:** running text and controls.
- **Muted text:** metric labels and secondary text.
- **Grey:** the lowest text tier: notes, meta lines, column headers.
- **Faint:** placeholders and disabled marks only.

### Surfaces
- **White:** rail, top bar, panels, sheets, and menus.
- **Stone:** the workspace ground and table headers.
- **Hairline:** borders and the 1px gaps between panels. **Seam:** row dividers.
- **Wash:** hover, focus, and the active nav item. **Row hover:** table row hover.

### Jade and state
- **Jade (marks only):** chart primary series, live dots, selected marks. Never body text.
- **Jade deep:** jade text (links, actions) and the primary button ground. **Press:** its hover.
- **Pass, warn, fail:** state. Warn has a mark colour for shapes and a darker text colour for words. Each has a tint for pill grounds.
- **Neutral:** unknown and empty marks.

### Traffic classes
Class colours are defined once in `src/lib/classes.ts`. They differ in lightness so stacked segments stay distinct on white. Use the same colour in charts, legends, and table markers, and keep the class name beside each marker.

**The Color Is Never Alone Rule.** Every coloured word has a dot, a square, or a bar beside it.

**The Confidence Rule.** Confidence has no state colour. The word is Body. Bars are ink, with empty bars in neutral.

## Typography

**Sans:** Instrument Sans (400, 500, 600) for every human word.
**Mono:** JetBrains Mono (400, 500) only for machine strings (ids, paths, URLs, versions, times, status codes, key badges) and for uppercase column headers and nav group labels.

Both load through `next/font/google`.

### Hierarchy
- **Screen title:** 16/600, shown as the breadcrumb in the top bar. No title in the workspace.
- **Panel title:** 15/600.
- **Metric figure:** 38/500, tabular. Label 13/500 muted, sentence case. Note 13/400 grey.
- **Table identity:** mono 14/500 ink, with a mono 12 grey meta line. Table figure 19/500 tabular. Column header mono 12/500 uppercase grey.
- **Nav item:** 14/400, 600 when active. Controls and pills: 13/500.

**The Text Floor Rule.** No sans text is smaller than 13px. No mono text is smaller than 12px.

**The Numeric Alignment Rule.** Use tabular numbers on all figures. Right-align table figures.

## Layout

The shell fills the viewport and does not scroll. The rail is 244px. The top bar is 56px. The workspace is the only scroll region (padding 18px 20px 28px). The global filter bar (site, range, class, window caption) is the first item in the workspace. A status row in mono 12 grey ends the workspace and shows data provenance.

```text
+-----------+-------------------------------------+
| rail 244  | top bar 56 (breadcrumb, freshness)  |
|           +-------------------------------------+
|           | filter bar                          |
|           | metric strip or panels (18px gap)   |
|           +----------------------+--------------+
|           | main panel           | insight 336  |
|           +----------------------+--------------+
|           | status row                          |
+-----------+-------------------------------------+
```

Panels in a grid use a 1px gap on a hairline ground. Below 1000px the rail hides and a menu control opens it as a drawer. Two-column groups stack. Tables drop qualifier-type columns first, then keep identity, status, and figure. Tables can scroll horizontally.

Metric strips use cells of 16px 18px 18px. The label sits at the top of the cell and the figure sits at the bottom, so figures align across a row when a label wraps.

## Elevation & Depth

Containers are square and flat. Tone and hairlines separate content. The only shadow is on menus and popovers (`0 18px 44px rgba(14,17,22,0.09)`, radius 8). The detail overlay dims the page without blur.

**The Flat Panel Rule.** Resting containers use a border only.

## Components

### Panels
White, 1px hairline border, 48px header with a 15/600 title, an optional grey count, and at most one right-aligned jade-deep action. Body padding is 16px 18px 18px. Tables and charts run full bleed.

### Tables
Header 34px on Stone. Rows are 52px (compact 44px) and whole-row clickable. Order: identity, status, figure, qualifier, time, then a chevron. A footer shows `Showing N ...` on the left and page buttons on the right. Never explain a table in a paragraph above it; use header tooltips.

### Pills and qualifiers
A status pill is sans 12/500 with a tinted ground, a 6px dot, and radius 5. Running pills pulse; nothing else does. A qualifier is a 7px square plus a word.

### Buttons and controls
All controls are 34px tall. One primary button per screen at most (jade-deep). Secondary uses a dark ground. Standard is white with a hairline. Segmented filters have a 3px white shell, 28px items, and an ink fill when active. Search is a 34px hairline field.

### Navigation
Group labels are mono 12 uppercase grey. Items are 34px with a 6px dot (idle light grey, active ink). The active item has a wash ground and ink 600 text. There is no accent bar.

### Evidence Sheet
A right sheet, 560px wide (capped to the viewport on small screens), white with a hairline left border and a 48px header. A sheet opened from another sheet shows a "Back to <previous>" control. A request sheet steps to the previous or next request of its session.

### Evidence Context Bar
A list opened from a recommendation shows a bar above the table: the recommendation title, the sample count against the full count, a link back, and a remove action. Filters with no control on the page show as removable chips.

### Empty and error states
An empty state is one 13px sentence and one control. An error keeps the row shape.

## Motion and interaction

Hover and focus change the background to wash. They never add a ring, underline, or accent border. Keyboard focus uses a visible wash-focus outline. Transitions use 180ms with `cubic-bezier(0.2, 0.7, 0.2, 1)`. There are no entrance animations, counters, or staggers. Reduced-motion settings remove transitions and animations.

## Do's and Don'ts

### Do:
- **Do** keep evidence labels and data limits beside the relevant content.
- **Do** keep class colours consistent across charts, legends, and tables.
- **Do** keep machine strings in mono and figures aligned.
- **Do** use sentence case. Use an en dash for ranges.

### Don't:
- **Don't** use shadows, gradients, glow, or decorative imagery.
- **Don't** use colour alone to state identity, confidence, or outcome.
- **Don't** use jade for body text, or more than one primary button per screen.
- **Don't** use em dashes, exclamation marks, or emoji.
