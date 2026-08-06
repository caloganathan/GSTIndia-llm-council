# Frontend — Compliance Panel

React + Vite. The API is same-origin by default: the dev server proxies
`/api` to the backend on **:8001** (see `vite.config.js`), and in a
single-service deployment the backend serves this bundle itself.

```bash
npm install
npm run dev      # UI on :5173, proxying /api to :8001
npm run lint
npm run build    # emits dist/, which the backend serves when present
```

Run the backend alongside it with `uv run python -m backend.main` from the
repository root, or use `./start.sh` to bring both up.

## Split deployment

To serve the bundle from a static host with the API elsewhere, bake the API's
public URL in at build time:

```bash
VITE_API_BASE_URL=https://your-api.onrender.com npm run build
```

The API must then allow that origin (`CORS_ORIGINS`), and it exposes
`Content-Disposition` so exported documents keep the per-matter filename the
server chose. Leave `VITE_API_BASE_URL` unset for the single-service
deployment, where CORS never applies.

## Conventions worth knowing

- **Design tokens live in `src/theme.css`** (light/dark via `data-theme` on
  `<html>`). Components must not hardcode colours.
- **`src/format.js` holds helpers and constants** separately from
  `shared.jsx`, so React Fast Refresh works. `POSTURES`, `STATUS_META` and
  friends live there for that reason.
- **`formatCurrency` abbreviates (₹1.23 L) and `formatRupeesExact` does not.**
  Any screen whose purpose is checking a figure against the department's
  annexure must use the exact one — an abbreviation cannot be reconciled.
- **A blank is never a zero.** An amount that could not be read carries
  `amount_unread`; clearing an input deletes the key rather than writing `0`.

## Views

`Dashboard` · `PanelWorkspace` (multi-file intake → defect review → live
deliberation) · `DefectList` · `MatterList` · `MatterDetail` (two separate
downloads: the filing reply and the internal file note, never merged) ·
`AdminPanel` · `GeneralCouncil` (heritage mode, off by default).
