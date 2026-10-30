// Centralized chart color constants — the recharts/inline-style equivalent
// of the CSS custom properties in index.css. Kept in one place so the
// warm CASCADE palette never has to be hand-matched hex-by-hex inside
// individual chart components. Values are the literal hex equivalents of
// the matching CSS token (see index.css :root) because SVG fill/stroke
// props are passed as plain strings by recharts, not resolved against the
// cascade the way a class name would be.

// Chrome/axis/tooltip chrome shared by every recharts chart in the app.
export const CHART_GRID = '#EDE2DA'
export const CHART_AXIS_TEXT = '#948D95'
export const CHART_AXIS_TEXT_STRONG = '#6B6570'
export const CHART_AXIS_LINE = '#E9DED7'
export const CHART_REFERENCE_LINE = '#D9C9BE'
export const CHART_TOOLTIP_BG = '#FFFFFF'
export const CHART_TOOLTIP_BORDER = '#E9DED7'

// Semantic series colors — mirrors --accent/--fc/--edos/--mixed/etc. in
// index.css so a chart and a badge referring to the same class always
// agree visually.
export const CHART_PRIMARY = '#E99A87' // "current run" / proposed detector / primary emphasis
export const CHART_SECONDARY = '#8D7EA6' // baseline / comparison series (muted plum-lavender)
export const CHART_FC = '#8D7EA6' // Flash Crowd class color
export const CHART_EDOS = '#D9765C' // EDoS class color
export const CHART_MIXED = '#B98CA0' // Mixed/interleaved class color, E4 phase markers
export const CHART_PLUM = '#51495D'
export const CHART_GREEN = '#4F8B63' // cost/positive series
export const CHART_AMBER = '#A97A3C' // replica/CPU series

// Endpoint-class colors (cheap/medium/expensive) — a separate taxonomy
// from the EDoS/Flash-Crowd traffic-class colors above.
export const CHART_ENDPOINT_CHEAP = '#DCCFC8'
export const CHART_ENDPOINT_MEDIUM = '#C8BFD0'
export const CHART_ENDPOINT_EXPENSIVE = '#EFA997'
