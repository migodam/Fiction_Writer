# Developer UI Tokens (DEV_UI_TOKENS)

**Rule: Never use raw hex colors in components; always use semantic tokens.**

## Design Tokens (Tailwind + CSS Variables)

The UI uses a centralized token system defined in `src/ui-react/style.css` and mapped into `tailwind.config.js`.

### Colors

*   **Surfaces:**
    *   `bg-bg`: Main application background.
    *   `bg-bg-elev-1`: Elevated background (e.g., sidebars).
    *   `bg-bg-elev-2`: Higher elevation background.
    *   `bg-panel`: Background for distinct panels.
    *   `bg-card`, `bg-card-2`: Background for cards/widgets.
*   **Lines & Borders:**
    *   `border-border`, `border-border-2`: General borders.
    *   `border-divider`: Subtle dividers.
*   **Text:**
    *   `text-text`: Primary text.
    *   `text-text-2`: Secondary text (muted).
    *   `text-text-3`: Tertiary text (faint).
    *   `text-text-invert`: Inverted text (for dark-on-light).
*   **Brand & Accents:**
    *   `text-brand`, `bg-brand`: Primary brand color.
    *   `text-brand-2`, `bg-brand-2`: Secondary brand accent.
    *   Semantic colors: `blue`, `green`, `red`, `amber`, `cyan`.
*   **States:**
    *   `bg-hover`, `bg-active`, `bg-selected`.
    *   `focus:ring-focus`: Outline for focused elements.

### Radius & Shadows
*   `rounded-xs`, `rounded-sm`, `rounded-md`, `rounded-lg`
*   `shadow-1`, `shadow-2`

### Sizing
*   Heights: `h-top-toolbar`, `h-status-bar`
*   Widths: `w-activity-bar`, `w-sidebar`, `w-inspector`

**Example Usage:**

```tsx
// Bad
<div className="bg-[#0B0F14] text-[#cccccc] border-[#333333]">

// Good
<div className="bg-bg text-text-2 border-border rounded-md shadow-1">
```
