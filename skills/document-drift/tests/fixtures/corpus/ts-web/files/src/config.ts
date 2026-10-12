export const config = {
  apiUrl: process.env.API_URL ?? "http://localhost:3000",
  port: Number(process.env.PORT ?? "8080"),
  logLevel: process.env.LOG_LEVEL ?? "info",
  featureFlags: (process.env.FEATURE_FLAGS ?? "").split(",").filter(Boolean),
};
