# Session Notes

## 2026-05-26

- Updated the Gemini default model from `gemini-1.5-pro` to `gemini-2.5-flash`.
- Added backend normalization so legacy `gemini-1.5-pro` configs are automatically upgraded to `gemini-2.5-flash`.
- Kept `GEMINI_MODEL` configurable through the environment so supported custom model overrides still work.
- Updated the local `.env`, `.env.example`, frontend fallback display, and `DETAIL.md` to keep the displayed/default model aligned with the supported backend value.

Reasoning:

- The Gemini video review flow was failing because the configured model `gemini-1.5-pro` is no longer available for the active `generateContent` API surface.
- A settings-layer normalization fix is safer than relying only on docs because it protects existing older `.env` files from silently breaking the feature again.
- `gemini-2.5-flash` was chosen as the new default because it is currently available for `generateContent` in the live model list and is a good fit for multimodal/social-caption generation.
