/** Formatting helpers and display constants (no components — see shared.jsx). */

export const CONFIDENCE_META = {
  strong: { label: 'Strong', cls: 'badge-success' },
  defensible: { label: 'Defensible', cls: 'badge-info' },
  weak: { label: 'Weak', cls: 'badge-warning' },
  insufficient_information: { label: 'Insufficient information', cls: 'badge-danger' },
  // Reconciliation bucket positions reuse the same scale.
  concede: { label: 'Reverse', cls: 'badge-danger' },
};

export const STATUS_META = {
  VERIFIED: { label: 'Verified', cls: 'badge-success' },
  // Real but no longer good law — reads like sound authority, so it is
  // surfaced as loudly as a fabrication.
  SUPERSEDED: { label: 'Superseded', cls: 'badge-danger' },
  UNVERIFIED: { label: 'Unverified', cls: 'badge-warning' },
  NOT_FOUND: { label: 'Not found', cls: 'badge-danger' },
};

export const ROLE_COLOUR = {
  revenue: 'var(--role-revenue)',
  assessee: 'var(--role-assessee)',
  procedural: 'var(--role-procedural)',
  risk: 'var(--role-risk)',
  chairman: 'var(--role-chairman)',
};

export function formatCurrency(value) {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  if (number >= 10_000_000) return `₹${(number / 10_000_000).toFixed(2)} Cr`;
  if (number >= 100_000) return `₹${(number / 100_000).toFixed(2)} L`;
  return `₹${number.toLocaleString('en-IN')}`;
}

export function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

export function formatCost(value) {
  if (!value) return '$0.00';
  return `$${Number(value).toFixed(value < 0.01 ? 4 : 2)}`;
}

// Defect postures. Held here rather than beside the component so React Fast
// Refresh keeps working — a module that exports both a component and a
// constant loses hot reloading for the whole file.
export const POSTURES = [
  { key: 'explained', label: 'Explained — drop requested',
    hint: 'The arithmetic or the documents answer it. No liability arises.' },
  { key: 'contested', label: 'Contested',
    hint: "The department's law is wrong. This is what convenes counsel." },
  { key: 'agreed_paid', label: 'Agreed and paid',
    hint: 'Correctly raised. Concede, compute interest, discharge by DRC-03.' },
  { key: 'paid_under_protest', label: 'Paid under protest',
    hint: 'Small and arguable. Pay without prejudice, reserve the refund.' },
  { key: 'partial', label: 'Part contested, part discharged',
    hint: 'The limb splits. State which amount goes which way.' },
  { key: 'undecided', label: 'Not yet settled',
    hint: 'Routed to the panel. Must not remain this way at filing.' },
];

// Postures that convene four counsel. The rest are answered by arithmetic,
// documents or a payment, and spending a panel on them buys nothing.
export const ARGUED_POSTURES = new Set(['contested', 'partial', 'undecided']);

export const TAX_HEADS = ['igst', 'cgst', 'sgst', 'cess', 'unallocated'];

export function postureLabel(key) {
  return POSTURES.find((p) => p.key === key)?.label || key || '\u2014';
}

export function headTotal(amounts) {
  return Object.values(amounts || {}).reduce((sum, v) => sum + (Number(v) || 0), 0);
}
