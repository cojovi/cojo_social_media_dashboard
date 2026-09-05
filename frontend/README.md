# ReelVault frontend

React 19, TypeScript, Vite, Tailwind, and Lucide. The main user guide is [../README.md](../README.md).

```bash
npm ci
npm run dev
npm run build
npm run lint
```

The development server proxies `/api` and `/thumbnails` to FastAPI on port 8000. The dashboard runs on port 5173 by default. `App.tsx` contains the archive/workbench, `ArchivePanel.tsx` shows background discovery/description controls, `api.ts` defines API contracts, and `useAnalysisQueue.ts` manages the separate browser-based full-video-review queue.

Archive data refreshes every ten seconds. Only the first 60 filtered cards render initially. Thumbnails are lazy-loaded; hover and editor opening never preload originals. The background quick-description queue belongs to the backend and survives closing this tab.
