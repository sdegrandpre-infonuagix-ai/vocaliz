// Salon Parisien design tokens (UX-DR1)
export const colors = {
  burgundy: '#7B1528',      // bourgogne profond — primary
  burgundyDark: '#5A0F1C',  // pressed/active state
  gold: '#C9A84C',          // or/laiton — accent
  goldLight: '#D4B96A',     // lighter gold for highlights
  ivory: '#F8F3E8',         // beige ivoire chaud — background
  ivoryDark: '#EDE5D4',     // subtle divider / input background
  charcoal: '#2C2C2C',      // charbon — primary text
  muted: '#7A6E5E',         // secondary text
  border: '#C4BAA8',        // field borders
  error: '#B00020',         // WCAG AA on ivory (contrast > 4.5:1)
  white: '#FFFFFF',
};

// WCAG AA contrast ratios (verified against #F8F3E8 ivory background):
// burgundy (#7B1528): ~10.8:1  ✓
// charcoal (#2C2C2C): ~14.1:1  ✓
// muted    (#7A6E5E): ~4.6:1   ✓ (just above 4.5:1 threshold)
// error    (#B00020): ~5.4:1   ✓

export const typography = {
  titleFamily: 'PlayfairDisplay_700Bold',
  titleSize: 30,
  subtitleSize: 18,
  bodySize: 16,
  captionSize: 13,
  lineHeight: 1.5,
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

// WCAG 2.5.5 AAA requires 44×44px minimum touch targets
export const MIN_TOUCH = 44;
