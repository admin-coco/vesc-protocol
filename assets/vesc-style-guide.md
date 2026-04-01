# VESC Style Guide

Reference for developers extending VESC UI. Follow this guide to ensure visual consistency across all VESC-branded interfaces and components.

---

## Table of Contents

- [Design Philosophy](#design-philosophy)
- [Color Palette](#color-palette)
- [Typography](#typography)
- [Spacing & Layout](#spacing--layout)
- [Border Radius](#border-radius)
- [Shadows & Glows](#shadows--glows)
- [Background System](#background-system)
- [Dark Mode](#dark-mode)
- [Light Mode](#light-mode)
- [Component: Navbar](#component-navbar)
- [Component: Buttons](#component-buttons)
- [Component: Swap Card](#component-swap-card)
- [Component: Input Panel](#component-input-panel)
- [Component: Token Selector](#component-token-selector)
- [Component: Swap Toggle Button](#component-swap-toggle-button)
- [Component: Warning Notice](#component-warning-notice)
- [Component: Dropdown Menu](#component-dropdown-menu)
- [Animations & Transitions](#animations--transitions)
- [Wallet Connect (RainbowKit)](#wallet-connect-rainbowkit)

---

## Design Philosophy

- **Dark-first.** All primary surfaces are dark zinc/black. Teal is the single accent color.
- **Subtle depth.** Cards use low-opacity white fills (`rgba(255,255,255,0.04)`) rather than flat gray — gives depth without loudness.
- **One accent.** `#1093a4` (teal) is used exclusively for interactive elements, active states, and brand moments. Never use it decoratively.
- **Glassmorphism sparingly.** Backdrop blur only on the navbar and modals — not on content cards.
- **Responsive scale.** All components have a mobile base size and a `sm:` breakpoint variant.

---

## Color Palette

### Brand / Accent

```css
--vesc-primary:        #1093a4;   /* main teal — buttons, links, active states */
--vesc-primary-hover:  #0d7a89;   /* hover state */
--vesc-accent-bright:  #15c5db;   /* bright cyan — gradient start, rings */
--vesc-accent-dark:    #0a5f6b;   /* dark teal — gradient end */
--vesc-accent-deeper:  #084850;   /* deep hover gradient end */
```

**Alpha variants (use for backgrounds, borders, glows):**
```css
--vesc-primary-5:   #1093a40d;   /* 5%  — very faint tint */
--vesc-primary-10:  #1093a41a;   /* 10% — subtle hover background */
--vesc-primary-20:  #1093a433;   /* 20% — disabled button fill */
--vesc-primary-30:  #1093a44d;   /* 30% — border on focus */
--vesc-primary-50:  #1093a480;   /* 50% — disabled button text */

--vesc-bright-5:    #15c5db0d;
--vesc-bright-8:    #15c5db14;
--vesc-bright-10:   #15c5db1a;
--vesc-bright-20:   #15c5db33;
--vesc-bright-30:   #15c5db4d;
--vesc-bright-50:   #15c5db80;
```

### Surfaces

```css
--vesc-bg:           #000000;    /* page background */
--vesc-bg-alt:       #0a0a0a;    /* slight lift */
--vesc-card:         #09090b;    /* zinc-950 — swap card, modals */
--vesc-card-inner:   rgba(255, 255, 255, 0.04);  /* input panels */
--vesc-card-hover:   rgba(255, 255, 255, 0.06);  /* input panel hover */
--vesc-overlay:      rgba(0, 0, 0, 0.95);        /* navbar, dropdown bg */
```

### Borders

```css
--vesc-border:       rgba(255, 255, 255, 0.10);  /* default card border */
--vesc-border-faint: rgba(255, 255, 255, 0.05);  /* navbar bottom border */
--vesc-border-focus: rgba(21, 197, 219, 0.30);   /* teal border on focus */
```

### Text

```css
--vesc-text:         #ffffff;                    /* primary */
--vesc-text-muted:   rgba(255, 255, 255, 0.60);  /* secondary labels */
--vesc-text-faint:   rgba(255, 255, 255, 0.50);  /* sell/buy label */
--vesc-text-ghost:   rgba(255, 255, 255, 0.30);  /* placeholder */
```

### Status Colors

```css
--vesc-success:      #00d294;    /* emerald-400 */
--vesc-warning:      #fac800;    /* yellow-400 */
--vesc-warning-bg:   rgba(234, 179, 8, 0.05);
--vesc-warning-border: rgba(234, 179, 8, 0.20);
--vesc-error:        #fb2c36;    /* red-500 */
--vesc-connected:    #30E000;    /* wallet connected indicator */
```

### Protocol Brand Colors (external integrations)

```css
--color-base-blue:   #0052FF;    /* Base network */
--color-usdc-blue:   #2775CA;    /* USDC */
--color-eth-purple:  #627EEA;    /* Ethereum */
```

---

## Typography

### Font Families

```css
/* Load via Next.js next/font or Google Fonts */
--font-display: "Plus Jakarta Sans", sans-serif;   /* hero headings only */
--font-body:    "Geist", sans-serif;               /* all body text, UI */
--font-mono:    "Geist Mono", monospace;           /* addresses, amounts, code */
```

**Plus Jakarta Sans weights:** 400, 500, 600, 700, 800
**Geist weights:** 100–900 variable
**Geist Mono weights:** 100–900 variable

### Type Scale

| Token | Size | Line Height | Usage |
|---|---|---|---|
| `text-xs` | 0.75rem (12px) | 1.33 | Warning notices, fine print |
| `text-sm` | 0.875rem (14px) | 1.43 | Nav links, labels, secondary UI |
| `text-base` | 1rem (16px) | 1.5 | Body copy |
| `text-lg` | 1.125rem (18px) | 1.56 | Submit button (sm breakpoint) |
| `text-xl` | 1.25rem (20px) | 1.4 | — |
| `text-2xl` | 1.5rem (24px) | 1.33 | Input dollar sign |
| `text-4xl` | 2.25rem (36px) | 1.11 | Input amounts (mobile) |
| `text-5xl` | 3rem (48px) | 1.0 | Input amounts (sm breakpoint) |
| Hero h1 | 1.75rem (28px) | tight | Mobile hero |
| Hero h1 sm | 2.25rem (36px) | tight | sm hero |
| Hero h1 md | 3rem (48px) | tight | md hero |

### Usage Rules

- **Plus Jakarta Sans** — hero `<h1>` only, `font-extrabold` (800)
- **Geist** — all UI: labels, buttons, nav, inputs
- **Geist Mono** — contract addresses, token amounts, numeric data
- `tracking-tight` (`-0.025em`) on all headings
- Never use system fonts for branded UI elements

---

## Spacing & Layout

Base unit: `0.25rem` (4px). All spacing is multiples of this.

```
4px   — gap between tight inline elements
6px   — token selector internal gap
8px   — icon button padding, small gaps
12px  — card padding (mobile), dropdown item padding
16px  — card padding (sm), nav horizontal padding, button padding
20px  — input panel padding (sm)
24px  — section gaps
```

**Max widths:**
```css
--max-content:   80rem;   /* 1280px — page content */
--max-swap-card: 480px;   /* swap component */
```

**Navbar height:** `56px` (mobile) / `64px` (sm)

---

## Border Radius

```css
--radius-sm:   4px;    /* fine details */
--radius-md:   8px;    /* dropdown items, icon badges */
--radius-lg:   12px;   /* buttons, nav links, swap toggle */
--radius-xl:   16px;   /* input panels (mobile), swap card (mobile) */
--radius-2xl:  24px;   /* input panels (sm), swap card (sm) */
--radius-full: 9999px; /* token selector pill, language switcher */
```

**Rule:** Card containers use `radius-2xl`. Inner panels use `radius-xl` (mobile) or `radius-2xl` (sm). Buttons use `radius-lg`. Pills use `radius-full`.

---

## Shadows & Glows

```css
/* Primary CTA button shadow */
box-shadow:
  0 10px 15px -3px rgba(16, 147, 164, 0.20),
  0 4px 6px -4px rgba(16, 147, 164, 0.20);

/* Dropdown / modal shadow */
box-shadow:
  0 20px 25px -5px rgba(0, 0, 0, 0.10),
  0 8px 10px -6px rgba(0, 0, 0, 0.10);

/* Wallet connect button shadow */
box-shadow: 0 4px 12px rgba(0, 0, 0, 0.10);

/* Focus ring (teal glow) */
box-shadow: 0 0 0 2px rgba(21, 197, 219, 0.30);
```

---

## Background System

The page background is pure black with two layered gradient overlays for depth. These sit behind all content.

```css
/* Layer 1 — linear gradient from bottom 70% */
position: absolute;
inset: 0;
background: linear-gradient(
  to top,
  rgba(16, 147, 164, 0.50) 0%,
  rgba(39, 117, 202, 0.30) 30%,
  transparent 100%
);
pointer-events: none;

/* Layer 2 — radial gradient from bottom center */
position: absolute;
inset: 0;
background: radial-gradient(
  ellipse 120% 80% at 50% 100%,
  rgba(16, 147, 164, 0.40) 0%,
  rgba(39, 117, 202, 0.30) 40%,
  transparent 70%
);
pointer-events: none;
```

Both layers are `z-0`. All page content is `z-10` or higher.

---

## Dark Mode

The VESC UI is **dark-only**. There is no light mode on the main app. When building extensions or embeds, always default to dark.

```css
:root {
  --background: #000000;
  --foreground: #ffffff;
  color-scheme: dark;
}

body {
  background: var(--background);
  color: var(--foreground);
  font-family: var(--font-body);
  -webkit-font-smoothing: antialiased;
}
```

---

## Light Mode

Light mode is not implemented in the main app but is provided here for developers building documentation sites, partner portals, or embeds that require it.

```css
@media (prefers-color-scheme: light) {
  :root {
    --background:        #FAF8F5;
    --foreground:        #0a0a0a;

    --vesc-card:         #ffffff;
    --vesc-card-inner:   rgba(0, 0, 0, 0.04);
    --vesc-card-hover:   rgba(0, 0, 0, 0.06);
    --vesc-overlay:      rgba(255, 255, 255, 0.95);

    --vesc-border:       rgba(0, 0, 0, 0.10);
    --vesc-border-faint: rgba(0, 0, 0, 0.05);

    --vesc-text:         #0a0a0a;
    --vesc-text-muted:   rgba(0, 0, 0, 0.60);
    --vesc-text-faint:   rgba(0, 0, 0, 0.50);
    --vesc-text-ghost:   rgba(0, 0, 0, 0.30);

    /* Brand accent stays the same — teal works on both */
    --vesc-primary:       #1093a4;
    --vesc-primary-hover: #0d7a89;
  }
}
```

**Light mode surface stack:**
- Page bg: `#FAF8F5` (warm off-white)
- Card: `#ffffff`
- Inner panel: `rgba(0,0,0,0.04)`
- Border: `rgba(0,0,0,0.10)`
- Text: `#0a0a0a`
- All accent colors remain identical (teal is brand-constant)

---

## Component: Navbar

```css
.navbar {
  position: fixed;
  top: 0; left: 0; right: 0;
  z-index: 60;
  height: 56px; /* sm: 64px */
  border-bottom: 1px solid var(--vesc-border-faint);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  background: var(--vesc-overlay);
}

.navbar-inner {
  max-width: 80rem;
  margin: 0 auto;
  padding: 0 12px; /* sm: 16px */
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.nav-link {
  padding: 8px 16px;
  border-radius: 12px;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--vesc-text-muted);
  transition: color 150ms, background 150ms;
}

.nav-link:hover { color: var(--vesc-text); }

.nav-link.active {
  background: rgba(255, 255, 255, 0.10);
  color: var(--vesc-text);
}
```

---

## Component: Buttons

### Primary Gradient Button

```css
.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 12px;
  font-size: 0.875rem;
  font-weight: 600;
  color: #ffffff;
  background: linear-gradient(to right in oklab, #15c5db, #0a5f6b);
  box-shadow:
    0 10px 15px -3px rgba(16, 147, 164, 0.20),
    0 4px  6px -4px rgba(16, 147, 164, 0.20);
  transition: background 150ms, transform 100ms;
  cursor: pointer;
  border: none;
}

.btn-primary:hover {
  background: linear-gradient(to right, #13adc0, #084850);
}

.btn-primary:active {
  transform: scale(0.98);
}
```

### Submit Button (active)

```css
.btn-submit {
  width: 100%;
  border-radius: 12px; /* sm: 16px */
  padding: 12px 0;     /* sm: 16px */
  font-size: 1rem;     /* sm: 1.125rem */
  font-weight: 600;
  color: #ffffff;
  background: linear-gradient(to right in oklab, #15c5db, #0a5f6b);
  transition: all 150ms;
  border: none;
  cursor: pointer;
}

.btn-submit:active { transform: scale(0.99); }
```

### Submit Button (disabled)

```css
.btn-submit:disabled {
  background: rgba(16, 147, 164, 0.20);
  color: rgba(16, 147, 164, 0.50);
  cursor: not-allowed;
}

.btn-submit:disabled:active { transform: none; }
```

### Icon Button (nav social links)

```css
.btn-icon {
  padding: 8px;
  border-radius: 8px;
  color: var(--vesc-text-muted);
  transition: color 150ms, background 150ms;
  background: transparent;
  border: none;
  cursor: pointer;
}

.btn-icon:hover {
  color: var(--vesc-text);
  background: rgba(255, 255, 255, 0.10);
}
```

---

## Component: Swap Card

The swap card is the primary UI element. Max width 480px, centered on page.

```html
<div class="swap-card">
  <!-- SELL panel -->
  <div class="swap-panel">...</div>

  <!-- Direction toggle -->
  <div class="swap-toggle-wrapper">
    <button class="swap-toggle">...</button>
  </div>

  <!-- BUY panel -->
  <div class="swap-panel">...</div>

  <!-- Submit -->
  <button class="btn-submit" disabled>Enter an amount</button>

  <!-- Warning -->
  <div class="swap-notice">...</div>
</div>
```

```css
.swap-card {
  width: 100%;
  max-width: 480px;
  border-radius: 16px;       /* sm: 24px */
  border: 1px solid var(--vesc-border);
  background: var(--vesc-card);
  padding: 12px;             /* sm: 16px */
}
```

---

## Component: Input Panel

Used for both the SELL and BUY sections inside the swap card.

```html
<div class="swap-panel">
  <div class="swap-panel-header">
    <span class="swap-panel-label">Sell</span>
    <!-- optional: balance display -->
  </div>
  <div class="swap-panel-row">
    <div class="swap-panel-input-wrapper">
      <span class="swap-panel-prefix">$</span>
      <input
        type="text"
        inputmode="decimal"
        placeholder="0"
        class="swap-panel-input"
      />
    </div>
    <!-- Token selector -->
    <button class="token-selector">...</button>
  </div>
</div>
```

```css
.swap-panel {
  border-radius: 16px;       /* sm: 24px */
  padding: 16px;             /* sm: 20px */
  background: var(--vesc-card-inner);
  transition: background 150ms;
}

.swap-panel:hover {
  background: var(--vesc-card-hover);
}

.swap-panel-header {
  margin-bottom: 12px;       /* sm: 16px */
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.swap-panel-label {
  font-size: 0.75rem;        /* sm: 0.875rem */
  color: var(--vesc-text-faint);
  flex-shrink: 0;
}

.swap-panel-row {
  display: flex;
  align-items: center;
  gap: 8px;                  /* sm: 12px */
  min-height: 48px;          /* sm: 56px */
}

.swap-panel-input-wrapper {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.swap-panel-prefix {
  font-size: 1.5rem;         /* sm: 2.25rem */
  font-weight: 500;
  color: var(--vesc-text-faint);
  flex-shrink: 0;
}

.swap-panel-input {
  min-width: 0;
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  font-size: 2.25rem;        /* sm: 3rem */
  font-weight: 500;
  font-family: var(--font-body);
  color: var(--vesc-text);
}

.swap-panel-input::placeholder {
  color: var(--vesc-text-ghost);
}
```

---

## Component: Token Selector

The pill button showing the selected token (USDC / VESC).

```html
<button class="token-selector">
  <img src="/token-logo.png" class="token-selector-img" alt="USDC" />
  <span class="token-selector-label">USDC</span>
  <svg class="token-selector-chevron">...</svg>
</button>
```

```css
.token-selector {
  display: flex;
  align-items: center;
  gap: 6px;                  /* sm: 8px */
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.10);
  padding: 6px 8px 6px 6px; /* sm: 8px 12px 8px 8px */
  border: none;
  cursor: pointer;
  transition: background 150ms;
  flex-shrink: 0;
}

.token-selector:hover {
  background: rgba(255, 255, 255, 0.15);
}

.token-selector-img {
  width: 24px; height: 24px; /* sm: 32px */
  border-radius: 9999px;
  object-fit: cover;
  flex-shrink: 0;
}

.token-selector-label {
  font-size: 0.875rem;       /* sm: 1rem */
  font-weight: 500;
  color: var(--vesc-text);
  white-space: nowrap;
}

.token-selector-chevron {
  color: var(--vesc-text-muted);
  width: 16px; height: 16px;
  flex-shrink: 0;
}
```

---

## Component: Swap Toggle Button

The directional arrow between SELL and BUY panels.

```html
<div class="swap-toggle-wrapper">
  <button class="swap-toggle group">
    <svg class="swap-toggle-icon"><!-- arrows icon --></svg>
  </button>
</div>
```

```css
.swap-toggle-wrapper {
  position: relative;
  z-index: 10;
  margin: -16px 0;           /* -my-4: overlaps both panels */
  display: flex;
  justify-content: center;
}

.swap-toggle {
  border-radius: 12px;
  border: 4px solid var(--vesc-card); /* creates the inset gap illusion */
  background: #27272a;               /* zinc-800 */
  padding: 8px;
  cursor: pointer;
  transition: background 150ms, transform 100ms;
}

.swap-toggle:hover {
  background: #3f3f46;               /* zinc-700 */
}

.swap-toggle:active {
  transform: scale(0.95);
}

.swap-toggle-icon {
  width: 16px; height: 16px;
  color: var(--vesc-text);
  transition: transform 300ms cubic-bezier(0.22, 1, 0.36, 1);
}

.swap-toggle:hover .swap-toggle-icon {
  transform: rotate(180deg);
}
```

---

## Component: Warning Notice

Used to display the official contract address below the swap card.

```html
<div class="swap-notice">
  Official VESCVault Contract: 0x50F50cF026837aB49f337927d2B3269a7DEDbc60
</div>
```

```css
.swap-notice {
  margin-top: 12px;          /* sm: 16px */
  border-radius: 12px;
  border: 1px solid var(--vesc-warning-border);
  background: var(--vesc-warning-bg);
  padding: 12px;
  font-size: 10px;           /* sm: 12px */
  color: rgba(250, 200, 0, 0.80);
  font-family: var(--font-mono);
  line-height: 1.5;
}
```

---

## Component: Dropdown Menu

```css
.dropdown {
  background: var(--vesc-overlay);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid var(--vesc-border);
  border-radius: 12px;
  padding: 8px;
  min-width: 240px;
  box-shadow:
    0 20px 25px -5px rgba(0, 0, 0, 0.10),
    0 8px  10px -6px rgba(0, 0, 0, 0.10);
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 400;
  color: var(--vesc-text-muted);
  cursor: pointer;
  transition: color 150ms, background 150ms;
}

.dropdown-item:hover {
  color: var(--vesc-text);
  background: rgba(255, 255, 255, 0.10);
}

.dropdown-item-icon {
  width: 28px; height: 28px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.10);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
```

---

## Animations & Transitions

```css
/* Default transition */
--transition-base: 150ms cubic-bezier(0.4, 0, 0.2, 1);

/* Snappy spring (used on hero, modals) */
--transition-spring: 700ms cubic-bezier(0.22, 1, 0.36, 1);

/* Icon rotation (swap toggle) */
--transition-rotate: 300ms cubic-bezier(0.22, 1, 0.36, 1);

/* Loading spinner */
animation: spin 1s linear infinite;

/* Pulse (loading states) */
animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
```

**Hero entrance animation:**
```css
.hero-enter {
  opacity: 0;
  transform: translateY(8px) scale(0.98);
  filter: blur(4px);
  transition: all 700ms cubic-bezier(0.22, 1, 0.36, 1);
}

.hero-enter-active {
  opacity: 1;
  transform: translateY(0) scale(1);
  filter: blur(0);
}
```

---

## Wallet Connect (RainbowKit)

When integrating RainbowKit, apply these theme variables to match the VESC style:

```js
const vescTheme = {
  blurs: { modalOverlay: 'blur(4px)' },
  fonts: { body: 'Geist, sans-serif' },
  radii: {
    actionButton: '9999px',
    connectButton: '12px',
    menuButton: '12px',
    modal: '24px',
    modalMobile: '28px',
  },
  colors: {
    accentColor: '#1093a4',
    accentColorForeground: '#ffffff',
    connectButtonBackground: '#1A1B1F',
    connectButtonText: '#ffffff',
    connectionIndicator: '#30E000',
    modalBackground: '#1A1B1F',
    modalText: '#ffffff',
    modalTextSecondary: 'rgba(255,255,255,0.6)',
    generalBorder: 'rgba(255,255,255,0.08)',
    error: '#FF494A',
    standby: '#FFD641',
  },
  shadows: {
    connectButton: '0px 4px 12px rgba(0,0,0,0.10)',
    dialog: '0px 8px 32px rgba(0,0,0,0.32)',
  },
};
```

---

## Quick Reference Card

| Token | Value |
|---|---|
| Primary brand | `#1093a4` |
| Bright accent | `#15c5db` |
| Page bg | `#000000` |
| Card bg | `#09090b` |
| Inner panel | `rgba(255,255,255,0.04)` |
| Border | `rgba(255,255,255,0.10)` |
| Text primary | `#ffffff` |
| Text muted | `rgba(255,255,255,0.60)` |
| Body font | Geist |
| Display font | Plus Jakarta Sans |
| Mono font | Geist Mono |
| Card radius | 16px / 24px (mobile/sm) |
| Button radius | 12px |
| Pill radius | 9999px |
| Backdrop blur | 24px |
| Default transition | 150ms ease |
