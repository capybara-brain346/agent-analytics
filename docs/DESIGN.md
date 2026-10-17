---
name: Agent Analytics
description: A compact dark console for agent traffic and its evidence.
colors:
  primary: "#bba4ef"
  background: "#17171b"
  foreground: "#dedee5"
  card: "#1b1b20"
  panel-heading: "#202025"
  popover: "#222228"
  secondary: "#292830"
  muted: "#25252c"
  muted-foreground: "#a2a2af"
  accent: "#302b3d"
  border: "#34343d"
  sidebar: "#141417"
  nav-active: "#2c2639"
  nav-active-text: "#cdb8f3"
  green: "#88c6ac"
  amber: "#dcbf7a"
  destructive: "#ee8b8b"
  search-crawler: "#8c9eff"
  ai-crawler: "#aa8bea"
  other-bot: "#d6b773"
  browser-automation: "#70bfc7"
  ordinary-browser: "#70b49c"
  unknown-class: "#72727e"
typography:
  headline:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif'
    fontSize: "23px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.6px"
  title:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif'
    fontSize: "11px"
    fontWeight: 550
    lineHeight: 1.5
  body:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif'
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: '"cv11", "ss01"'
  label:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif'
    fontSize: "10px"
    fontWeight: 400
    lineHeight: 1.5
  metric:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif'
    fontSize: "25px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "-0.7px"
  mono:
    fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", monospace'
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: "3px"
  md: "4px"
  lg: "5px"
  xl: "6px"
spacing:
  xs: "6px"
  sm: "8px"
  control: "9px"
  compact: "10px"
  md: "12px"
  panel: "13px"
  lg: "16px"
  gutter: "18px"
  section: "20px"
  page: "25px"
components:
  button-outline:
    backgroundColor: "#1c1c22"
    textColor: "#b6b2c2"
    rounded: "{rounded.md}"
    padding: "6px 9px"
  button-ghost:
    textColor: "#aaaab6"
    rounded: "{rounded.sm}"
    size: "24px"
  button-link:
    textColor: "{colors.foreground}"
  input-search:
    backgroundColor: "#1d1c22"
    textColor: "#dcd5e5"
    rounded: "{rounded.md}"
    padding: "0 9px"
    height: "31px"
  nav-item:
    textColor: "#a7a7b3"
    rounded: "{rounded.md}"
    padding: "9px 10px"
  nav-item-active:
    backgroundColor: "{colors.nav-active}"
    textColor: "{colors.nav-active-text}"
    rounded: "{rounded.md}"
    padding: "9px 10px"
  status-chip:
    backgroundColor: "#23332b"
    textColor: "#9bcab1"
    rounded: "{rounded.sm}"
    padding: "1px 5px"
  panel:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.lg}"
  evidence-sheet:
    backgroundColor: "#1c1b22"
    width: "610px"
---

# Design System: Agent Analytics

## Overview

**Creative North Star: "The Evidence Console"**

The console uses the user's three dark observability references. Compact controls, aligned numbers, thin borders, and small charts keep records in view. Color marks selection, traffic class, or status.

The system has no decorative image layer. Panels use a small change in tone. Detail sheets keep the source page visible on wide screens. This record describes the code in `apps/dashboard`; the reference screenshots are review evidence, not shipped assets.

**Key Characteristics:**
- Dense tables and compact charts.
- Charcoal surfaces with fine borders.
- Lavender selection and stable traffic class colors.
- Evidence labels beside claims and values.
- Short state changes and no page-load animation.

## Colors

The palette uses dark neutral surfaces with muted colors for data and state. The frontmatter holds the source values.

### Primary
- **Lavender:** selection, focus outlines, links, and detail actions. Active navigation uses a darker lavender surface and lighter text.

### Secondary
- **Periwinkle:** verified search crawler data.
- **Muted violet:** known AI crawler data.
- **Sand:** other identifiable bot data.
- **Cyan:** browser automation data.
- **Teal:** ordinary browser data.
- **Sage, amber, and soft red:** healthy, caution, and failure states. Status chips use their own darker fills and borders.

### Neutral
- **Charcoal ground:** page background.
- **Deep charcoal:** side rail.
- **Raised charcoal:** panels, panel heads, controls, and popovers.
- **Soft white:** main text.
- **Muted gray:** support text.
- **Fine gray:** borders and dividers.
- **Unknown gray:** unknown traffic class data.

**The Stable Class Rule.** Use the same class color in charts, legends, and table markers. Keep the text label beside each marker.

**The Status Rule.** Use red for failures, denials, and spoofed identity states. Keep status text visible with its color.

## Typography

**Display Font:** No separate display role is used.
**Body Font:** Segoe UI with platform sans-serif fallbacks.
**Label/Mono Font:** SFMono-Regular with Consolas, Liberation Mono, and monospace fallbacks.

The sans-serif face serves the working interface. Monospace separates paths, IDs, methods, and code from prose. Table values and metrics use tabular numbers.

### Hierarchy
- **Headline:** page title. It becomes (22px) at widths up to (800px).
- **Title:** panel heading. It becomes (12px) from (1600px), and (10px) at widths up to (640px).
- **Body:** base text. It becomes (13px) from (1600px). Detail prose often uses (11px).
- **Label:** compact controls, table text, table headings, and evidence labels.
- **Metric:** summary values. They use (23px) at intermediate widths.
- **Mono:** machine values. Table paths use (10px).

