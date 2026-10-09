# Front end

## Components

```
src/
├── App.tsx
├── main.tsx
└── components/
    ├── OldModal.tsx
    ├── Sidebar.tsx
    ├── Header.tsx
    └── Footer.tsx
```

Older browsers load [the legacy polyfills](../src/legacy/polyfills.ts) before the app boots.

Pages could later move into `src/pages/` once routing grows.

## Support

`src/legacy/polyfills.ts` was dropped together with IE11 support.
