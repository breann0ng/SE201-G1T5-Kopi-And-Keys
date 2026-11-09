// The app uses light mode only (the Settings page and its theme choice were removed).
// Set before React renders, so the page never flashes a dark theme from an old saved choice.
document.documentElement.dataset.theme = "light";