**The Numeric Alignment Rule.** Use tabular numbers for values that users compare. Align table number columns to the right.

**The Text Floor Rule.** No text is smaller than (10px). Linked or clickable text follows the same floor.

## Layout

The wide layout has a fixed side rail (204px), a top bar (50px), and a content area with a maximum width (1900px). Main padding is (24px 25px 0). Panel gaps are (18px). Panel heads are (39px) high. Table rows are usually (39px) high.

```text
+----------+-------------------------------------+
| side rail| top bar                             |
|          +-------------------------------------+
|          | page title and filters              |
|          | full-width panels or metric cells   |
|          +----------------------+--------------+
|          | wide data panel      | narrow panel |
+----------+----------------------+--------------+
```

At widths up to (1200px), the rail becomes (184px) and panel gaps become (14px). At widths up to (1020px), standard two-column groups stack; the chart group keeps two columns until (640px). At widths up to (800px), the rail is hidden and a menu control appears. At widths up to (640px), the main horizontal inset is (12px), filters wrap, panel groups stack, and metric cells use three cells above two wider cells. Tables can scroll horizontally.

The mobile chart uses a separate (340-unit) SVG with (24) bars and (12-unit) axis text. The desktop chart uses (900) units and (96) bars. This keeps chart labels readable without stretching the desktop chart into a narrow space.

## Elevation & Depth

Resting panels are flat. Tone and borders separate content. Shadows are reserved for temporary layers. The detail overlay dims the page without blur.

### Shadow Vocabulary
- **Filter popover:** (`0 8px 24px #0005`). Separates an open filter from its panel.
- **Evidence sheet:** (`-10px 0 40px #0005`). Separates the right sheet from the source page.

**The Flat Panel Rule.** Use a border and a panel-head tone for resting containers. Keep shadows on temporary layers.

## Shapes

Corners are small and regular. Controls and navigation use the medium radius. Panels use the large radius. Status chips use the small radius. Borders are normally (1px). Dots and profile avatars are round. Chart bars and table grids remain square or almost square.

## Components

### Buttons

Actions are compact. The outline guide action uses a dark fill and a thin border. Its hover state raises the fill and lightens the text. Icon actions are square and use a tinted hover fill. Text actions use a lavender hover color and an underline. Linked numbers show a dotted underline at rest, so a reader can tell a link from a static value. Global keyboard focus uses a lavender outline (2px) with an offset (3px). Disabled buttons use half opacity and a disabled cursor. The shared library also has a ghost close button; unused library variants are not a screen design rule.

### Chips

Status chips pair text with a small dot. Green, amber, red, purple, and neutral variants each have a dark fill and a fine matching border. Selected filter chips have a stronger lavender border and fill. Evidence labels use a dot and the words Observed, Inferred, or Unknown; they are not decorative headings.

### Cards / Containers

Panels have a fine neutral border, a dark body, and a slightly lighter head. Horizontal panel padding commonly uses the panel spacing token. Tables use alternate row tones and a brighter hover row. Metric cells share one bordered strip rather than separate floating cards.

### Inputs / Fields

Search fields have a thin border, a dark fill, a search icon, and a clear action when text is present. Focus changes the wrapper border. Select controls are compact native selects inside a styled wrapper; keyboard focus adds a lavender outline. Keep a text label available to assistive technology.

### Navigation

Navigation rows pair line icons with labels. The active row has a lavender tint and a slim marker at the left edge. Hover raises the neutral fill and text. On smaller screens, a menu control replaces the fixed rail. Tabs use a slim active underline.

### Evidence Sheet

The right sheet has a tinted head, a scrollable body, and a close action. Its desktop width uses the component token, capped at the viewport minus (34px). At widths up to (640px), it fills the viewport width. Sheet state changes take (200ms); the overlay fades in (150ms). Reduced-motion settings remove transitions and animations.

A sheet opened from another sheet shows a "Back to <previous>" control above the title. Close returns through the same history entries, so browser Back does not reopen a closed sheet. A request sheet steps to the previous or next request of its session.

### Evidence Context Bar

A list opened from a recommendation shows a tinted bar above the table: the recommendation title, the sample count against the full count, a link back to the recommendation, and a remove action. Filters that have no control on the page show as removable chips.

### Help Popover

Help icons open a small popover on click, tap, or hover. It uses the popover surface, a fine border, and the temporary-layer shadow.

## Do's and Don'ts

### Do:
- **Do** keep evidence labels and data limits beside the relevant content.
- **Do** keep class colors consistent across charts, legends, and tables.
- **Do** keep paths in monospace and comparable numbers aligned.
- **Do** use borders and tone to separate resting panels.
- **Do** keep keyboard focus visible and charts readable on small screens.

### Don't:
- **Don't** use decorative imagery, gradients, or glow in this console.
- **Don't** use color alone to state identity, confidence, or outcome.
- **Don't** add display type or large rounded cards to the compact working interface.
- **Don't** use the smallest support-text sizes as a default for new content.
